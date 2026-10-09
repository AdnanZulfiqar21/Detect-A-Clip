"""LAB evaluation on frozen fixtures-v3 (P04-T02/T03/T05/T06, AI-01/02/03/05/07 exploratory).

Two stages:
 1. `extract_family()` renders each query through the simulated capture channel and runs
    selection → quality → description → retrieval → temporal verification, in parallel.
    Evidence (hypotheses + frame summary) is cached per (descriptor family, fixture family).
 2. `score_family()` applies a DecisionThresholds to the cached evidence and scores every
    query with the preregistered rules in SCORING_RULES. Calibration (calibrate.py) reuses
    stage 1 and repeats stage 2 over a grid, on the CALIBRATION family only.

Purpose is always LAB. Synthetic results never establish device, rights, coverage or
release evidence.
"""
from __future__ import annotations

import json
import os
import pickle
import platform
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import GENERATOR_VERSION, INDEX_FORMAT_VERSION, PREPROCESSING_VERSION, __version__
from ..decision import DecisionThresholds, FrameSummary, decide
from ..index.builder import IndexBundle, build_index, duplicate_descriptor_ratio
from ..index.descriptors import DescriptorFamily
from ..index.retrieval import FlatRetriever
from ..pipeline import Delivered, extract_evidence
from ..schemas import RecognitionResult, ResultState
from ..synth.fixtures import FIXTURE_VERSION, QueryCase, all_gallery_editions, fixture_manifest, make_queries
from ..verify import Hypothesis
from .protocol import Metric

DELIVERY_FPS = 10  # simulated OS delivery; the selector reduces to ≤2 fps
MATCH = (ResultState.VERIFIED_MATCH, ResultState.POSSIBLE_MATCH)

SCORING_RULES = """\
fixtures-v3 scoring rules (preregistered 2026-10-09 before any CALIBRATION/FINAL outcome)
Every query yields exactly one outcome category. "named" = candidate_work_id of a
VERIFIED or POSSIBLE result; for episodes candidate_work_id is the series ID and
candidate_episode_id the episode (None = series level).
- CLEAN / EDITED: CORRECT_VERIFIED, CORRECT_POSSIBLE, ABSTAIN, WRONG_VERIFIED, WRONG_POSSIBLE.
- SERIES_UNIQUE: CORRECT_VERIFIED / CORRECT_POSSIBLE (right series and right episode);
  SERIES_LEVEL (right series, no episode: granularity loss, not wrong); ABSTAIN;
  WRONG_EPISODE_VERIFIED / WRONG_EPISODE_POSSIBLE; WRONG_VERIFIED / WRONG_POSSIBLE (outside series).
- SERIES_INTRO (shared intro): CORRECT = series level or ABSTAIN; any named episode is
  UNSUPPORTED_SPECIFICITY_VERIFIED / _POSSIBLE; outside series is WRONG_*.
- SERIES_RECAP (previous episode's footage + 2 s own): CORRECT = series level, own episode,
  or ABSTAIN; another episode VERIFIED = WRONG_EPISODE_VERIFIED; POSSIBLE = WRONG_EPISODE_POSSIBLE.
- STOCK_SHARED (same stock scene in two works): CORRECT = ABSTAIN, or POSSIBLE naming either
  work; VERIFIED naming either work = OVERCONFIDENT_SHARED; outside the pair = WRONG_*.
- MONTAGE (two works): CORRECT_SEGMENTS = POSSIBLE whose segments name both works and nothing
  else; PARTIAL = names a subset; ABSTAIN; OVERCONFIDENT_VERIFIED = VERIFIED; WRONG_* = any
  named work or segment outside the pair.
- TRAILER (rapid cuts of one work): CORRECT_* names it; ABSTAIN; WRONG_* other work.
- ABSENT: ABSTAIN; FALSE_VERIFIED; FALSE_POSSIBLE (a wrong title shown as uncertain). Both
  are errors and are reported separately; FALSE_POSSIBLE is never merged into ABSTAIN.
- UNUSABLE: EXPECTED_STATE if the state is in the case's acceptable list, else UNEXPECTED_STATE
  (WRONG_* if a title is named).
- OVERLAY (overlay over the underlying video): CORRECT_* names the video's work; ABSTAIN;
  WRONG_* names another work.
Safety totals: WRONG_TITLE_VERIFIED = every *_VERIFIED error category; WRONG_TITLE_POSSIBLE =
every *_POSSIBLE error category (incl. FALSE_POSSIBLE).
"""

