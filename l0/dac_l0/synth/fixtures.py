"""Frozen evaluation fixtures, version `fixtures-v3` (P00-T08, P04-T03/T05/T06).

Three disjoint families with disjoint seeds. History matters (see DECISIONS ED-10):

- DEV: the gen-2 gallery works (seeds 1000+) and absent works (seeds 5000+). Their LAB
  outcomes have already been seen and they guided changes (incl. the OF-01 investigation).
  Tuning on DEV is allowed; DEV results are never reported as untouched evaluation.
- CALIBRATION: fresh seeds (11000+/13000+/15000+/17000+). Used only to choose decision
  thresholds (eval/calibrate.py). Reported as calibration results, not final results.
- FINAL: fresh seeds (21000+/23000+/25000+/27000+). Sealed: evaluated once with the frozen
  calibration file. Any later change of method makes FINAL "seen"; the next sealed family
  must then use new seeds (fixtures-v4).

Every family has the same challenge structure:
  CLEAN, EDITED (every transform cycled), ABSENT (+ natural scenes), SERIES_UNIQUE,
  SERIES_INTRO (shared intro), SERIES_RECAP (recap of the previous episode),
  STOCK_SHARED (same stock scene in two works), MONTAGE (two works), TRAILER (rapid cuts of
  one work), and UNUSABLE feeds (blank, static, synthetic private screens and overlays).

All queries pass through the simulated capture channel (generator.capture_channel).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .. import GENERATOR_VERSION
from .generator import (
    CONTENT_RNG_KEY,
    EDITED_TRANSFORMS,
    Clip,
    ComposedWork,
    Edition,
    EditionKind,
    NaturalScene,
    PrivateScreen,
    PrivateScreenKind,
    QueryTransform,
    SegmentClip,
    SynthWork,
    _rng,
    blank_frame,
)

FIXTURE_VERSION = "fixtures-v4"  # v4: fresh CAL4/FINAL4 seeds, larger families, separated starts, unique labels
# History: v3.1 (10 s shared intro/stock) — its CALIBRATION and FINAL families are SEEN and kept only
# so earlier reports stay traceable; they are not part of the v4 gallery.
QUERY_LEN_S = 8.0
FAMILIES = ("DEV", "CAL4", "FINAL4")
MIN_START_SEPARATION_S = 3.0

# family → seed bases and work-index bases (indices are disjoint across families)
_SPEC = {
    "DEV":         dict(plain_seed=1000,  n_plain=20, plain_idx=0,  absent_seed=5000,  absent_idx=900, series_seed=3100,  series_idx=100, stock_seed=3200,  stock_idx=110, nat_seed=7000,  nat_idx=0),
    "CALIBRATION": dict(plain_seed=11000, n_plain=10, plain_idx=20, absent_seed=15000, absent_idx=910, series_seed=13100, series_idx=120, stock_seed=13200, stock_idx=130, nat_seed=17000, nat_idx=10),
    "FINAL":       dict(plain_seed=21000, n_plain=10, plain_idx=30, absent_seed=25000, absent_idx=920, series_seed=23100, series_idx=140, stock_seed=23200, stock_idx=150, nat_seed=27000, nat_idx=20),
    # fixtures-v4 fresh families (never rendered or evaluated before their preregistration commit)
    "CAL4":        dict(plain_seed=31000, n_plain=20, plain_idx=40, absent_seed=35000, absent_idx=930, series_seed=33100, series_idx=160, stock_seed=33200, stock_idx=170, nat_seed=37000, nat_idx=30, n_absent=20, n_natural=10),
    "FINAL4":      dict(plain_seed=41000, n_plain=20, plain_idx=60, absent_seed=45000, absent_idx=960, series_seed=43100, series_idx=180, stock_seed=43200, stock_idx=190, nat_seed=47000, nat_idx=40, n_absent=20, n_natural=10),
}
N_ABSENT = 10
N_EPISODES = 4
N_NATURAL = 6


@dataclass
class FamilyFixtures:
    name: str
    plain: List[SynthWork]
    episodes: List[ComposedWork]
    stock_pair: Tuple[ComposedWork, ComposedWork]
    stock_window: Tuple[float, float, float, float]  # (A start, A end, B start, B end) in work time
    absent: List[SynthWork]
    natural: List[NaturalScene]

    @property
    def gallery_works(self) -> List:
        return list(self.plain) + list(self.episodes) + list(self.stock_pair)

    def gallery_editions(self) -> List[Edition]:
        eds = [Edition(w, k) for w in self.plain for k in EditionKind]
        eds += [Edition(w, EditionKind.THEATRICAL) for w in self.episodes]
        eds += [Edition(w, EditionKind.THEATRICAL) for w in self.stock_pair]
        return eds


def build_family(name: str) -> FamilyFixtures:
    sp = _SPEC[name]
    plain = [SynthWork(sp["plain_idx"] + i, sp["plain_seed"] + i) for i in range(sp["n_plain"])]
    absent = [SynthWork(sp["absent_idx"] + i, sp["absent_seed"] + i) for i in range(sp.get("n_absent", N_ABSENT))]
    natural = [NaturalScene(sp["nat_idx"] + i, sp["nat_seed"] + i) for i in range(sp.get("n_natural", N_NATURAL))]

    # Series: one shared intro base, one body base per episode. Never indexed on their own.
    intro = SynthWork(sp["series_idx"] + 9, sp["series_seed"])
    bodies = [SynthWork(sp["series_idx"] + 5 + k, sp["series_seed"] + 1 + k) for k in range(N_EPISODES)]
    series_id = f"S-{name[:3]}"
    episodes = []
    for k in range(N_EPISODES):
        recap = (bodies[k - 1], 20.0, 6.0) if k > 0 else (intro, 10.0, 6.0)
        episodes.append(ComposedWork(
            work_index=sp["series_idx"] + k, seed=sp["series_seed"] + 50 + k,
            segments=((intro, 0.0, 10.0), recap, (bodies[k], 0.0, 44.0)),
            series_id=series_id, episode_id=f"E{k + 1:02d}",
        ))

    # Stock footage reused in two different standalone works.
    stock = SynthWork(sp["stock_idx"] + 9, sp["stock_seed"])
    a = SynthWork(sp["stock_idx"] + 5, sp["stock_seed"] + 1)
    b = SynthWork(sp["stock_idx"] + 6, sp["stock_seed"] + 2)
    wa = ComposedWork(sp["stock_idx"], sp["stock_seed"] + 11, ((a, 0.0, 20.0), (stock, 10.0, 10.0), (a, 20.0, 30.0)))
    wb = ComposedWork(sp["stock_idx"] + 1, sp["stock_seed"] + 12, ((b, 0.0, 32.0), (stock, 10.0, 10.0), (b, 32.0, 18.0)))
    return FamilyFixtures(name, plain, episodes, (wa, wb), (20.0, 30.0, 32.0, 42.0), absent, natural)


def all_gallery_editions() -> List[Edition]:
    """One gallery index holds every family's indexed works (absent works never)."""
    eds: List[Edition] = []
    for f in FAMILIES:
        eds += build_family(f).gallery_editions()
    return eds


