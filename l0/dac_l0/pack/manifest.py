"""Signed development integrity manifest for L0 packs.

The manifest binds the complete model/preprocessing/index/calibration/rights tuple
(F04). Development packs are explicitly UNCALIBRATED and cannot pass a release gate.
Signing uses Ed25519 with a locally generated DEVELOPMENT_ONLY key; the private key is
git-ignored. A development key never becomes a release key (ED-05).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .. import EXACT_PREPROCESSING_VERSION, GENERATOR_VERSION, INDEX_FORMAT_VERSION, PREPROCESSING_VERSION
from ..index.builder import IndexBundle
from ..schemas import PackManifest, PermittedAct, RegionAssuranceMethod
from ..synth.manifest import L0_GRANT_ID

DEV_KEY_ID_PREFIX = "DEVKEY-"
MAX_MANIFEST_BYTES = 64 * 1024


def canonical_bytes(manifest_dict: Dict) -> bytes:
    d = {k: v for k, v in manifest_dict.items() if k != "signature"}
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def generate_dev_key(dir_: Path) -> Tuple[str, Path, Path]:
    """Create a DEVELOPMENT_ONLY Ed25519 keypair. Returns (key_id, private_path, public_path)."""
    dir_.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = DEV_KEY_ID_PREFIX + hashlib.sha256(pub_bytes).hexdigest()[:16]
    priv_path = dir_ / f"{key_id}.dev.private.pem"
    pub_path = dir_ / f"{key_id}.public.pem"
    priv_path.write_bytes(
        priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    pub_path.write_bytes(pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return key_id, priv_path, pub_path


def load_private(path: Path) -> Ed25519PrivateKey:
    k = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(k, Ed25519PrivateKey):
        raise ValueError("not an Ed25519 private key")
    return k


def load_public(path: Path) -> Ed25519PublicKey:
    k = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(k, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return k


def build_manifest(
    bundle: IndexBundle,
    pack_id: str,
    pack_version: str,
    key_id: str,
    rights_epoch: int = 1,
    calibration_version: str = "dev-uncalibrated-1",
    calibration_status: str = "UNCALIBRATED",
    valid_until: Optional[str] = None,
    region_assurance_method: RegionAssuranceMethod = RegionAssuranceMethod.NONE,
    tombstones: Optional[list] = None,
    minimum_allowed_version: str = "0.1.0",
    valid_from: Optional[str] = None,
) -> PackManifest:
    payload = bundle.to_bytes()
    return PackManifest(
        pack_id=pack_id,
        pack_version=pack_version,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_size_bytes=len(payload),
        generator_version=GENERATOR_VERSION,
        preprocessing_version=EXACT_PREPROCESSING_VERSION if bundle.family.value == "DACDHASH" else PREPROCESSING_VERSION,
        index_format_version=INDEX_FORMAT_VERSION,
        calibration_version=calibration_version,
        calibration_status=calibration_status,
        rights_epoch=rights_epoch,
        valid_from=valid_from or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        valid_until=valid_until,
        signed_time_basis="build-host-utc",
        key_id=key_id,
        tombstones=list(tombstones or []),
        minimum_allowed_version=minimum_allowed_version,
        region_grants=["*"],
        operation_grants=[
            PermittedAct.LOCAL_DISTRIBUTION, PermittedAct.TRANSIENT_QUERY, PermittedAct.DECISION,
            PermittedAct.DISPLAY_METADATA, PermittedAct.EVALUATION,
        ],
        region_assurance_method=region_assurance_method,
        indexed_hours=bundle.indexed_hours,
        title_count=bundle.title_count,
        descriptor_bytes=bundle.family.descriptor_bytes,
        sampling_interval_s=bundle.sampling_interval_s,
        descriptor_family=bundle.family.value,
        vector_count=bundle.vector_count,
        grant_id=L0_GRANT_ID,
    )


def manifest_to_dict(m: PackManifest) -> Dict:
    d = asdict(m)
    d["operation_grants"] = [a.value for a in m.operation_grants]
    d["region_assurance_method"] = m.region_assurance_method.value
    d["manifest_type"] = "L0_DEV_INTEGRITY_MANIFEST"
    return d


def sign_manifest(m: PackManifest, priv: Ed25519PrivateKey) -> Dict:
    d = manifest_to_dict(m)
    d["signature"] = priv.sign(canonical_bytes(d)).hex()
    return d


def verify_signature(signed: Dict, pub: Ed25519PublicKey) -> bool:
    try:
        sig = bytes.fromhex(signed["signature"])
    except (KeyError, ValueError, TypeError):
        return False
    try:
        pub.verify(sig, canonical_bytes(signed))
        return True
    except InvalidSignature:
        return False


def write_pack(out_dir: Path, bundle: IndexBundle, signed_manifest: Dict, pack_id: str) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_path = out_dir / f"{pack_id}.pack"
    manifest_path = out_dir / f"{pack_id}.manifest.json"
    payload_path.write_bytes(bundle.to_bytes())
    manifest_path.write_text(json.dumps(signed_manifest, indent=1, sort_keys=True), encoding="utf-8")
    return payload_path, manifest_path
