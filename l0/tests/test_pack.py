"""SEC-01 (basic L0), RIGHTS-02 epoch logic, RIGHTS-03 region method, D10 total budget,
and untrusted payload parsing bounds."""
import json
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)

import struct

import pytest

from dac_l0.index.builder import HEADER_FMT, HEADER_SIZE, IndexBundle, build_index
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.pack.loader import DeviceRightsState, PackRejected, load_pack
from dac_l0.pack.manifest import build_manifest, generate_dev_key, load_private, load_public, sign_manifest
from dac_l0.schemas import RegionAssuranceMethod
from dac_l0.synth.generator import Edition, EditionKind, gallery_works


@pytest.fixture(scope="module")
def bundle():
    eds = [Edition(w, EditionKind.THEATRICAL) for w in gallery_works(3)]
    return build_index(eds, DescriptorFamily.HASH64, 2.0)


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    d = tmp_path_factory.mktemp("keys")
    kid, priv, pub = generate_dev_key(d)
    kid2, priv2, pub2 = generate_dev_key(d)
    return {"kid": kid, "priv": load_private(priv), "pub": load_public(pub), "kid2": kid2, "priv2": load_private(priv2), "pub2": load_public(pub2)}


def signed(bundle, keys, **kw):
    priv = kw.pop("priv", keys["priv"])
    kid = kw.pop("kid", keys["kid"])
    m = build_manifest(bundle, kw.pop("pack_id", "L0-T"), "0.1.0", kid, **kw)
    return json.dumps(sign_manifest(m, priv)).encode()


def state(keys, **kw):
    s = DeviceRightsState(**kw)
    s.trusted_keys[keys["kid"]] = keys["pub"]
    return s


def test_valid_pack_loads_and_commits_state(bundle, keys):
    s = state(keys)
    lp = load_pack(signed(bundle, keys, rights_epoch=3), bundle.to_bytes(), s, now(), True)
    assert lp.bundle.vector_count == bundle.vector_count
    assert lp.manifest["calibration_status"] == "UNCALIBRATED"
    assert s.minimum_rights_epoch == 3
    assert s.installed_index_bytes["L0-T"] == len(bundle.to_bytes())


def _assert_rejected_unchanged(fn, s, reason_part):
    before = (s.minimum_rights_epoch, dict(s.installed_index_bytes))
    with pytest.raises(PackRejected) as e:
        fn()
    assert reason_part in e.value.reason
    assert (s.minimum_rights_epoch, dict(s.installed_index_bytes)) == before


def test_payload_byte_flip_rejected(bundle, keys):
    s = state(keys)
    p = bytearray(bundle.to_bytes())
    p[-5] ^= 0x01
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys), bytes(p), s, now(), True), s, "hash mismatch")


def test_manifest_field_tamper_breaks_signature(bundle, keys):
    s = state(keys)
    m = json.loads(signed(bundle, keys))
    m["calibration_status"] = "CALIBRATED"
    _assert_rejected_unchanged(lambda: load_pack(json.dumps(m).encode(), bundle.to_bytes(), s, now(), True), s, "bad signature")


def test_unknown_and_revoked_signers_rejected(bundle, keys):
    s = state(keys)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys, priv=keys["priv2"], kid=keys["kid2"]), bundle.to_bytes(), s, now(), True), s, "unknown signing key")
    s.revoked_key_ids.add(keys["kid"])
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys), bundle.to_bytes(), s, now(), True), s, "signer revoked")


def test_key_substitution_with_other_trusted_key_rejected(bundle, keys):
    """Signed by key2 but claiming key1's ID."""
    s = state(keys)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys, priv=keys["priv2"], kid=keys["kid"]), bundle.to_bytes(), s, now(), True), s, "bad signature")


def test_rights_epoch_cannot_roll_back(bundle, keys):
    s = state(keys)
    load_pack(signed(bundle, keys, rights_epoch=5), bundle.to_bytes(), s, now(), True)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys, rights_epoch=4), bundle.to_bytes(), s, now(), True), s, "epoch rollback")


@pytest.mark.parametrize("method", [RegionAssuranceMethod.ONLINE_ACTIVATION, RegionAssuranceMethod.STORE_COUNTRY_ATTESTATION, RegionAssuranceMethod.COARSE_LOCATION])
def test_unaccepted_region_assurance_method_refused_at_activation(bundle, keys, method):
    """D07: online activation (or any method) is not territory proof until accepted."""
    s = state(keys)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys, region_assurance_method=method), bundle.to_bytes(), s, now(), True), s, "not accepted")


def test_total_installed_budget_is_not_per_pack(bundle, keys):
    """D10: two packs share one 250 MB cap (scaled down here)."""
    size = len(bundle.to_bytes())
    s = state(keys)
    budget = int(size * 1.5)
    load_pack(signed(bundle, keys, pack_id="A"), bundle.to_bytes(), s, now(), True, budget_bytes=budget)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys, pack_id="B"), bundle.to_bytes(), s, now(), True, budget_bytes=budget), s, "budget exceeded")
    # Replacing the same pack id is allowed (its old bytes are excluded from the total).
    load_pack(signed(bundle, keys, pack_id="A"), bundle.to_bytes(), s, now(), True, budget_bytes=budget)


