"""IDX-01 (interrupted / disk-full / activation), RIGHTS-02 (epoch and version floors survive a
restored state file), RIGHTS-04 analogue (lab lease), and restart recovery after *abrupt*
process termination (child process killed with os._exit before each I/O step)."""
import json
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dac_l0.index.builder import build_index
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.pack.loader import DeviceRightsState, PackRejected
from dac_l0.pack.manifest import build_manifest, generate_dev_key, load_private, load_public, sign_manifest
from dac_l0.pack.store import Io, LabLease, PackStore, StoreError, TrustedTime
from dac_l0.synth.generator import Edition, EditionKind, gallery_works

L0 = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    d = tmp_path_factory.mktemp("k")
    kid, priv, pub = generate_dev_key(d)
    b1 = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(2)], DescriptorFamily.HASH64)
    b2 = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(3)], DescriptorFamily.HASH64)
    return kid, load_private(priv), load_public(pub), b1, b2, priv


def signed(m, bundle, version, epoch, minimum="0.1.0"):
    kid, priv = m[0], m[1]
    return json.dumps(sign_manifest(build_manifest(bundle, "L0-T", version, kid, rights_epoch=epoch,
                                                   minimum_allowed_version=minimum), priv)).encode()


def rights(m):
    r = DeviceRightsState()
    r.trusted_keys[m[0]] = m[2]
    return r


def slots(root):
    return sorted(p.name for p in (root / "packs" / "L0-T").iterdir()) if (root / "packs" / "L0-T").exists() else []


def test_install_activates_and_reloads_after_restart(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    s2 = PackStore(tmp_path, rights(material))
    assert s2.active("L0-T", now(), True).bundle.vector_count == material[3].vector_count
    assert s2.state.active_versions["L0-T"] == "1.0.0"
    assert not any((tmp_path / "staging").iterdir())
    assert len(slots(tmp_path)) == 1


@pytest.mark.parametrize("fail_on", ["payload", "manifest", "activate", "state", "floors"])
def test_io_failure_at_each_step_keeps_a_consistent_store(tmp_path, material, fail_on):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    real = Io()

    def write_bytes(p, b):
        if (fail_on == "payload" and p.name == "payload.pack") or (fail_on == "manifest" and p.name == "manifest.json") \
                or (fail_on == "state" and p.name == "state.json.tmp") or (fail_on == "floors" and p.name == "floors.json.tmp"):
            raise OSError(28, "No space left on device")
        real.write_bytes(p, b)

    def rep(a, b):
        if fail_on == "activate" and a.parent.name == "staging":
            raise OSError("interrupted")
        real.replace(a, b)

    s.io = Io(write_bytes=write_bytes, replace=rep, rmtree=real.rmtree, mkdir=real.mkdir)
    with pytest.raises(OSError):
        s.install(signed(material, material[4], "2.0.0", 2), material[4].to_bytes(), now(), True)
    s3 = PackStore(tmp_path, rights(material))
    expected = material[4] if fail_on == "floors" else material[3]   # floors fail happens after the commit
    assert s3.active("L0-T", now(), True).bundle.vector_count == expected.vector_count
    assert len(slots(tmp_path)) == 1
    assert not any((tmp_path / "staging").iterdir())


CHILD = textwrap.dedent('''
    import json, os, sys
    from datetime import datetime, timezone
    from pathlib import Path
    sys.path.insert(0, sys.argv[4])
    from dac_l0.index.builder import build_index
    from dac_l0.index.descriptors import DescriptorFamily
    from dac_l0.pack.loader import DeviceRightsState
    from dac_l0.pack.manifest import build_manifest, load_private, load_public, sign_manifest
    from dac_l0.pack.store import Io, PackStore
    from dac_l0.synth.generator import Edition, EditionKind, gallery_works
    root, keydir, kill_at = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    priv_path = next(keydir.glob("*.dev.private.pem")); pub_path = next(keydir.glob("*.public.pem"))
    kid = pub_path.name.split(".")[0]
    r = DeviceRightsState(); r.trusted_keys[kid] = load_public(pub_path)
    b2 = build_index([Edition(w, EditionKind.THEATRICAL) for w in gallery_works(3)], DescriptorFamily.HASH64)
    m = json.dumps(sign_manifest(build_manifest(b2, "L0-T", "2.0.0", kid, rights_epoch=2), load_private(priv_path))).encode()
    real = Io(); n = [0]
    def step(fn):
        def w(*a):
            if n[0] == kill_at:
                os._exit(9)          # abrupt termination: no finally, no handlers, no flush
            n[0] += 1
            return fn(*a)
        return w
    s = PackStore(root, r)
    s.io = Io(write_bytes=step(real.write_bytes), replace=step(real.replace), rmtree=step(real.rmtree), mkdir=step(real.mkdir))
    s.install(m, b2.to_bytes(), datetime.now(timezone.utc), True)
    print("COMPLETED", n[0])
''')


def test_abrupt_termination_at_every_io_step_recovers(tmp_path, material):
    keydir = tmp_path / "keys"
    kid, priv_path, pub_path = generate_dev_key(keydir)
    pub = load_public(pub_path)
    priv = load_private(priv_path)
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    outcomes = []
    k = 0
    while True:
        root = tmp_path / f"store{k}"
        r = DeviceRightsState(); r.trusted_keys[kid] = pub
        s = PackStore(root, r)
        s.install(json.dumps(sign_manifest(build_manifest(material[3], "L0-T", "1.0.0", kid, rights_epoch=1), priv)).encode(),
                  material[3].to_bytes(), now(), True)
        p = subprocess.run([sys.executable, str(script), str(root), str(keydir), str(k), str(L0)],
                           capture_output=True, text=True, timeout=300)
        completed = "COMPLETED" in p.stdout
        if not completed:
            assert p.returncode == 9, (k, p.returncode, p.stderr[-500:])
        r2 = DeviceRightsState(); r2.trusted_keys[kid] = pub
        s2 = PackStore(root, r2)                                   # restart + recovery
        version = s2.state.active_versions["L0-T"]
        assert version in ("1.0.0", "2.0.0"), (k, version)
        lp = s2.active("L0-T", now(), True)                        # referenced slot fully valid
        assert lp.manifest["pack_version"] == version
        assert len(slots(root)) == 1, (k, slots(root))
        assert not any((root / "staging").iterdir())
        assert not (root / "state.json.tmp").exists() and not (root / "floors.json.tmp").exists()
        if version == "2.0.0":
            assert s2.state.minimum_rights_epoch == 2
        outcomes.append((k, version))
        if completed:
            break
        k += 1
    kill_points = len(outcomes) - 1
    assert kill_points >= 7, outcomes                               # every I/O step was interrupted once
    assert {v for _, v in outcomes} == {"1.0.0", "2.0.0"}            # both sides of the commit point seen


def test_epoch_and_version_floor_survive_restore_of_old_state_file(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    old_state = (tmp_path / "state.json").read_bytes()
    s.install(signed(material, material[4], "2.0.0", 5, minimum="2.0.0"), material[4].to_bytes(), now(), True)
    (tmp_path / "state.json").write_bytes(old_state)          # backup restore of an old copy
    with pytest.raises(StoreError, match="missing slot"):
        PackStore(tmp_path, rights(material))                  # old state names a slot that was removed: fail closed


def test_floors_beat_an_older_state_that_still_matches_files(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[4], "2.0.0", 5, minimum="2.0.0"), material[4].to_bytes(), now(), True)
    st = json.loads((tmp_path / "state.json").read_text())
    st["minimum_rights_epoch"] = 0
    st["minimum_pack_versions"] = {}
    (tmp_path / "state.json").write_text(json.dumps(st))      # tampered/older state, same slot
    s2 = PackStore(tmp_path, rights(material))
    assert s2.state.minimum_rights_epoch == 5
    assert s2.rights.minimum_pack_versions["L0-T"] == (2, 0, 0)
    with pytest.raises(PackRejected, match="epoch rollback"):
        s2.install(signed(material, material[3], "2.1.0", 1), material[3].to_bytes(), now(), True)
    with pytest.raises(PackRejected, match="rollback"):
        s2.install(signed(material, material[3], "1.0.0", 9), material[3].to_bytes(), now(), True)


def test_compatible_rollback_cannot_lower_epoch(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[4], "2.0.0", 3), material[4].to_bytes(), now(), True)
    s.install(signed(material, material[3], "1.1.0", 3), material[3].to_bytes(), now(), True)  # older content, allowed floor
    assert s.state.minimum_rights_epoch == 3


