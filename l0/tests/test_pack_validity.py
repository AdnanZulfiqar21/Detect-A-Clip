"""Pack validity-window, compatibility and version rules (owner finding 2026-10-10).

Every fixture is *correctly signed* with a development key after the field change, so a
rejection proves the rule, not the signature check. Every rejection must leave the device
rights state unchanged.
"""
import json

import pytest

from dac_l0.index.builder import build_index
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.pack.loader import DeviceRightsState, PackRejected, load_pack
from dac_l0.pack.manifest import build_manifest, canonical_bytes, generate_dev_key, load_private, load_public, manifest_to_dict
from dac_l0.synth.generator import Edition, EditionKind, gallery_works

NOW = "2026-10-10T12:00:00+00:00"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("k")
    kid, priv, pub = generate_dev_key(d)
    b = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(2)], DescriptorFamily.HASH64)
    return kid, load_private(priv), load_public(pub), b


def signed(env, **fields):
    kid, priv, _, b = env
    d = manifest_to_dict(build_manifest(b, "L0-T", "1.0.0", kid))
    d["valid_from"] = "2026-10-01T00:00:00+00:00"
    d.update(fields)
    d.pop("signature", None)
    d["signature"] = priv.sign(canonical_bytes(d)).hex()
    return json.dumps(d).encode()


def state(env):
    s = DeviceRightsState()
    s.trusted_keys[env[0]] = env[2]
    return s


def reject(env, reason, manifest, now=NOW, trusted=True, release=False, st=None):
    st = st or state(env)
    before = (st.minimum_rights_epoch, dict(st.installed_index_bytes), dict(st.minimum_pack_versions))
    with pytest.raises(PackRejected) as e:
        load_pack(manifest, env[3].to_bytes(), st, now, trusted, release)
    assert reason in e.value.reason, e.value.reason
    assert (st.minimum_rights_epoch, dict(st.installed_index_bytes), dict(st.minimum_pack_versions)) == before


def accept(env, manifest, now=NOW, trusted=True, st=None):
    st = st or state(env)
    return load_pack(manifest, env[3].to_bytes(), st, now, trusted, False), st


# ------------------------------------------------------------------ validity window


def test_baseline_accepts(env):
    accept(env, signed(env))


def test_future_valid_from_rejected(env):
    reject(env, "not yet valid", signed(env, valid_from="2026-11-01T00:00:00+00:00"))


def test_inverted_or_empty_window_rejected(env):
    reject(env, "validity window", signed(env, valid_from="2026-10-05T00:00:00+00:00", valid_until="2026-10-04T00:00:00+00:00"))
    reject(env, "validity window", signed(env, valid_from="2026-10-05T00:00:00+00:00", valid_until="2026-10-05T00:00:00+00:00"))


def test_timezone_offsets_compared_as_instants(env):
    # 2026-12-31T23:00-05:00 is 2027-01-01T04:00Z: still valid at 02:00Z (string order says expired).
    accept(env, signed(env, valid_until="2026-12-31T23:00:00-05:00"), now="2027-01-01T02:00:00+00:00")
    # 2027-01-01T01:00+05:00 is 2026-12-31T20:00Z: expired at 22:00Z (string order says valid).
    reject(env, "expired", signed(env, valid_until="2027-01-01T01:00:00+05:00"), now="2026-12-31T22:00:00Z")
    # Equal instants written with different offsets: valid_until is exclusive.
    reject(env, "expired", signed(env, valid_until="2026-10-10T17:30:00+05:30"), now="2026-10-10T12:00:00Z")


@pytest.mark.parametrize("bad", ["yesterday", "2026-10-10T00:00:00", "2026-13-01T00:00:00+00:00", "", 20261010, None])
def test_malformed_or_missing_valid_from_rejected(env, bad):
    reject(env, "valid_from", signed(env, valid_from=bad))


@pytest.mark.parametrize("bad", ["soon", "2026-12-31", "2026-12-31T00:00:00", 5])
def test_malformed_valid_until_rejected(env, bad):
    reject(env, "valid_until", signed(env, valid_until=bad))


def test_malformed_now_is_a_caller_error_not_a_pass(env):
    reject(env, "time", signed(env), now="not-a-time")
    reject(env, "time", signed(env), now="2026-10-10T12:00:00")  # naive


def test_untrusted_time_dev_vs_licensed(env):
    # A synthetic development pack without expiry may load on untrusted time (documented).
    accept(env, signed(env), now=None, trusted=False)
    # Any pack with an expiry, or any non-development pack, needs trusted time.
    reject(env, "trustworthy", signed(env, valid_until="2027-01-01T00:00:00Z"), now=None, trusted=False)
    reject(env, "trustworthy", signed(env, grant_id="GRANT-LICENSED-001"), now=None, trusted=False)


def test_licensed_pack_requires_expiry(env):
    reject(env, "valid_until", signed(env, grant_id="GRANT-LICENSED-001"))


# ------------------------------------------------------------------ compatibility


@pytest.mark.parametrize("field,value,reason", [
    ("calibration_status", "PROBABLY_FINE", "calibration_status"),
    ("calibration_version", "", "calibration_version"),
    ("descriptor_family", "THUMB32", "descriptor"),
    ("descriptor_family", "NOT_A_FAMILY", "descriptor"),
    ("descriptor_bytes", 32, "descriptor"),
    ("sampling_interval_s", 5.0, "sampling"),
    ("indexed_hours", 99.0, "indexed_hours"),
    ("title_count", 7, "title count"),
    ("vector_count", 1, "descriptor"),
    ("signed_time_basis", "", "signed_time_basis"),
    ("pack_id", "../evil", "pack_id"),
])
def test_incompatible_metadata_rejected(env, field, value, reason):
    reject(env, reason, signed(env, **{field: value}))


def test_uncalibrated_or_lab_calibration_never_passes_release(env):
    reject(env, "release", signed(env, valid_until="2027-01-01T00:00:00Z"), release=True)
    reject(env, "release", signed(env, calibration_status="CALIBRATED_L0_SYNTHETIC", valid_until="2027-01-01T00:00:00Z"), release=True)


# ------------------------------------------------------------------ versions / rollback


@pytest.mark.parametrize("v", ["1", "1.0", "v1.0.0", "1.0.0-beta", "01.0.0", "", "1..0"])
def test_malformed_versions_rejected(env, v):
    reject(env, "version", signed(env, pack_version=v))
    reject(env, "version", signed(env, minimum_allowed_version=v))


def test_pack_older_than_its_own_declared_minimum_rejected(env):
    reject(env, "below minimum", signed(env, pack_version="1.0.0", minimum_allowed_version="1.2.0"))


def test_declared_minimum_is_remembered_and_blocks_rollback(env):
    _, st = accept(env, signed(env, pack_version="2.1.0", minimum_allowed_version="2.0.0"))
    assert st.minimum_pack_versions["L0-T"] == (2, 0, 0)
    # An older pack that declares a lower minimum is still refused (rollback restriction).
    reject(env, "rollback", signed(env, pack_version="1.9.0", minimum_allowed_version="1.0.0"), st=st)
    # Version ordering is numeric, not lexical: 2.10.0 > 2.9.0.
    accept(env, signed(env, pack_version="2.10.0", minimum_allowed_version="2.0.0"), st=st)
    # The remembered minimum never decreases.
    accept(env, signed(env, pack_version="2.11.0", minimum_allowed_version="1.0.0"), st=st)
    assert st.minimum_pack_versions["L0-T"] == (2, 0, 0)