# --------------------------------------------------------------------------- queries


@dataclass
class QueryCase:
    family: str                      # DEV / CALIBRATION / FINAL
    kind: str                        # CLEAN, EDITED, ABSENT, SERIES_UNIQUE, SERIES_INTRO, ...
    label: str
    render: Callable[[float], np.ndarray]
    cluster: str                     # work-level cluster for interval estimation
    true_work: Optional[str] = None  # top-level identity (work ID, or series ID for episodes)
    true_episode: Optional[str] = None
    true_edition: Optional[str] = None
    acceptable: Tuple[str, ...] = ()  # identities that may be named without being wrong
    length_s: float = QUERY_LEN_S
    transform: str = "NONE"


def _clip_case(fam, kind, ed: Edition, start, tr, idx, true_work, true_ep=None, acceptable=()) -> QueryCase:
    key = f"{FIXTURE_VERSION}|{fam}|{kind}|{idx}"
    clip = Clip(ed, start, QUERY_LEN_S, tr, key)
    return QueryCase(fam, kind, f"{ed.asset_id}@{start:.2f}:{tr.value}#{idx}", clip.frame_at, true_work or ed.work.work_id,
                     true_work, true_ep, ed.edition_id if true_work else None, tuple(acceptable), QUERY_LEN_S, tr.value)