def test_corrupt_state_fails_closed(tmp_path, material):
    PackStore(tmp_path, rights(material))
    (tmp_path / "state.json").write_text("{not json")
    with pytest.raises(StoreError):
        PackStore(tmp_path, rights(material))


def test_tampered_active_pack_is_rejected_on_load(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    p = tmp_path / "packs" / "L0-T" / slots(tmp_path)[0] / "payload.pack"
    b = bytearray(p.read_bytes()); b[-1] ^= 1; p.write_bytes(bytes(b))
    with pytest.raises(PackRejected, match="hash"):
        s.active("L0-T", now(), True)


def test_staging_cap_checked_before_writing(tmp_path, material):
    s = PackStore(tmp_path, rights(material), staging_cap_bytes=100)
    with pytest.raises(PackRejected, match="staging cap"):
        s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    assert not any((tmp_path / "staging").iterdir())


def test_leftovers_are_cleaned_on_start(tmp_path, material):
    s = PackStore(tmp_path, rights(material))
    s.install(signed(material, material[3], "1.0.0", 1), material[3].to_bytes(), now(), True)
    (tmp_path / "staging" / "L0-T.dead").mkdir()
    (tmp_path / "packs" / "L0-T" / "0123456789abcdef").mkdir()
    (tmp_path / "state.json.tmp").write_text("partial")
    s2 = PackStore(tmp_path, rights(material))
    assert not any((tmp_path / "staging").iterdir())
    assert len(slots(tmp_path)) == 1 and not (tmp_path / "state.json.tmp").exists()
    assert len(s2.recovery_actions) == 3


# ----------------------------------------------------------------- RIGHTS-04 lab lease


def test_lab_lease_valid_then_expired():
    t0 = TrustedTime("boot-A", 1_000, True)
    lease = LabLease.grant("L0-T", 60_000, t0)
    assert lease.status(replace(t0, monotonic_ms=30_000)) == "VALID"
    assert lease.status(replace(t0, monotonic_ms=61_000)) == "EXPIRED"


@pytest.mark.parametrize("t", [
    TrustedTime("boot-B", 2_000, True),
    TrustedTime("boot-A", 500, True),
    TrustedTime("boot-A", 2_000, False),
])
def test_lab_lease_requires_revalidation_through_untrusted_time(t):
    lease = LabLease.grant("L0-T", 60_000, TrustedTime("boot-A", 1_000, True))
    assert lease.status(t) == "REVALIDATE"


def test_lease_cannot_be_granted_on_untrusted_time():
    with pytest.raises(PackRejected):
        LabLease.grant("L0-T", 60_000, TrustedTime("boot-A", 1, False))
