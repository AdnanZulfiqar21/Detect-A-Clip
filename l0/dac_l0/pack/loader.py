"""Untrusted pack loading with fail-closed checks (SEC-01, SEC-03 partial, RIGHTS-02/03/04 dev
scope, D07, D10).

Order of checks (all must pass; any failure raises PackRejected and leaves the device
state unchanged; state is only written after the last check):
  1. manifest size, JSON shape, field types, identifiers
  2. key ID known, not revoked, signature valid
  3. compatibility: index format, preprocessing for the descriptor family, generator
     (development packs), calibration status/version, descriptor family/bytes
  4. versions: strict MAJOR.MINOR.PATCH; pack >= its declared minimum; pack >= the highest
     minimum this device has already accepted for that pack ID (rollback restriction)
  5. payload size within the total installed budget (D10), declared size and hash
  6. region assurance method accepted (D07)
  7. rights epoch never rolls back (RIGHTS-02)
  8. validity window on parsed instants (explicit offsets only), trusted-time rules
  9. release mode: only CALIBRATED, licensed packs with an expiry
 10. payload parse within bounds and consistency with the manifest (family, counts,
     sampling interval, indexed hours)

Synthetic development packs vs licensed/release packs: a development pack is signed under
the self-created synthetic grant (L0_GRANT_ID). It may load on untrusted time only if it has
no expiry, and it may never claim CALIBRATED. Every other pack is treated as licensed: it
needs an expiry and trusted time, and release mode additionally needs CALIBRATED.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, Tuple, Union

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .. import EXACT_PREPROCESSING_VERSION, GENERATOR_VERSION, PREPROCESSING_VERSION
from ..index.builder import TOTAL_INSTALLED_INDEX_BUDGET_BYTES, IndexBundle
from ..index.descriptors import DescriptorFamily
from ..schemas import PermittedAct, RegionAssuranceMethod
from ..synth.manifest import L0_GRANT_ID
from ..index.format import SUPPORTED_FORMATS, strict_json_loads
from .manifest import MAX_MANIFEST_BYTES, verify_signature

REQUIRED_KEYS = {
    "pack_id", "pack_version", "payload_sha256", "payload_size_bytes", "generator_version",
    "preprocessing_version", "index_format_version", "calibration_version", "calibration_status",
    "rights_epoch", "valid_from", "valid_until", "signed_time_basis", "key_id", "tombstones",
    "minimum_allowed_version", "region_grants", "operation_grants", "region_assurance_method",
    "indexed_hours", "title_count", "descriptor_bytes", "sampling_interval_s", "descriptor_family",
    "vector_count", "grant_id", "manifest_type", "signature",
}
CALIBRATION_STATUSES = {"UNCALIBRATED", "CALIBRATED_L0_SYNTHETIC", "CALIBRATED"}
SUPPORTED_INDEX_FORMATS = set(SUPPORTED_FORMATS)
_PACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_VERSION = re.compile(r"^(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})$")
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$")

Version = Tuple[int, int, int]


class PackRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class DeviceRightsState:
    """Minimal persistent-by-design state the device keeps for rights safety. Only epochs,
    version floors and installed byte totals; never anything query-derived."""

    minimum_rights_epoch: int = 0
    installed_index_bytes: Dict[str, int] = field(default_factory=dict)  # pack_id -> bytes
    minimum_pack_versions: Dict[str, Version] = field(default_factory=dict)  # pack_id -> floor
    accepted_region_methods: Set[RegionAssuranceMethod] = field(default_factory=lambda: {RegionAssuranceMethod.NONE})
    trusted_keys: Dict[str, Ed25519PublicKey] = field(default_factory=dict)
    revoked_key_ids: Set[str] = field(default_factory=set)

    def total_installed_excluding(self, pack_id: str) -> int:
        return sum(b for p, b in self.installed_index_bytes.items() if p != pack_id)


@dataclass
class LoadedPack:
    manifest: Dict
    bundle: IndexBundle


def parse_instant(value, what: str) -> datetime:
    """ISO-8601 instant with an explicit offset (Z or +HH:MM). Naive or malformed -> reject."""
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        raise PackRejected(f"{what} malformed or missing (explicit UTC offset required)")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PackRejected(f"{what} malformed or missing (not a calendar instant)")
    if t.tzinfo is None or t.utcoffset() is None:
        raise PackRejected(f"{what} malformed or missing (explicit UTC offset required)")
    return t


def parse_version(value, what: str) -> Version:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise PackRejected(f"{what} malformed (MAJOR.MINOR.PATCH, no leading zeros or suffixes)")
    a, b, c = value.split(".")
    return int(a), int(b), int(c)


def is_development_pack(m: Dict) -> bool:
    return m.get("grant_id") == L0_GRANT_ID and m.get("manifest_type") == "L0_DEV_INTEGRITY_MANIFEST"


def expected_preprocessing(family: DescriptorFamily) -> str:
    return EXACT_PREPROCESSING_VERSION if family == DescriptorFamily.DACDHASH else PREPROCESSING_VERSION


def _now(now: Union[None, str, datetime]) -> datetime:
    if isinstance(now, datetime):
        t = now
    elif isinstance(now, str) and _INSTANT.fullmatch(now):
        t = datetime.fromisoformat(now.replace("Z", "+00:00"))
    else:
        raise PackRejected("current time missing or malformed although marked trustworthy (explicit UTC offset required)")
    if t.tzinfo is None or t.utcoffset() is None:
        raise PackRejected("current time naive although marked trustworthy")
    return t


def load_pack(
    manifest_json: bytes,
    payload: bytes,
    state: DeviceRightsState,
    now: Union[None, str, datetime],
    time_trustworthy: bool,
    release_mode: bool = False,
    budget_bytes: int = TOTAL_INSTALLED_INDEX_BUDGET_BYTES,
) -> LoadedPack:
    # 1. bounds, shape, types
    if len(manifest_json) > MAX_MANIFEST_BYTES:
        raise PackRejected("manifest too large")
    try:
        m = strict_json_loads(manifest_json)
    except (UnicodeDecodeError, ValueError):
        raise PackRejected("manifest not valid JSON")
    if not isinstance(m, dict) or set(m.keys()) != REQUIRED_KEYS:
        raise PackRejected("manifest keys mismatch")
    if m["manifest_type"] != "L0_DEV_INTEGRITY_MANIFEST":
        raise PackRejected("unknown manifest type")
    for k in ("payload_size_bytes", "rights_epoch", "title_count", "descriptor_bytes", "vector_count"):
        if not isinstance(m[k], int) or isinstance(m[k], bool) or m[k] < 0:
            raise PackRejected(f"{k} must be a non-negative integer")
    for k in ("indexed_hours", "sampling_interval_s"):
        v = m[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
            raise PackRejected(f"{k} must be a finite non-negative number")
    if not isinstance(m["pack_id"], str) or not _PACK_ID.fullmatch(m["pack_id"]):
        raise PackRejected("bad pack_id")
    for k in ("generator_version", "preprocessing_version", "index_format_version", "calibration_version",
              "signed_time_basis", "key_id", "grant_id", "payload_sha256"):
        if not isinstance(m[k], str) or not m[k].strip():
            raise PackRejected(f"{k} must be a non-empty string")
    if not isinstance(m["tombstones"], list) or not all(isinstance(t, str) for t in m["tombstones"]):
        raise PackRejected("tombstones must be a list of strings")
    if not isinstance(m["region_grants"], list) or not all(isinstance(t, str) and t for t in m["region_grants"]):
        raise PackRejected("region_grants must be a list of strings")
    try:
        if not isinstance(m["operation_grants"], list):
            raise ValueError
        for a in m["operation_grants"]:
            PermittedAct(a)
    except (ValueError, TypeError):
        raise PackRejected("operation_grants contain an unknown act")
    dev = is_development_pack(m)

    # 2. key + signature
    key_id = m["key_id"]
    if key_id in state.revoked_key_ids:
        raise PackRejected("signer revoked")
    pub = state.trusted_keys.get(key_id)
    if pub is None:
        raise PackRejected("unknown signing key")
    if not verify_signature(m, pub):
        raise PackRejected("bad signature")

    # 3. compatibility
    if m["index_format_version"] not in SUPPORTED_INDEX_FORMATS:
        raise PackRejected("incompatible index format version")
    try:
        family = DescriptorFamily(m["descriptor_family"])
    except ValueError:
        raise PackRejected("unknown descriptor family")
    if m["descriptor_bytes"] != family.descriptor_bytes:
        raise PackRejected("descriptor family/bytes mismatch")
    if m["preprocessing_version"] != expected_preprocessing(family):
        raise PackRejected("incompatible preprocessing for the descriptor family")
    if dev and m["generator_version"] != GENERATOR_VERSION:
        raise PackRejected("incompatible synthetic generator version")
    if m["calibration_status"] not in CALIBRATION_STATUSES:
        raise PackRejected("unknown calibration_status")
    if dev and m["calibration_status"] == "CALIBRATED":
        raise PackRejected("synthetic development pack cannot claim release calibration_status")

    # 4. versions
    version = parse_version(m["pack_version"], "pack_version")
    declared_min = parse_version(m["minimum_allowed_version"], "minimum_allowed_version")
    if version < declared_min:
        raise PackRejected("pack_version below minimum allowed version declared by the manifest")
    floor = state.minimum_pack_versions.get(m["pack_id"])
    if floor is not None and version < floor:
        raise PackRejected("pack version rollback below the device's recorded minimum")

    # 5. size + hash
    if m["payload_size_bytes"] != len(payload):
        raise PackRejected("payload size mismatch")
    if state.total_installed_excluding(m["pack_id"]) + len(payload) > budget_bytes:
        raise PackRejected("total installed index budget exceeded")
    if hashlib.sha256(payload).hexdigest() != m["payload_sha256"]:
        raise PackRejected("payload hash mismatch")

    # 6. region assurance (D07)
    try:
        method = RegionAssuranceMethod(m["region_assurance_method"])
    except ValueError:
        raise PackRejected("unknown region assurance method")
    if method not in state.accepted_region_methods:
        raise PackRejected(f"region assurance method {method.value} not accepted")

    # 7. epoch rollback
    if m["rights_epoch"] < state.minimum_rights_epoch:
        raise PackRejected("rights epoch rollback")

    # 8. validity window
    valid_from = parse_instant(m["valid_from"], "valid_from")
    valid_until = None if m["valid_until"] is None else parse_instant(m["valid_until"], "valid_until")
    if valid_until is not None and valid_until <= valid_from:
        raise PackRejected("invalid validity window (valid_until must be after valid_from)")
    if time_trustworthy:
        now_t = _now(now)
        if now_t < valid_from:
            raise PackRejected("pack not yet valid")
        if valid_until is not None and now_t >= valid_until:
            raise PackRejected("pack expired")
    elif valid_until is not None or not dev or release_mode:
        raise PackRejected("time not trustworthy; licensed packs and packs with an expiry need trusted time")
    if (not dev or release_mode) and valid_until is None:
        raise PackRejected("licensed/release packs need a valid_until")

    # 9. release gate
    if release_mode and (dev or m["calibration_status"] != "CALIBRATED"):
        raise PackRejected("release gate requires a licensed CALIBRATED pack (UNCALIBRATED and L0 synthetic calibration never pass)")

    # 10. payload parse + consistency
    try:
        bundle = IndexBundle.from_bytes(payload, max_payload_bytes=budget_bytes)
    except ValueError as e:
        raise PackRejected(f"payload rejected: {e}")
    if bundle.source_format != m["index_format_version"]:
        raise PackRejected("manifest/payload index format mismatch")
    if bundle.family != family or bundle.vector_count != m["vector_count"]:
        raise PackRejected("manifest/payload descriptor mismatch")
    if bundle.title_count != m["title_count"]:
        raise PackRejected("manifest/payload title count mismatch")
    if abs(bundle.sampling_interval_s - float(m["sampling_interval_s"])) > 1e-9:
        raise PackRejected("manifest/payload sampling interval mismatch")
    expected_hours = bundle.vector_count * bundle.sampling_interval_s / 3600.0
    if abs(float(m["indexed_hours"]) - expected_hours) > 1e-6 * max(1.0, expected_hours):
        raise PackRejected("manifest indexed_hours inconsistent with the payload")

    # Commit device state only after every check passed (atomic activation).
    state.minimum_rights_epoch = max(state.minimum_rights_epoch, m["rights_epoch"])
    state.installed_index_bytes[m["pack_id"]] = len(payload)
    state.minimum_pack_versions[m["pack_id"]] = max(floor or (0, 0, 0), declared_min)
    return LoadedPack(m, bundle)