ERROR_VERIFIED = {"WRONG_VERIFIED", "WRONG_EPISODE_VERIFIED", "UNSUPPORTED_SPECIFICITY_VERIFIED",
                  "OVERCONFIDENT_SHARED", "OVERCONFIDENT_VERIFIED", "FALSE_VERIFIED"}
ERROR_POSSIBLE = {"WRONG_POSSIBLE", "WRONG_EPISODE_POSSIBLE", "UNSUPPORTED_SPECIFICITY_POSSIBLE", "FALSE_POSSIBLE"}


def score(case: QueryCase, r: RecognitionResult) -> str:
    st = r.state
    named = r.candidate_work_id if st in MATCH else None
    ver = st == ResultState.VERIFIED_MATCH
    sfx = "VERIFIED" if ver else "POSSIBLE"
    k = case.kind
    if k == "UNUSABLE":
        if named:
            return f"WRONG_{sfx}"
        return "EXPECTED_STATE" if st.value in case.acceptable else "UNEXPECTED_STATE"
    if named is None:
        return "ABSTAIN"
    if k == "ABSENT":
        return f"FALSE_{sfx}"
    if k in ("CLEAN", "EDITED", "TRAILER", "OVERLAY"):
        return f"CORRECT_{sfx}" if named == case.true_work else f"WRONG_{sfx}"
    if k in ("SERIES_UNIQUE", "SERIES_INTRO", "SERIES_RECAP"):
        if named != case.true_work:
            return f"WRONG_{sfx}"
        ep = r.candidate_episode_id
        if k == "SERIES_UNIQUE":
            if ep is None:
                return "SERIES_LEVEL"
            return f"CORRECT_{sfx}" if ep == case.true_episode else f"WRONG_EPISODE_{sfx}"
        if k == "SERIES_INTRO":
            return "CORRECT_SERIES_LEVEL" if ep is None else f"UNSUPPORTED_SPECIFICITY_{sfx}"
        return f"CORRECT_{sfx}" if ep in (None, case.true_episode) else f"WRONG_EPISODE_{sfx}"
    if k == "STOCK_SHARED":
        if named not in case.acceptable:
            return f"WRONG_{sfx}"
        return "OVERCONFIDENT_SHARED" if ver else "CORRECT_POSSIBLE"
    if k == "MONTAGE":
        seg_works = {s.work_id for s in r.segments} | {named}
        if not seg_works <= set(case.acceptable):
            return f"WRONG_{sfx}"
        if ver:
            return "OVERCONFIDENT_VERIFIED"
        return "CORRECT_SEGMENTS" if seg_works == set(case.acceptable) else "PARTIAL"
    raise ValueError(k)


# --------------------------------------------------------------------------- stage 1

_W: Dict = {}


def _worker_init(bundle_path: str, family: str, th: DecisionThresholds) -> None:
    b = IndexBundle.from_bytes(Path(bundle_path).read_bytes(), max_payload_bytes=1 << 31)
    _W["retr"] = FlatRetriever(b)
    _W["cases"] = make_queries(family)
    _W["th"] = th


def _deliveries(case: QueryCase):
    n = int(case.length_s * DELIVERY_FPS)
    for i in range(n):
        yield Delivered(int(i * 1000 / DELIVERY_FPS), case.render(i / DELIVERY_FPS))


def _extract_one(i: int):
    case = _W["cases"][i]
    t0 = time.perf_counter()
    hyps, summ, _ = extract_evidence(_deliveries(case), _W["retr"], _W["th"])
    return i, hyps, summ, (time.perf_counter() - t0) * 1000


@dataclass
class Evidence:
    family: str
    descriptor: str
    hyps: List[List[Hypothesis]]
    summaries: List[FrameSummary]
    latency_ms: List[float]
    retrieval_digest: str


def _retrieval_key(th: DecisionThresholds, d: DescriptorFamily) -> str:
    return f"{d.value}|r={th.radius(d)}|k={th.top_k}|m={th.mirror_invariant}"


