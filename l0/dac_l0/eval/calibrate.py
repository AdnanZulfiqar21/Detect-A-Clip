"""Threshold calibration on the CALIBRATION family only (P04-T05).

Preregistered selection rule (written before any CALIBRATION outcome was computed):
 1. Hard constraints on CALIBRATION: zero wrong-title VERIFIED results of any kind
    (incl. FALSE_VERIFIED, wrong episode, unsupported specificity, overconfident shared
    footage and montage VERIFIED).
 2. Among feasible settings, minimise wrong-title POSSIBLE results (a wrong title shown as
    uncertain is still an error, OF-01).
 3. Then maximise correct named results on CLEAN + EDITED + SERIES_UNIQUE + TRAILER + OVERLAY.
 4. Then maximise CORRECT_VERIFIED on the same kinds.
 5. Ties: the most conservative setting (larger verified_min_support, span, margin;
    smaller distance fractions) in a fixed grid order.
If no setting is feasible the result is reported as INFEASIBLE and nothing is frozen.

Output: a frozen calibration JSON (thresholds, digest, fixture manifest hash, evidence
digest, grid, selection trace). `calibration_status` becomes CALIBRATED_L0_SYNTHETIC, a
LAB-only status that the pack loader's release mode still rejects.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..decision import DecisionThresholds
from ..index.descriptors import DescriptorFamily
from ..synth.fixtures import fixture_manifest, make_queries
from .run_lab import build_gallery, extract_family, score_family

# Grid revised once after the DEV v3.1 run (montage half-coverage VERIFIED) and before any
# CALIBRATION outcome: verified_min_support_fraction added; two distance axes thinned.
GRID = {
    "verified_min_support": [5, 6, 7, 8],
    "verified_min_support_fraction": [0.5, 0.6, 0.7],
    "verified_min_span_ms": [2000, 3000, 4000],
    "verified_max_mean_dist_frac": [0.6, 0.8],
    "verified_min_margin": [2, 3, 4],
    "possible_min_support": [3, 4, 5],
    "possible_min_span_ms": [1000, 1500, 2500],
    "possible_max_mean_dist_frac": [0.6, 0.9],
    "possible_on_competition": [False, True],
}
OBJECTIVE_KINDS = ("CLEAN", "EDITED", "SERIES_UNIQUE", "TRAILER", "OVERLAY")


def _conservatism(th: DecisionThresholds) -> Tuple:
    return (th.verified_min_support, th.verified_min_support_fraction, th.verified_min_span_ms, th.verified_min_margin, -th.verified_max_mean_dist_frac,
            th.possible_min_support, th.possible_min_span_ms, -th.possible_max_mean_dist_frac, not th.possible_on_competition)


def calibrate(desc: DescriptorFamily, base: DecisionThresholds, cache_dir: Path, out_dir: Path) -> Dict:
    assert base.radius(desc) > 0
    ev = extract_family("CALIBRATION", desc, base, cache_dir)
    cases = make_queries("CALIBRATION")
    bundle, _ = build_gallery(desc, cache_dir)
    keys = list(GRID)
    best = None
    feasible = 0
    trace: List[Dict] = []
    for values in itertools.product(*(GRID[k] for k in keys)):
        th = replace(base, **dict(zip(keys, values)))
        if th.possible_min_support > th.verified_min_support:
            continue
        fs = score_family(ev, cases, bundle, th, with_intervals=False)
        if fs.wrong_title_verified > 0:
            continue
        feasible += 1
        named = sum(n for k in OBJECTIVE_KINDS for c, n in fs.by_kind.get(k, {}).items() if c.startswith("CORRECT"))
        verified = sum(fs.by_kind.get(k, {}).get("CORRECT_VERIFIED", 0) for k in OBJECTIVE_KINDS)
        key = (fs.wrong_title_possible, -named, -verified, tuple(-x if isinstance(x, (int, float)) else x for x in _conservatism(th)))
        if best is None or key < best[0]:
            best = (key, th, fs, named, verified)
    now = datetime.now(timezone.utc)
    out: Dict = {
        "calibration_type": "L0_SYNTHETIC_CALIBRATION",
        "descriptor": desc.value,
        "created_at": now.isoformat(),
        "family_used": "CALIBRATION",
        "fixture_manifest_sha256": fixture_manifest()["sha256"],
        "evidence_digest": ev.retrieval_digest,
        "grid": GRID,
        "selection_rule": __doc__,
        "feasible_settings": feasible,
    }
    if best is None:
        out["status"] = "INFEASIBLE"
    else:
        _, th, fs, named, verified = best
        frozen = replace(th, calibration_version=f"l0cal-{desc.value}-{now.strftime('%Y%m%d')}", calibration_status="CALIBRATED_L0_SYNTHETIC")
        out.update({
            "status": "FROZEN",
            "thresholds": asdict(frozen),
            "thresholds_digest": frozen.digest(),
            "calibration_outcomes": {"by_kind": fs.by_kind, "wrong_title_verified": fs.wrong_title_verified,
                                     "wrong_title_possible": fs.wrong_title_possible, "correct_named_objective": named,
                                     "correct_verified_objective": verified, "errors": fs.errors},
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"calibration_{desc.value}.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    out["path"] = str(p)
    return out


def load_frozen(path: Path) -> DecisionThresholds:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("status") != "FROZEN":
        raise ValueError("calibration file is not FROZEN")
    th = DecisionThresholds(**d["thresholds"])
    if th.digest() != d["thresholds_digest"]:
        raise ValueError("calibration thresholds digest mismatch")
    if d["fixture_manifest_sha256"] != fixture_manifest()["sha256"]:
        raise ValueError("calibration was made on a different fixture manifest")
    return th