def _starts(rng, lo: float, hi: float, n: int, min_sep: float = MIN_START_SEPARATION_S) -> List[float]:
    """n clip starts in [lo, hi] at least min_sep apart (deterministic rejection sampling)."""
    out: List[float] = []
    for _ in range(400):
        if len(out) == n:
            break
        s = float(rng.uniform(lo, hi))
        if all(abs(s - o) >= min_sep for o in out):
            out.append(s)
    if len(out) < n:
        raise ValueError("cannot place separated starts")
    return out


def make_queries(name: str) -> List[QueryCase]:
    F = build_family(name)
    rng = _rng(CONTENT_RNG_KEY, FIXTURE_VERSION, "queries", name)
    cases: List[QueryCase] = []
    i = 0
    edited_cycle = 0
    for w in F.plain:
        for k in EditionKind:
            ed = Edition(w, k)
            for start in _starts(rng, 2.5, ed.duration_s - QUERY_LEN_S - 0.5, 2):
                cases.append(_clip_case(name, "CLEAN", ed, start, QueryTransform.NONE, i, w.work_id)); i += 1
                tr = EDITED_TRANSFORMS[edited_cycle % len(EDITED_TRANSFORMS)]; edited_cycle += 1
                cases.append(_clip_case(name, "EDITED", ed, start, tr, i, w.work_id)); i += 1
    series = F.episodes[0].series_id
    for ep in F.episodes:
        ed = Edition(ep, EditionKind.THEATRICAL)
        start = float(rng.uniform(14.0, ep.duration_s - QUERY_LEN_S - 0.5))
        c = _clip_case(name, "SERIES_UNIQUE", ed, start, QueryTransform.NONE, i, series, ep.episode_id); i += 1
        c.cluster = ep.work_id
        cases.append(c)
        # Shared intro (identical in every episode; the 8 s clip lies wholly inside the 10 s
        # intro) → series level is the correct granularity.
        c = _clip_case(name, "SERIES_INTRO", ed, 1.0, QueryTransform.NONE, i, series, None); i += 1
        c.cluster = ep.work_id
        cases.append(c)
        # Recap of the previous episode (6 s) plus 2 s of this episode.
        c = _clip_case(name, "SERIES_RECAP", ed, 10.0, QueryTransform.NONE, i, series, ep.episode_id); i += 1
        c.cluster = ep.work_id
        cases.append(c)
    wa, wb = F.stock_pair
    # The 8 s clip lies wholly inside the 10 s stock scene shared by both works.
    for j, (w, st) in enumerate([(wa, F.stock_window[0] + 1.0), (wb, F.stock_window[2] + 1.0)]):
        for tr in (QueryTransform.NONE, QueryTransform.CAPTIONED):
            c = _clip_case(name, "STOCK_SHARED", Edition(w, EditionKind.THEATRICAL), st, tr, i, w.work_id,
                           acceptable=(wa.work_id, wb.work_id)); i += 1
            cases.append(c)
    # Montage: 4 s of one plain work + 4 s of another.
    for m in range(12):
        a, b = rng.choice(len(F.plain), size=2, replace=False)
        ea, eb = Edition(F.plain[a], EditionKind.THEATRICAL), Edition(F.plain[b], EditionKind.THEATRICAL)
        sa, sb = float(rng.uniform(3, 50)), float(rng.uniform(3, 50))
        sc = SegmentClip(((ea, sa, 4.0), (eb, sb, 4.0)), f"{FIXTURE_VERSION}|{name}|MONTAGE|{m}")
        cases.append(QueryCase(name, "MONTAGE", f"{ea.asset_id}@{sa:.1f}+{eb.asset_id}@{sb:.1f}#m{m}", sc.frame_at,
                               f"{sc.work_ids[0]}+{sc.work_ids[1]}", None, None, None, sc.work_ids))
    # Trailer: five 1.6 s cuts from one work, out of order.
    for t in range(8):
        w = F.plain[int(rng.integers(0, len(F.plain)))]
        ed = Edition(w, EditionKind.THEATRICAL)
        starts = sorted(rng.uniform(3, 55, size=5), reverse=bool(t % 2))
        sc = SegmentClip(tuple((ed, float(s), 1.6) for s in starts), f"{FIXTURE_VERSION}|{name}|TRAILER|{t}")
        cases.append(QueryCase(name, "TRAILER", f"{ed.asset_id} cuts#t{t}", sc.frame_at, w.work_id, w.work_id, None, None, (w.work_id,)))
    for w in F.absent:
        ed = Edition(w, EditionKind.THEATRICAL)
        for j, start in enumerate(_starts(rng, 2.5, ed.duration_s - QUERY_LEN_S - 0.5, 6)):
            tr = QueryTransform.NONE if j % 2 == 0 else EDITED_TRANSFORMS[int(rng.integers(0, len(EDITED_TRANSFORMS)))]
            c = _clip_case(name, "ABSENT", ed, start, tr, i, None); i += 1
            c.cluster = w.work_id
            cases.append(c)
    for ns in F.natural:
        key = f"{FIXTURE_VERSION}|{name}|NAT|{ns.asset_id}"
        from .generator import capture_channel
        cases.append(QueryCase(name, "ABSENT", ns.asset_id, (lambda t, ns=ns, key=key: capture_channel(ns.render_frame(t), key, t)), ns.asset_id))
    # Unusable feeds (identical in every family; they carry no identity).
    still = F.plain[0].render_frame(10.0)
    cases.append(QueryCase(name, "UNUSABLE", "BLANK_BLACK", lambda t: blank_frame(0), "blank", acceptable=("UNSUPPORTED_CAPTURE",)))
    cases.append(QueryCase(name, "UNUSABLE", "STATIC_FRAME_OF_KNOWN_WORK", lambda t: still, "static", acceptable=("INSUFFICIENT_SIGNAL",)))
    underlay_ed = Edition(F.plain[1], EditionKind.THEATRICAL)
    for kind in PrivateScreenKind:
        ps = PrivateScreen(kind, 1)
        cases.append(QueryCase(name, "UNUSABLE", ps.asset_id, (lambda t, ps=ps: ps.render_frame(t)), "private",
                               acceptable=("NO_CONFIDENT_MATCH", "INSUFFICIENT_SIGNAL")))
    # Overlay classes over playing video (CAP-04 overlay analogues): a title may legitimately
    # be recognised from the visible video, but the overlay must not create a wrong title.
    for kind in (PrivateScreenKind.NOTIFICATION_BANNER, PrivateScreenKind.KEYBOARD, PrivateScreenKind.PIP_WINDOW):
        ps = PrivateScreen(kind, 2)
        cases.append(QueryCase(name, "OVERLAY", f"{ps.asset_id}+{underlay_ed.asset_id}",
                               (lambda t, ps=ps: ps.render_frame(t, underlay=underlay_ed.render_frame(20.0 + t))),
                               underlay_ed.work.work_id, underlay_ed.work.work_id, None, None, (underlay_ed.work.work_id,)))
    return cases


def fixture_manifest() -> Dict:
    """Frozen description of fixtures-v3 (no rendered media). Its hash is recorded with
    every calibration file and LAB report."""
    fams = {}
    for f in FAMILIES:
        F = build_family(f)
        fams[f] = {
            "plain": [(w.work_id, w.seed) for w in F.plain],
            "episodes": [(e.work_id, e.series_id, e.episode_id, [(s[0].seed, s[1], s[2]) for s in e.segments]) for e in F.episodes],
            "stock_pair": [(w.work_id, [(s[0].seed, s[1], s[2]) for s in w.segments]) for w in F.stock_pair],
            "absent": [(w.work_id, w.seed) for w in F.absent],
            "natural": [(n.asset_id, n.seed) for n in F.natural],
            "query_count": len(make_queries(f)),
        }
    body = {"fixture_version": FIXTURE_VERSION, "generator_version": GENERATOR_VERSION,
            "content_rng_key": CONTENT_RNG_KEY, "families": fams,
            "status": {"DEV": "SEEN (tuning allowed)", "CAL4": "CALIBRATION ONLY", "FINAL4": "SEALED"}}
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body
