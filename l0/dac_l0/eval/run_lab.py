"""LAB evaluation runner: AI-01/02/03/07 exploratory + IDX-01 desktop baseline (P04-T02).

Writes a JSON + Markdown report with purpose LAB into the evidence directory.
"""
from __future__ import annotations

import json
import platform
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np

from .. import __version__
from ..decision import DecisionThresholds
from ..index.builder import IndexBundle, build_index, duplicate_descriptor_ratio
from ..index.descriptors import DescriptorFamily
from ..index.retrieval import FlatRetriever
from ..pipeline import Delivered, recognise
from ..schemas import ResultState
from ..synth.generator import (
    EDITED_TRANSFORMS,
    Clip,
    Edition,
    EditionKind,
    NaturalScene,
    PrivateScreen,
    PrivateScreenKind,
    QueryTransform,
    SynthWork,
    absent_works,
    blank_frame,
    gallery_works,
)
from .protocol import PROTOCOL_TEXT, Metric, freeze_splits

QUERY_LEN_S = 8.0
DELIVERY_FPS = 10  # OS delivers at 10 fps; the selector reduces to ≤2 fps


@dataclass
class QueryCase:
    family: str          # CLEAN / EDITED / ABSENT / UNUSABLE
    true_work: Optional[str]
    true_edition: Optional[str]
    label: str
    render: Callable[[float], np.ndarray]
    cluster: str
    split: str = "N/A"  # DEV / CALIBRATION / FINAL / ABSENT / N/A

    @property
    def frames(self) -> Iterator[Delivered]:
        """Lazily simulated OS delivery at DELIVERY_FPS (frames are never all held in memory)."""
        n = int(QUERY_LEN_S * DELIVERY_FPS)
        for i in range(n):
            yield Delivered(int(i * 1000 / DELIVERY_FPS), self.render(i / DELIVERY_FPS))


def make_queries(works: List[SynthWork], absent: List[SynthWork], clips_per_edition: int = 3, seed: int = 7, split_of: Optional[Dict[str, str]] = None) -> List[QueryCase]:
    split_of = split_of or {}
    rng = np.random.default_rng(seed)
    cases: List[QueryCase] = []
    for w in works:
        for kind in EditionKind:
            ed = Edition(w, kind)
            for j in range(clips_per_edition):
                start = float(rng.uniform(2.5, ed.duration_s - QUERY_LEN_S - 0.5))
                clean = Clip(ed, start, QUERY_LEN_S)
                cases.append(QueryCase("CLEAN", w.work_id, ed.edition_id, f"{ed.asset_id}@{start:.1f}", clean.frame_at, w.work_id, split_of.get(w.work_id, "N/A")))
                tr = EDITED_TRANSFORMS[int(rng.integers(0, len(EDITED_TRANSFORMS)))]
                edited = Clip(ed, start, QUERY_LEN_S, tr)
                cases.append(QueryCase("EDITED", w.work_id, ed.edition_id, f"{ed.asset_id}@{start:.1f}:{tr.value}", edited.frame_at, w.work_id, split_of.get(w.work_id, "N/A")))
    for w in absent:
        ed = Edition(w, EditionKind.THEATRICAL)
        for j in range(6):
            start = float(rng.uniform(2.5, ed.duration_s - QUERY_LEN_S - 0.5))
            tr = QueryTransform.NONE if j % 2 == 0 else EDITED_TRANSFORMS[int(rng.integers(0, len(EDITED_TRANSFORMS)))]
            cases.append(QueryCase("ABSENT", None, None, f"{ed.asset_id}@{start:.1f}:{tr.value}", Clip(ed, start, QUERY_LEN_S, tr).frame_at, w.work_id, "ABSENT"))
    for i in range(6):
        ns = NaturalScene(i, 7000 + i)
        cases.append(QueryCase("ABSENT", None, None, ns.asset_id, ns.render_frame, ns.asset_id, "ABSENT"))
    # Unusable feeds (AI-07 / CAP-03 analogues)
    cases.append(QueryCase("UNUSABLE", None, None, "BLANK_BLACK", lambda t: blank_frame(0), "blank"))
    still = works[0].render_frame(10.0)
    cases.append(QueryCase("UNUSABLE", works[0].work_id, None, "STATIC_FRAME_OF_KNOWN_WORK", lambda t: still, "static"))
    for kind in PrivateScreenKind:
        ps = PrivateScreen(kind, 1)
        cases.append(QueryCase("UNUSABLE", None, None, ps.asset_id, lambda t, ps=ps: ps.render_frame(t), "private"))
    return cases