def build_gallery(desc: DescriptorFamily, cache_dir: Path, sampling_interval_s: float = 2.0) -> Tuple[IndexBundle, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"gallery_{FIXTURE_VERSION}_{GENERATOR_VERSION}_{PREPROCESSING_VERSION}_{INDEX_FORMAT_VERSION}_{desc.value}_{sampling_interval_s}.idx"
    if p.exists():
        return IndexBundle.from_bytes(p.read_bytes(), max_payload_bytes=1 << 31), p
    b = build_index(all_gallery_editions(), desc, sampling_interval_s)
    p.write_bytes(b.to_bytes())
    return b, p


def extract_family(family: str, desc: DescriptorFamily, th: DecisionThresholds, cache_dir: Path, workers: Optional[int] = None) -> Evidence:
    key = _retrieval_key(th, desc)
    import hashlib
    digest = hashlib.sha256(f"{FIXTURE_VERSION}|{GENERATOR_VERSION}|{PREPROCESSING_VERSION}|{key}".encode()).hexdigest()[:16]
    cp = cache_dir / f"evidence_{family}_{digest}.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    bundle, bpath = build_gallery(desc, cache_dir)
    n = len(make_queries(family))
    hyps: List = [None] * n
    summ: List = [None] * n
    lat: List = [0.0] * n
    with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 2),
                             initializer=_worker_init, initargs=(str(bpath), family, th)) as ex:
        for i, h, s, ms in ex.map(_extract_one, range(n), chunksize=4):
            hyps[i], summ[i], lat[i] = h, s, ms
    ev = Evidence(family, desc.value, hyps, summ, lat, digest)
    cp.write_bytes(pickle.dumps(ev))
    return ev


# --------------------------------------------------------------------------- stage 2


@dataclass
class FamilyScore:
    family: str
    descriptor: str
    thresholds_digest: str
    by_kind: Dict[str, Dict[str, int]] = field(default_factory=dict)
    metrics: List[Dict] = field(default_factory=list)
    wrong_title_verified: int = 0
    wrong_title_possible: int = 0
    errors: List[str] = field(default_factory=list)
    latency_ms_p50: float = 0.0
    latency_ms_p90: float = 0.0


def score_family(ev: Evidence, cases: List[QueryCase], bundle: IndexBundle, th: DecisionThresholds, with_intervals: bool = True) -> FamilyScore:
    fs = FamilyScore(ev.family, ev.descriptor, th.digest())
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    clusters: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
    for i, case in enumerate(cases):
        r = decide(f"lab-{i}", 1, ev.hyps[i], ev.summaries[i], bundle, 0, th)
        cat = score(case, r)
        counts[case.kind][cat] += 1
        if cat in ERROR_VERIFIED:
            fs.wrong_title_verified += 1
        if cat in ERROR_POSSIBLE:
            fs.wrong_title_possible += 1
        if cat in ERROR_VERIFIED or cat in ERROR_POSSIBLE or cat in ("UNEXPECTED_STATE",):
            fs.errors.append(f"{case.kind} {case.label} → {cat} ({r.state.value} {r.candidate_work_id} {r.candidate_episode_id} flags={r.ambiguity_flags})")
        if with_intervals:
            ok_named = int(cat.startswith("CORRECT"))
            clusters[f"{case.kind}:correct_named"][case.cluster].append(ok_named)
            clusters[f"{case.kind}:correct_verified"][case.cluster].append(int(cat == "CORRECT_VERIFIED"))
            clusters[f"{case.kind}:wrong_title_verified"][case.cluster].append(int(cat in ERROR_VERIFIED))
            clusters[f"{case.kind}:wrong_title_possible"][case.cluster].append(int(cat in ERROR_POSSIBLE))
    fs.by_kind = {k: dict(v) for k, v in counts.items()}
    if with_intervals:
        for name, byc in sorted(clusters.items()):
            k = sum(sum(v) for v in byc.values())
            n = sum(len(v) for v in byc.values())
            m = Metric(name, k, n, name).finalize({c: (sum(v), len(v)) for c, v in byc.items()})
            fs.metrics.append(m.to_dict())
    if ev.latency_ms:
        fs.latency_ms_p50 = float(np.percentile(ev.latency_ms, 50))
        fs.latency_ms_p90 = float(np.percentile(ev.latency_ms, 90))
    return fs