def test_expiry_requires_trustworthy_time(bundle, keys):
    s = state(keys)
    m = signed(bundle, keys, valid_until="2026-12-31T00:00:00+00:00")
    _assert_rejected_unchanged(lambda: load_pack(m, bundle.to_bytes(), s, None, False), s, "not trustworthy")
    _assert_rejected_unchanged(lambda: load_pack(m, bundle.to_bytes(), s, "2027-01-01T00:00:00+00:00", True), s, "expired")
    load_pack(m, bundle.to_bytes(), s, "2026-11-01T00:00:00+00:00", True)


def test_release_mode_refuses_uncalibrated(bundle, keys):
    s = state(keys)
    _assert_rejected_unchanged(lambda: load_pack(signed(bundle, keys), bundle.to_bytes(), s, now(), True, release_mode=True), s, "release")


def test_oversized_manifest_rejected(bundle, keys):
    s = state(keys)
    _assert_rejected_unchanged(lambda: load_pack(b"{" + b" " * 70_000 + b"}", bundle.to_bytes(), s, now(), True), s, "too large")


def test_extra_manifest_key_rejected(bundle, keys):
    s = state(keys)
    m = json.loads(signed(bundle, keys))
    m["dynamic_code_url"] = "https://example.invalid/x.js"
    _assert_rejected_unchanged(lambda: load_pack(json.dumps(m).encode(), bundle.to_bytes(), s, now(), True), s, "keys mismatch")


# ---------------------------------------------------------- untrusted payload parsing


def test_parser_rejects_truncation_at_every_boundary(bundle):
    data = bundle.to_bytes()
    for cut in [0, 5, HEADER_SIZE, HEADER_SIZE + 3, HEADER_SIZE + 10, len(data) - 1]:
        with pytest.raises(ValueError):
            IndexBundle.from_bytes(data[:cut])


def test_parser_rejects_inflated_vector_count(bundle):
    data = bytearray(bundle.to_bytes())
    magic, ver, db, n, nw, iv = struct.unpack(HEADER_FMT, bytes(data[:HEADER_SIZE]))
    data[:HEADER_SIZE] = struct.pack(HEADER_FMT, magic, ver, db, n + 1, nw, iv)
    with pytest.raises(ValueError, match="body length"):
        IndexBundle.from_bytes(bytes(data))
    data[:HEADER_SIZE] = struct.pack(HEADER_FMT, magic, ver, db, 2**31, nw, iv)
    with pytest.raises(ValueError, match="out of bounds"):
        IndexBundle.from_bytes(bytes(data))


def test_parser_rejects_locator_pointing_at_unknown_work(bundle):
    b = IndexBundle.from_bytes(bundle.to_bytes())
    locs = b.locators.copy()
    locs[0, 0:4] = list((len(b.works) + 7).to_bytes(4, "little"))
    bad = IndexBundle(b.family, b.sampling_interval_s, b.descriptors, locs, b.works)
    with pytest.raises(ValueError, match="unknown work"):
        IndexBundle.from_bytes(bad.to_bytes())


def test_parser_rejects_bad_metadata_and_unknown_descriptor_size(bundle):
    data = bytearray(bundle.to_bytes())
    meta_off = HEADER_SIZE + 4
    data[meta_off] = ord("X")  # break the JSON
    with pytest.raises(ValueError):
        IndexBundle.from_bytes(bytes(data))
    data = bytearray(bundle.to_bytes())
    magic, ver, db, n, nw, iv = struct.unpack(HEADER_FMT, bytes(data[:HEADER_SIZE]))
    data[:HEADER_SIZE] = struct.pack(HEADER_FMT, magic, ver, 77, n, nw, iv)
    with pytest.raises(ValueError, match="descriptor size"):
        IndexBundle.from_bytes(bytes(data))


def test_roundtrip_is_bit_exact_and_build_is_reproducible(bundle):
    assert IndexBundle.from_bytes(bundle.to_bytes()).to_bytes() == bundle.to_bytes()
    eds = [Edition(w, EditionKind.THEATRICAL) for w in gallery_works(3)]
    assert build_index(eds, DescriptorFamily.HASH64, 2.0).sha256() == bundle.sha256()


# ------------------------------------------------------------ P04-T04a display names


def test_display_names_round_trip_and_resolution():
    from dac_l0.index.builder import resolve_display_name

    eds = [Edition(w, EditionKind.THEATRICAL) for w in gallery_works(1)]
    b = build_index(eds, DescriptorFamily.HASH64, 2.0)
    b.works[0].names = {"en": "Synthetic Work 000", "ur-Latn": "Masnooi Kaam 000", "tr": "Sentetik Eser 000"}
    b2 = IndexBundle.from_bytes(b.to_bytes())
    n = b2.works[0].names
    assert resolve_display_name(n, ["ur-Latn"], "x") == "Masnooi Kaam 000"
    assert resolve_display_name(n, ["ur-PK"], "x") == "Masnooi Kaam 000"   # same language
    assert resolve_display_name(n, ["ko"], "x") == "Synthetic Work 000"    # English fallback
    assert resolve_display_name({}, ["ko"], "SW000") == "SW000"


@pytest.mark.parametrize("names", [
    {"not a tag": "x"}, {"en": ""}, {"en": "a" * 201}, {"en": "line\nbreak"},
    {f"x{i:02d}": "n" for i in range(17)},
])
def test_display_name_bounds_rejected(names):
    eds = [Edition(w, EditionKind.THEATRICAL) for w in gallery_works(1)]
    b = build_index(eds, DescriptorFamily.HASH64, 2.0)
    b.works[0].names = names
    with pytest.raises(ValueError):
        IndexBundle.from_bytes(b.to_bytes())
