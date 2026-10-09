"""IDX-01 (interrupted / disk-full / atomic activation), RIGHTS-02 (epoch survives restore),
RIGHTS-04 analogue (lab lease through reboot, rollback, untrusted time). Desktop dev scope."""
import json
import shutil
from dataclasses import replace

import pytest

from dac_l0.index.builder import build_index
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.pack.loader import DeviceRightsState, PackRejected
from dac_l0.pack.manifest import build_manifest, generate_dev_key, load_private, load_public, sign_manifest
from dac_l0.pack.store import Io, LabLease, PackStore, StoreError, TrustedTime
from dac_l0.synth.generator import Edition, EditionKind, gallery_works


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    d = tmp_path_factory.mktemp("k")
    kid, priv, pub = generate_dev_key(d)
    b1 = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(2)], DescriptorFamily.HASH64)
    b2 = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(3)], DescriptorFamily.HASH64)
    return kid, load_private(priv), load_public(pub), b1, b2


def signed(m, bundle, version, epoch):
    kid, priv, _, _, _ = m
    return json.dumps(sign_manifest(build_manifest(bundle, "L0-T", version, kid, rights_epoch=epoch), priv)).encode()


def rights(m):
    r = DeviceRightsState()
    r.trusted_keys[m[0]] = m[2]
    return r


def test_install_activates_and_reloads_after_restart(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)
    s2 = PackStore(tmp_path, rights(material))
    assert s2.active("L0-T", None, True).bundle.vector_count == material[3].vector_count
    assert s2.state.active_versions["L0-T"] == "1"
    assert not any((tmp_path / "staging").iterdir())


@pytest.mark.parametrize("fail_on", ["payload", "manifest", "activate", "state"])
def test_failure_at_each_step_keeps_previous_pack_and_state(tmp_path, material, fail_on):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)
    before_state = (tmp_path / "state.json").read_bytes()

    calls = {"n": 0}
    real = Io()

    def write_bytes(p, b):
        if (fail_on == "payload" and p.name == "payload.pack") or (fail_on == "manifest" and p.name == "manifest.json") \
                or (fail_on == "state" and p.name == "state.json.tmp"):
            raise OSError(28, "No space left on device")
        real.write_bytes(p, b)

    def rep(a, b):
        if fail_on == "activate" and b.parent.name == "active" and a.parent.name == "staging":
            raise OSError("interrupted")
        real.replace(a, b)

    s.io = Io(write_bytes=write_bytes, replace=rep, rmtree=real.rmtree)
    with pytest.raises(OSError):
        s.install(signed(material, material[4], "2", 2), material[4].to_bytes(), None, True)
    s3 = PackStore(tmp_path, rights(material))
    assert (tmp_path / "state.json").read_bytes() == before_state
    assert s3.active("L0-T", None, True).bundle.vector_count == material[3].vector_count
    assert s3.state.minimum_rights_epoch == 1


def test_epoch_survives_restore_of_old_state_file(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)
    old_state = (tmp_path / "state.json").read_bytes()
    s.install(signed(material, material[4], "2", 5), material[4].to_bytes(), None, True)
    (tmp_path / "state.json").write_bytes(old_state)          # backup restore of an old copy
    s2 = PackStore(tmp_path, rights(material))
    assert s2.state.minimum_rights_epoch == 5                  # epoch marker wins
    with pytest.raises(PackRejected, match="epoch rollback"):
        s2.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)


def test_compatible_rollback_cannot_lower_epoch(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[4], "2", 3), material[4].to_bytes(), None, True)
    s.install(signed(material, material[3], "1b", 3), material[3].to_bytes(), None, True)  # older content, same epoch
    assert s.state.minimum_rights_epoch == 3


def test_corrupt_state_fails_closed(tmp_path, material):
    PackStore(tmp_path, rights(material))
    (tmp_path / "state.json").write_text("{not json")
    with pytest.raises(StoreError):
        PackStore(tmp_path, rights(material))


def test_tampered_active_pack_is_rejected_on_load(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)
    p = tmp_path / "active" / "L0-T" / "payload.pack"
    b = bytearray(p.read_bytes()); b[-1] ^= 1; p.write_bytes(bytes(b))
    with pytest.raises(PackRejected, match="hash"):
        s.active("L0-T", None, True)


def test_staging_cap_checked_before_writing(tmp_path, material):
    s = PackStore(tmp_path, rights(material), staging_cap_bytes=100)
    with pytest.raises(PackRejected, match="staging cap"):
        s.install(signed(material, material[3], "1", 1), material[3].to_bytes(), None, True)
    assert not any((tmp_path / "staging").iterdir())


def test_leftover_staging_is_cleaned_on_start(tmp_path, material):
    PackStore(tmp_path, rights(material))
    (tmp_path / "staging" / "L0-T.dead").mkdir()
    PackStore(tmp_path, rights(material))
    assert not any((tmp_path / "staging").iterdir())


# ----------------------------------------------------------------- RIGHTS-04 lab lease


def test_lab_lease_valid_then_expired():
    t0 = TrustedTime("boot-A", 1_000, True)
    lease = LabLease.grant("L0-T", 60_000, t0)
    assert lease.status(replace(t0, monotonic_ms=30_000)) == "VALID"
    assert lease.status(replace(t0, monotonic_ms=61_000)) == "EXPIRED"


@pytest.mark.parametrize("t", [
    TrustedTime("boot-B", 2_000, True),      # reboot / reset / restore to another boot session
    TrustedTime("boot-A", 500, True),        # monotonic went backwards
    TrustedTime("boot-A", 2_000, False),     # wall clock untrusted (airplane mode + manual clock)
])
def test_lab_lease_requires_revalidation_through_untrusted_time(t):
    lease = LabLease.grant("L0-T", 60_000, TrustedTime("boot-A", 1_000, True))
    assert lease.status(t) == "REVALIDATE"


def test_lease_cannot_be_granted_on_untrusted_time():
    with pytest.raises(PackRejected):
        LabLease.grant("L0-T", 60_000, TrustedTime("boot-A", 1, False))