def _git_commit() -> str:
    try:
        rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "."], text=True, stderr=subprocess.DEVNULL).strip()
        return rev + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def run(out_dir: Path, families: List[str], descriptors: List[DescriptorFamily], th: DecisionThresholds,
        cache_dir: Path, label: str, calibration_file: Optional[str] = None) -> Path:
    if "FINAL" in families and th.calibration_status != "CALIBRATED_L0_SYNTHETIC":
        raise RuntimeError("FINAL is sealed: run it only with a frozen calibration file")
    now = datetime.now(timezone.utc)
    report = {
        "purpose": "LAB",
        "label": label,
        "claim_boundary": "Synthetic L0 exploratory evidence only. Not device, rights, coverage or release evidence.",
        "run_at": now.isoformat(),
        "host": f"{platform.system()} {platform.release()} {platform.machine()} python {platform.python_version()}",
        "l0_version": __version__,
        "git_commit": _git_commit(),
        "fixture_manifest_sha256": fixture_manifest()["sha256"],
        "generator": GENERATOR_VERSION, "preprocessing": PREPROCESSING_VERSION, "index_format": INDEX_FORMAT_VERSION,
        "thresholds": asdict(th), "thresholds_digest": th.digest(), "calibration_file": calibration_file,
        "scoring_rules": SCORING_RULES,
        "results": [],
    }
    for desc in descriptors:
        bundle, _ = build_gallery(desc, cache_dir)
        idx = {"descriptor": desc.value, "vector_count": bundle.vector_count, "payload_bytes": bundle.payload_bytes,
               "indexed_hours": bundle.indexed_hours, "bytes_per_reference_hour": bundle.bytes_per_reference_hour(),
               "duplicate_ratio": duplicate_descriptor_ratio(bundle), "title_count": bundle.title_count}
        for fam in families:
            ev = extract_family(fam, desc, th, cache_dir)
            fs = score_family(ev, make_queries(fam), bundle, th)
            report["results"].append({"index": idx, **asdict(fs)})
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    jp = out_dir / f"lab_{label}_{stamp}.json"
    jp.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    mp = out_dir / f"lab_{label}_{stamp}.md"
    mp.write_text(render_markdown(report), encoding="utf-8")
    return mp


def render_markdown(rep: Dict) -> str:
    L = [f"# L0 LAB report `{rep['label']}` — {rep['run_at']}", "",
         f"**Purpose:** {rep['purpose']}. {rep['claim_boundary']}", "",
         f"Host {rep['host']} · commit `{rep['git_commit']}` · {rep['generator']} / {rep['preprocessing']} / {rep['index_format']}",
         f"Fixture manifest `{rep['fixture_manifest_sha256'][:16]}` · thresholds `{rep['thresholds_digest'][:16]}` "
         f"({rep['thresholds']['calibration_status']}) · calibration file: {rep['calibration_file'] or 'none'}", ""]
    L += ["## Safety totals and outcome counts", "",
          "| Descriptor | Family | wrong title VERIFIED | wrong title POSSIBLE | p50 ms | p90 ms |", "|---|---|---:|---:|---:|---:|"]
    for r in rep["results"]:
        L.append(f"| {r['descriptor']} | {r['family']} | {r['wrong_title_verified']} | {r['wrong_title_possible']} | {r['latency_ms_p50']:.0f} | {r['latency_ms_p90']:.0f} |")
    for r in rep["results"]:
        L += ["", f"### {r['descriptor']} · {r['family']}", "",
              f"Index: {r['index']['vector_count']} vectors, {r['index']['payload_bytes']:,} B, {r['index']['bytes_per_reference_hour']:,.0f} B per reference hour, {r['index']['title_count']} titles.", "",
              "| Kind | Outcomes |", "|---|---|"]
        for k, v in sorted(r["by_kind"].items()):
            L.append(f"| {k} | " + ", ".join(f"{c}={n}" for c, n in sorted(v.items())) + " |")
        L += ["", "| Metric | k/n | Wilson 95 % | cluster boot 95 % (clusters) |", "|---|---:|---|---|"]
        for m in r["metrics"]:
            if m["name"].endswith("correct_named") or "wrong_title" in m["name"]:
                L.append(f"| {m['name']} | {m['k']}/{m['n']} | [{m['wilson95'][0]:.3f}, {m['wilson95'][1]:.3f}] | [{m['cluster_boot95'][0]:.3f}, {m['cluster_boot95'][1]:.3f}] ({m['n_clusters']}) |")
        if r["errors"]:
            L += ["", "<details><summary>Errors (" + str(len(r["errors"])) + ")</summary>", ""] + [f"- {e}" for e in r["errors"]] + ["", "</details>"]
    L += ["", "## Scoring rules", "", "```", rep["scoring_rules"], "```", ""]
    return "\n".join(L)
