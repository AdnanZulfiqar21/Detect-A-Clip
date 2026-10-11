"""The committed cross-language manifest V2 cases must still get the same verdicts from the
current Python loader (the Kotlin PackLoader is checked against the same file). The cases are
not regenerated here because their signing key was random and its private half was discarded."""
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from dac_l0.pack.loader import DeviceRightsState, PackRejected, load_pack, parse_version

FILE = Path(__file__).resolve().parents[2] / "android" / "app" / "src" / "test" / "resources" / "golden_manifest_cases.txt"


def test_committed_manifest_cases_match_python_loader():
    pub_line = None
    payloads = {}
    cases = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("PUBKEY "):
            pub_line = line.split()
        elif line.startswith("PAYLOAD "):
            _, name, hx = line.split()
            payloads[name] = bytes.fromhex(hx)
        elif line.startswith("CASE "):
            cases.append(line.split())
    key_id, pub = pub_line[1], Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_line[2]))
    assert len(cases) >= 50
    mismatches = []
    for c in cases:
        name, expect = c[1], c[2] == "ACCEPT"
        kv = dict(x.split("=", 1) for x in c[3:])
        st = DeviceRightsState(minimum_rights_epoch=int(kv["epoch"]))
        st.trusted_keys[key_id] = pub
        if kv["revoked"] == "1":
            st.revoked_key_ids.add(key_id)
        if kv["floors"] != "-":
            for item in kv["floors"].split(","):
                pid, v = item.split(":")
                st.minimum_pack_versions[pid] = parse_version(v, "floor")
        now = None if kv["now"] == "UNTRUSTED" else kv["now"]
        try:
            load_pack(bytes.fromhex(kv["manifest"]), payloads[kv["payload"]], st, now, now is not None,
                      kv["release"] == "1", signature=bytes.fromhex(kv["sig"]))
            got = True
        except PackRejected:
            got = False
        if got != expect:
            mismatches.append(name)
    assert mismatches == []
