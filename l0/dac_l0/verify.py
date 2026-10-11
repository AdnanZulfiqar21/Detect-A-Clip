"""Temporal / equivalence verification (P04-T03).

Given per-query-frame candidates, find (work, edition) hypotheses whose reference
timestamps advance consistently with the query timestamps (a stable offset), count the
supporting frames, flag edition ambiguity, and segment montages into disjoint query
ranges that support different works.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .index.retrieval import Candidate


@dataclass
class Hypothesis:
    work_index: int
    edition_index: Optional[int]      # None when editions cannot be separated
    offset_ms: int                    # reference_t - query_t for the supporting cluster
    support: int                      # number of distinct query frames supporting it
    mean_distance: float
    query_start_ms: int
    query_end_ms: int
    ambiguous_editions: List[int] = field(default_factory=list)

    @property
    def span_ms(self) -> int:
        """Query time covered by supporting frames. Consecutive frames of a slow scene are
        correlated, so span is reported alongside the raw frame count (OF-01)."""
        return self.query_end_ms - self.query_start_ms


def _cluster_offsets(pairs: Sequence[Tuple[int, int, float]], tol_ms: int) -> Tuple[int, List[Tuple[int, int, float]]]:
    """pairs = (query_t, offset, distance). Return (centre offset, members) of the largest
    cluster of offsets within ±tol_ms, counting at most one member per query frame."""
    best_centre, best_members = 0, []
    offs = sorted(set(p[1] for p in pairs))
    for c in offs:
        members: Dict[int, Tuple[int, int, float]] = {}
        for qt, off, d in pairs:
            if abs(off - c) <= tol_ms:
                prev = members.get(qt)
                if prev is None or d < prev[2]:
                    members[qt] = (qt, off, d)
        if len(members) > len(best_members):
            best_centre, best_members = c, list(members.values())
    return best_centre, best_members


def verify(
    per_frame: Sequence[Tuple[int, List[Candidate]]],
    sampling_interval_ms: int,
    min_support: int = 2,
    edition_margin: int = 3,
) -> List[Hypothesis]:
    """per_frame: list of (query_timestamp_ms, candidates). Returns hypotheses sorted by
    support desc, then mean distance asc."""
    # A query frame matches the nearest reference sample, so offsets jitter by up to half a
    # reference interval; +250 ms absorbs selection jitter and mild speed changes.
    tol = sampling_interval_ms // 2 + 250
    by_we: Dict[Tuple[int, int], List[Tuple[int, int, float]]] = defaultdict(list)
    for qt, cands in per_frame:
        for c in cands:
            by_we[(c.locator.work_index, c.locator.edition_index)].append((qt, c.locator.t_ms - qt, c.distance))

    raw: List[Hypothesis] = []
    for (wi, ei), pairs in by_we.items():
        centre, members = _cluster_offsets(pairs, tol)
        if len(members) < min_support:
            continue
        qts = [m[0] for m in members]
        raw.append(
            Hypothesis(
                work_index=wi, edition_index=ei, offset_ms=centre, support=len(members),
                mean_distance=sum(m[2] for m in members) / len(members),
                query_start_ms=min(qts), query_end_ms=max(qts),
            )
        )

    # Edition ambiguity: editions of the same work with (near-)equal support and overlapping
    # query ranges cannot be separated; collapse to work-level with the ambiguity recorded.
    by_work: Dict[int, List[Hypothesis]] = defaultdict(list)
    for h in raw:
        by_work[h.work_index].append(h)
    merged: List[Hypothesis] = []
    for wi, hs in by_work.items():
        hs.sort(key=lambda h: (-h.support, h.mean_distance))
        top = hs[0]
        # An edition is asserted only when it beats every other edition of the same work by
        # `edition_margin` supporting frames; otherwise report the work with ambiguity.
        tied = [h for h in hs if h.support > top.support - edition_margin and h.edition_index != top.edition_index]
        if tied:
            top.ambiguous_editions = sorted({top.edition_index, *[h.edition_index for h in tied]})
            top.edition_index = None
        merged.append(top)
    merged.sort(key=lambda h: (-h.support, h.mean_distance))
    return merged


def segment_montage(hyps: Sequence[Hypothesis], min_support: int = 3) -> List[Hypothesis]:
    """Return hypotheses for different works that occupy mostly disjoint query ranges.
    If two strong hypotheses overlap heavily in query time they are competing, not a montage."""
    strong = [h for h in hyps if h.support >= min_support]
    segments: List[Hypothesis] = []
    for h in strong:
        overlap = False
        for s in segments:
            lo, hi = max(h.query_start_ms, s.query_start_ms), min(h.query_end_ms, s.query_end_ms)
            if hi - lo > 0.5 * max(1, min(h.query_end_ms - h.query_start_ms, s.query_end_ms - s.query_start_ms)):
                overlap = True
                break
        if not overlap:
            segments.append(h)
    segments.sort(key=lambda h: h.query_start_ms)
    return segments
