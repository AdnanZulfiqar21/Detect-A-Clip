"""Untrusted pack loading with fail-closed checks (SEC-01 basic, RIGHTS-03 partial, D07/D10).

Order of checks (all must pass; any failure rejects the pack and leaves state unchanged):
 1. manifest size and JSON shape bounds
 2. key ID known and signature valid
 3. tuple compatibility (generator/preprocessing/index versions)
 4. payload size within the *total installed* budget (D10) and matches declared size/hash
 5. region assurance method accepted (D07: only NONE for synthetic packs by default)
 6. rights epoch never rolls back below the device's minimum epoch (RIGHTS-02 logic)
 7. validity window against trustworthy time (fail closed when time is untrusted)
 8. release mode refuses UNCALIBRATED manifests
 9. payload parses within bounds
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .. import GENERATOR_VERSION, INDEX_FORMAT_VERSION, PREPROCESSING_VERSION
from ..index.builder import TOTAL_INSTALLED_INDEX_BUDGET_BYTES, IndexBundle
from ..schemas import RegionAssuranceMethod
from .manifest import MAX_MANIFEST_BYTES, verify_signature

REQUIRED_KEYS = {
    "pack_id", "pack_version", "payload_sha256", "payload_size_bytes", "generator_version",
    "preprocessing_version", "index_format_version", "calibration_version", "calibration_status",
    "rights_epoch", "valid_from", "valid_until", "signed_time_basis", "key_id", "tombstones",
    "minimum_allowed_version", "region_grants", "operation_grants", "region_assurance_method",
    "indexed_hours", "title_count", "descriptor_bytes", "sampling_interval_s", "descriptor_family",
    "vector_count", "grant_id", "manifest_type", "signature",
}


class PackRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class DeviceRightsState:
    """Minimal persistent-by-design state the device must keep for rights safety.
    (Only epochs and installed byte totals; never anything query-derived.)"""

    minimum_rights_epoch: int = 0
    installed_index_bytes: Dict[str, int] = field(default_factory=dict)  # pack_id → bytes
    accepted_region_methods: Set[RegionAssuranceMethod] = field(default_factory=lambda: {RegionAssuranceMethod.NONE})
    trusted_keys: Dict[str, Ed25519PublicKey] = field(default_factory=dict)
    revoked_key_ids: Set[str] = field(default_factory=set)

    def total_installed_excluding(self, pack_id: str) -> int:
        return sum(b for p, b in self.installed_index_bytes.items() if p != pack_id)


@dataclass
class LoadedPack:
    manifest: Dict
    bundle: IndexBundle


def load_pack(
    manifest_json: bytes,
    payload: bytes,
    state: DeviceRightsState,
    now_iso: Optional[str],
    time_trustworthy: bool,
    release_mode: bool = False,
    budget_bytes: int = TOTAL_INSTALLED_INDEX_BUDGET_BYTES,
) -> LoadedPack:
    # 1. bounds + shape
    if len(manifest_json) > MAX_MANIFEST_BYTES:
        raise PackRejected("manifest too large")
    try:
        m = json.loads(manifest_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PackRejected("manifest not valid JSON")
    if not isinstance(m, dict) or set(m.keys()) != REQUIRED_KEYS:
        raise PackRejected("manifest keys mismatch")
    if m["manifest_type"] != "L0_DEV_INTEGRITY_MANIFEST":
        raise PackRejected("unknown manifest type")
    for k in ("payload_size_bytes", "rights_epoch", "title_count", "descriptor_bytes", "vector_count"):
        if not isinstance(m[k], int) or m[k] < 0:
            raise PackRejected(f"{k} must be a non-negative integer")

    # 2. key + signature
    key_id = m["key_id"]
    if key_id in state.revoked_key_ids:
        raise PackRejected("signer revoked")
    pub = state.trusted_keys.get(key_id)
    if pub is None:
        raise PackRejected("unknown signing key")
    if not verify_signature(m, pub):
        raise PackRejected("bad signature")

    # 3. tuple compatibility
    if (m["generator_version"], m["preprocessing_version"], m["index_format_version"]) != (
        GENERATOR_VERSION, PREPROCESSING_VERSION, INDEX_FORMAT_VERSION
    ):
        raise PackRejected("incompatible model/preprocessing/index tuple")

    # 4. size + hash
    if m["payload_size_bytes"] != len(payload):
        raise PackRejected("payload size mismatch")
    if state.total_installed_excluding(m["pack_id"]) + len(payload) > budget_bytes:
        raise PackRejected("total installed index budget exceeded")
    if hashlib.sha256(payload).hexdigest() != m["payload_sha256"]:
        raise PackRejected("payload hash mismatch")

    # 5. region assurance (D07)
    try:
        method = RegionAssuranceMethod(m["region_assurance_method"])
    except ValueError:
        raise PackRejected("unknown region assurance method")
    if method not in state.accepted_region_methods:
        raise PackRejected(f"region assurance method {method.value} not accepted")

    # 6. epoch rollback
    if m["rights_epoch"] < state.minimum_rights_epoch:
        raise PackRejected("rights epoch rollback")

    # 7. validity window (fail closed on untrusted time)
    if m["valid_until"] is not None:
        if not time_trustworthy or now_iso is None:
            raise PackRejected("time not trustworthy; cannot evaluate expiry")
        if now_iso >= m["valid_until"]:
            raise PackRejected("pack expired")
    if not time_trustworthy and m["valid_until"] is None and release_mode:
        raise PackRejected("time not trustworthy in release mode")

    # 8. calibration gate
    if release_mode and m["calibration_status"] != "CALIBRATED":
        raise PackRejected("UNCALIBRATED pack cannot pass a release gate")

    # 9. payload parse
    try:
        bundle = IndexBundle.from_bytes(payload, max_payload_bytes=budget_bytes)
    except ValueError as e:
        raise PackRejected(f"payload rejected: {e}")
    if bundle.vector_count != m["vector_count"] or bundle.family.value != m["descriptor_family"]:
        raise PackRejected("manifest/payload descriptor mismatch")
    if bundle.title_count != m["title_count"]:
        raise PackRejected("manifest/payload title count mismatch")

    # Commit device state only after every check passed (atomic activation).
    state.minimum_rights_epoch = max(state.minimum_rights_epoch, m["rights_epoch"])
    state.installed_index_bytes[m["pack_id"]] = len(payload)
    return LoadedPack(m, bundle)