@dataclass
class FamilyReport:
    family: str
    build_seconds: float
    vector_count: int
    payload_bytes: int
    bytes_per_reference_hour: float
    indexed_hours: float
    duplicate_ratio: float
    metrics: List[Dict] = field(default_factory=list)
    latency_ms_p50: float = 0.0
    latency_ms_p90: float = 0.0
    state_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def evaluate_family(family: DescriptorFamily, works: List[SynthWork], cases: List[QueryCase], thresholds: DecisionThresholds, sampling_interval_s: float = 2.0) -> Tuple[FamilyReport, IndexBundle]:
    editions = [Edition(w, k) for w in works for k in EditionKind]
    bundle = build_index(editions, family, sampling_interval_s)
    retr = FlatRetriever(bundle)
    rep = FamilyReport(family.value, bundle.build_seconds, bundle.vector_count, bundle.payload_bytes,
                       bundle.bytes_per_reference_hour(), bundle.indexed_hours, duplicate_descriptor_ratio(bundle))
    lat: List[float] = []
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_cluster: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
    tallies: Dict[str, List[int]] = defaultdict(list)

    for i, c in enumerate(cases):
        t0 = time.perf_counter()
        result, hyps, summary = recognise(f"lab-{i}", 1, c.frames, retr, now_monotonic_ms=0, thresholds=thresholds)
        lat.append((time.perf_counter() - t0) * 1000)
        counts[c.family][result.state.value] += 1
        assert result.state != ResultState.OUTSIDE_CATALOGUE
        named = result.candidate_work_id
        if c.family in ("CLEAN", "EDITED"):
            top1 = int(named == c.true_work and result.state in (ResultState.VERIFIED_MATCH, ResultState.POSSIBLE_MATCH))
            ver = int(named == c.true_work and result.state == ResultState.VERIFIED_MATCH)
            wrong_named = int(named is not None and named != c.true_work)
            for suffix in ([""] + (["[heldout]"] if c.split in ("CALIBRATION", "FINAL") else [])):
                for nm, v in ((f"{c.family}_top1", top1), (f"{c.family}_verified_correct", ver), (f"{c.family}_wrong_work_named", wrong_named)):
                    tallies[nm + suffix].append(v)
                    by_cluster[nm + suffix][c.cluster].append(v)
            if result.state == ResultState.VERIFIED_MATCH and c.true_edition is not None:
                if result.candidate_edition_id is not None:
                    ok = int(result.candidate_edition_id == c.true_edition)
                    tallies[f"{c.family}_edition_correct_when_asserted"].append(ok)
                    by_cluster[f"{c.family}_edition_correct_when_asserted"][c.cluster].append(ok)
            if not top1:
                rep.failures.append(f"{c.family} {c.label} → {result.state.value} {named} flags={result.ambiguity_flags}")
        elif c.family == "ABSENT":
            fv = int(result.state == ResultState.VERIFIED_MATCH)
            fp = int(result.state == ResultState.POSSIBLE_MATCH)
            tallies["ABSENT_false_verified"].append(fv)
            tallies["ABSENT_false_possible"].append(fp)
            by_cluster["ABSENT_false_verified"][c.cluster].append(fv)
            by_cluster["ABSENT_false_possible"][c.cluster].append(fp)
            if fv or fp:
                rep.failures.append(f"ABSENT {c.label} → {result.state.value} {named}")
        else:  # UNUSABLE
            expected = {
                "BLANK_BLACK": {ResultState.UNSUPPORTED_CAPTURE},
                "STATIC_FRAME_OF_KNOWN_WORK": {ResultState.INSUFFICIENT_SIGNAL},
            }.get(c.label, {ResultState.NO_CONFIDENT_MATCH, ResultState.INSUFFICIENT_SIGNAL})
            ok = int(result.state in expected)
            tallies["UNUSABLE_expected_state"].append(ok)
            by_cluster["UNUSABLE_expected_state"][c.label].append(ok)
            if not ok:
                rep.failures.append(f"UNUSABLE {c.label} → {result.state.value} (expected {[e.value for e in expected]})")

    defs = {
        "CLEAN_top1": "CLEAN clips; success = true work named in VERIFIED or POSSIBLE",
        "CLEAN_verified_correct": "CLEAN clips; success = true work in VERIFIED_MATCH",
        "CLEAN_wrong_work_named": "CLEAN clips; event = a different work named (any match state)",
        "CLEAN_edition_correct_when_asserted": "CLEAN VERIFIED results that asserted an edition",
        "EDITED_top1": "EDITED clips; success = true work named in VERIFIED or POSSIBLE",
        "EDITED_verified_correct": "EDITED clips; success = true work in VERIFIED_MATCH",
        "EDITED_wrong_work_named": "EDITED clips; event = a different work named",
        "EDITED_edition_correct_when_asserted": "EDITED VERIFIED results that asserted an edition",
        "ABSENT_false_verified": "ABSENT clips; event = VERIFIED_MATCH emitted",
        "ABSENT_false_possible": "ABSENT clips; event = POSSIBLE_MATCH emitted",
        "UNUSABLE_expected_state": "UNUSABLE feeds; success = expected non-match state",
    }
    for name, vals in tallies.items():
        base = name.replace("[heldout]", "")
        d = defs.get(base, base) + (" — restricted to CALIBRATION+FINAL works (not used to choose radii)" if name.endswith("[heldout]") else "")
        m = Metric(name, int(sum(vals)), len(vals), d)
        clusters = {cid: (int(sum(v)), len(v)) for cid, v in by_cluster[name].items()}
        rep.metrics.append(m.finalize(clusters).to_dict())
    rep.latency_ms_p50 = float(np.percentile(lat, 50)) if lat else 0.0
    rep.latency_ms_p90 = float(np.percentile(lat, 90)) if lat else 0.0
    rep.state_counts = {k: dict(v) for k, v in counts.items()}
    return rep, bundle


