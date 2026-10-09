"""Command-line entry points for the desktop L0 track.

  python -m dac_l0.cli manifest            # write ASSET_MANIFEST.json / RIGHTS_MANIFEST.json
  python -m dac_l0.cli build  --family HASH64 --out packs/
  python -m dac_l0.cli keygen --out keys/
  python -m dac_l0.cli sign   --pack packs/L0-SYNTH-001.pack --key keys/<id>.dev.private.pem
  python -m dac_l0.cli verify --manifest packs/L0-SYNTH-001.manifest.json --pack ... --pub keys/<id>.public.pem
  python -m dac_l0.cli fixtures                     # frozen fixtures-v3 manifest
  python -m dac_l0.cli lab --families DEV,CALIBRATION --label dev
  python -m dac_l0.cli calibrate                    # CALIBRATION family only → evidence/calibration/
  python -m dac_l0.cli lab --calibrated --families FINAL --i-understand-final-is-sealed --label final
  python -m dac_l0.cli preview --asset SW000-E0_THEATRICAL --out assets/generated/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cmd_manifest(a):
    from .synth.manifest import write_manifests

    p = write_manifests(Path(a.out))
    m = json.loads(p.read_text(encoding="utf-8"))
    print(f"wrote {p} ({m['counts']['total_assets']} assets, sha256 {m['manifest_sha256'][:16]}…)")


def cmd_build(a):
    from .index.builder import build_index
    from .index.descriptors import DescriptorFamily
    from .synth.generator import Edition, EditionKind, gallery_works

    fam = DescriptorFamily(a.family)
    eds = [Edition(w, k) for w in gallery_works(a.works) for k in EditionKind]
    b = build_index(eds, fam, a.interval)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{a.pack_id}.pack"
    path.write_bytes(b.to_bytes())
    print(json.dumps({"pack": str(path), **b.stats, "indexed_hours": b.indexed_hours, "title_count": b.title_count}, indent=1))


def cmd_keygen(a):
    from .pack.manifest import generate_dev_key

    key_id, priv, pub = generate_dev_key(Path(a.out))
    print(f"DEVELOPMENT_ONLY key {key_id}\n private: {priv} (git-ignored)\n public : {pub}")


def cmd_sign(a):
    from .index.builder import IndexBundle
    from .pack.manifest import build_manifest, load_private, sign_manifest

    payload = Path(a.pack).read_bytes()
    b = IndexBundle.from_bytes(payload)
    priv = load_private(Path(a.key))
    key_id = Path(a.key).name.split(".")[0]
    m = build_manifest(b, a.pack_id, a.version, key_id)
    signed = sign_manifest(m, priv)
    mp = Path(a.pack).with_suffix(".manifest.json")
    mp.write_text(json.dumps(signed, indent=1, sort_keys=True), encoding="utf-8")
    print(f"signed manifest → {mp} (calibration_status={signed['calibration_status']})")


def cmd_verify(a):
    from .pack.loader import DeviceRightsState, PackRejected, load_pack
    from .pack.manifest import load_public

    state = DeviceRightsState()
    key_id = Path(a.pub).name.split(".")[0]
    state.trusted_keys[key_id] = load_public(Path(a.pub))
    try:
        lp = load_pack(Path(a.manifest).read_bytes(), Path(a.pack).read_bytes(), state, now_iso=None, time_trustworthy=True, release_mode=a.release)
        print(f"ACCEPTED {lp.manifest['pack_id']} v{lp.manifest['pack_version']}: {lp.bundle.vector_count} vectors, {lp.bundle.title_count} titles, {lp.manifest['calibration_status']}")
    except PackRejected as e:
        print(f"REJECTED: {e.reason}")
        sys.exit(2)


def _descs(a):
    from .index.descriptors import DescriptorFamily

    return [DescriptorFamily(f) for f in a.family] if a.family else list(DescriptorFamily)


def cmd_lab(a):
    """DEV / CALIBRATION runs with the development thresholds or a frozen calibration file."""
    from .decision import DecisionThresholds
    from .eval.calibrate import load_frozen
    from .eval.run_lab import run

    for d in _descs(a):
        th = load_frozen(Path(a.calibration_dir) / f"calibration_{d.value}.json") if a.calibrated else DecisionThresholds()
        fams = a.families.split(",")
        if "FINAL" in fams and not a.i_understand_final_is_sealed:
            raise SystemExit("FINAL is sealed; pass --i-understand-final-is-sealed for the single preregistered run")
        p = run(Path(a.out), fams, [d], th, Path(a.cache), f"{a.label}_{d.value}",
                calibration_file=str(Path(a.calibration_dir) / f"calibration_{d.value}.json") if a.calibrated else None)
        print(f"report → {p}")


def cmd_calibrate(a):
    from .decision import DecisionThresholds
    from .eval.calibrate import calibrate

    for d in _descs(a):
        out = calibrate(d, DecisionThresholds(), Path(a.cache), Path(a.out))
        print(d.value, out["status"], out.get("feasible_settings"), out.get("thresholds_digest", "")[:16], out["path"])


def cmd_fixtures(a):
    from .synth.fixtures import fixture_manifest

    m = fixture_manifest()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(m, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(f"fixtures {m['fixture_version']} sha256 {m['sha256'][:16]} → {a.out}")


def cmd_preview(a):
    """Render one asset to an MP4 so a human witness can look at it (git-ignored output)."""
    import cv2

    from .synth.generator import Edition, EditionKind, NATIVE_FPS, SynthWork, gallery_works

    wid, eid = a.asset.split("-", 1)
    w = next(x for x in gallery_works(1000) if x.work_id == wid)
    ed = Edition(w, EditionKind(eid))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{ed.asset_id}.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), NATIVE_FPS, (640, 360))
    n = int(ed.duration_s * NATIVE_FPS)
    for i in range(n):
        vw.write(ed.render_frame(i / NATIVE_FPS))
    vw.release()
    print(f"wrote {path} ({n} frames)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dac_l0")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("manifest"); p.add_argument("--out", default=str(ROOT / "assets")); p.add_argument("--works", type=int, default=20); p.add_argument("--absent", type=int, default=10); p.set_defaults(fn=cmd_manifest)
    p = sp.add_parser("build"); p.add_argument("--family", default="HASH64"); p.add_argument("--interval", type=float, default=2.0); p.add_argument("--works", type=int, default=20); p.add_argument("--out", default=str(ROOT / "packs")); p.add_argument("--pack-id", default="L0-SYNTH-001"); p.set_defaults(fn=cmd_build)
    p = sp.add_parser("keygen"); p.add_argument("--out", default=str(ROOT / "keys")); p.set_defaults(fn=cmd_keygen)
    p = sp.add_parser("sign"); p.add_argument("--pack", required=True); p.add_argument("--key", required=True); p.add_argument("--pack-id", default="L0-SYNTH-001"); p.add_argument("--version", default="0.1.0"); p.set_defaults(fn=cmd_sign)
    p = sp.add_parser("verify"); p.add_argument("--manifest", required=True); p.add_argument("--pack", required=True); p.add_argument("--pub", required=True); p.add_argument("--release", action="store_true"); p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("lab"); p.add_argument("--out", default=str(ROOT / "evidence" / "lab")); p.add_argument("--families", default="DEV,CALIBRATION"); p.add_argument("--family", action="append"); p.add_argument("--cache", default=str(ROOT / ".cache")); p.add_argument("--calibrated", action="store_true"); p.add_argument("--calibration-dir", default=str(ROOT / "evidence" / "calibration")); p.add_argument("--label", default="run"); p.add_argument("--i-understand-final-is-sealed", action="store_true"); p.set_defaults(fn=cmd_lab)
    p = sp.add_parser("calibrate"); p.add_argument("--family", action="append"); p.add_argument("--cache", default=str(ROOT / ".cache")); p.add_argument("--out", default=str(ROOT / "evidence" / "calibration")); p.set_defaults(fn=cmd_calibrate)
    p = sp.add_parser("fixtures"); p.add_argument("--out", default=str(ROOT / "assets" / "FIXTURES_v3.json")); p.set_defaults(fn=cmd_fixtures)
    p = sp.add_parser("preview"); p.add_argument("--asset", default="SW000-E0_THEATRICAL"); p.add_argument("--out", default=str(ROOT / "assets" / "generated")); p.set_defaults(fn=cmd_preview)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
