"""P04-T02c / IDX-01: reference sampling interval study on the DEV family only.

Compares 1 s, 2 s and 5 s reference sampling for one descriptor using the frozen calibration
thresholds (calibrated at 2 s; other intervals are therefore *not* re-calibrated, which is
part of what the study shows). DEV is a seen family: this is method exploration, not an
estimate of held-out performance.

  python -m dac_l0.eval.sampling_study --family HASH64
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..index.descriptors import DescriptorFamily
from ..synth.fixtures import make_queries
from .calibrate import load_frozen
from .run_lab import build_gallery, extract_family, score_family

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="HASH64")
    ap.add_argument("--intervals", default="1.0,2.0,5.0")
    a = ap.parse_args(argv)
    desc = DescriptorFamily(a.family)
    th = load_frozen(ROOT / "evidence" / "calibration" / f"calibration_{desc.value}.json")
    cache = ROOT / ".cache"
    cases = make_queries("DEV")
    rows = []
    for si in [float(x) for x in a.intervals.split(",")]:
        bundle, _ = build_gallery(desc, cache, si)
        ev = extract_family("DEV", desc, th, cache, sampling_interval_s=si)
        fs = score_family(ev, cases, bundle, th, with_intervals=False)
        k = fs.by_kind
        rows.append({
            "sampling_interval_s": si, "vectors": bundle.vector_count, "payload_bytes": bundle.payload_bytes,
            "bytes_per_reference_hour": round(bundle.bytes_per_reference_hour()),
            "clean_correct": sum(v for c, v in k.get("CLEAN", {}).items() if c.startswith("CORRECT")),
            "edited_correct": sum(v for c, v in k.get("EDITED", {}).items() if c.startswith("CORRECT")),
            "absent_false_any": sum(v for c, v in k.get("ABSENT", {}).items() if c.startswith("FALSE")),
            "wrong_title_verified": fs.wrong_title_verified, "wrong_title_possible": fs.wrong_title_possible,
            "recognition_p50_ms": round(fs.latency_ms_p50),
            "n_clean": sum(k.get("CLEAN", {}).values()), "n_edited": sum(k.get("EDITED", {}).values()),
            "n_absent": sum(k.get("ABSENT", {}).values()),
        })
    out = {"study": "P04-T02c sampling interval", "family": "DEV (seen; exploration only)", "descriptor": desc.value,
           "thresholds_digest": th.digest(), "run_at": datetime.now(timezone.utc).isoformat(), "rows": rows}
    d = ROOT / "evidence" / "studies"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"sampling_{desc.value}.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r in rows:
        print(r)
    print(f"→ {p}")


if __name__ == "__main__":
    main()