def run(out_dir: Path, n_works: int = 20, n_absent: int = 10, families: Optional[List[DescriptorFamily]] = None, thresholds: DecisionThresholds = DecisionThresholds()) -> Path:
    families = families or list(DescriptorFamily)
    works = gallery_works(n_works)
    absent = absent_works(n_absent)
    splits = freeze_splits([w.work_id for w in works], [w.work_id for w in absent])
    split_of = {**{w: "DEV" for w in splits.dev_works}, **{w: "CALIBRATION" for w in splits.calibration_works}, **{w: "FINAL" for w in splits.final_works}}
    cases = make_queries(works, absent, split_of=split_of)
    reports = []
    for fam in families:
        rep, _ = evaluate_family(fam, works, cases, thresholds)
        reports.append(rep)
    now = datetime.now(timezone.utc)
    out = {
        "purpose": "LAB",
        "claim_boundary": "Synthetic L0 exploratory evidence only. Not device, rights, coverage or release evidence.",
        "run_at": now.isoformat(),
        "host": f"{platform.system()} {platform.release()} {platform.machine()} python {platform.python_version()}",
        "l0_version": __version__,
        "git_commit": _git_commit(),
        "thresholds": thresholds.__dict__,
        "split_manifest_hash": splits.manifest_hash(),
        "splits": splits.__dict__,
        "query_counts": {f: sum(1 for c in cases if c.family == f) for f in ("CLEAN", "EDITED", "ABSENT", "UNUSABLE")},
        "protocol": PROTOCOL_TEXT,
        "families": [r.__dict__ for r in reports],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    jp = out_dir / f"lab_report_{stamp}.json"
    jp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    mp = out_dir / f"lab_report_{stamp}.md"
    mp.write_text(render_markdown(out), encoding="utf-8")
    return mp


def render_markdown(out: Dict) -> str:
    L = [f"# L0 LAB report — {out['run_at']}", "",
         f"**Purpose:** {out['purpose']}. {out['claim_boundary']}", "",
         f"Host: {out['host']} · l0 {out['l0_version']} · commit `{out['git_commit']}` · split hash `{out['split_manifest_hash'][:16]}`", "",
         "Query counts: " + ", ".join(f"{k}={v}" for k, v in out["query_counts"].items()), "",
         "## IDX-01 desktop baseline (payload only; metadata/index overhead included in payload_bytes)", "",
         "| Family | vectors | payload B | B / reference hour | indexed h | build s | dup ratio | p50 ms/query | p90 ms/query |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for f in out["families"]:
        L.append(f"| {f['family']} | {f['vector_count']} | {f['payload_bytes']:,} | {f['bytes_per_reference_hour']:,.0f} | {f['indexed_hours']:.3f} | {f['build_seconds']:.2f} | {f['duplicate_ratio']:.3f} | {f['latency_ms_p50']:.1f} | {f['latency_ms_p90']:.1f} |")
    L += ["", "## Metrics (Wilson 95 % assumes independence; cluster bootstrap over works is exploratory)", ""]
    for f in out["families"]:
        L += [f"### {f['family']}", "", "| metric | k/n | rate | Wilson 95 % | cluster boot 95 % (n clusters) | notes |", "|---|---:|---:|---|---|---|"]
        for m in f["metrics"]:
            L.append(f"| {m['name']} | {m['k']}/{m['n']} | {m['rate']:.3f} | [{m['wilson95'][0]:.3f}, {m['wilson95'][1]:.3f}] | [{m['cluster_boot95'][0]:.3f}, {m['cluster_boot95'][1]:.3f}] ({m['n_clusters']}) | {'; '.join(m['notes'])} |")
        L += ["", "State counts: " + json.dumps(f["state_counts"]), ""]
        if f["failures"]:
            L += ["<details><summary>Failures (" + str(len(f["failures"])) + ")</summary>", ""]
            L += [f"- {x}" for x in f["failures"][:200]]
            L += ["", "</details>", ""]
    L += ["## Protocol (preregistered)", "", "```", out["protocol"], "```", ""]
    return "\n".join(L)
