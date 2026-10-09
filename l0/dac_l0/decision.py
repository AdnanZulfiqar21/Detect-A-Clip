"""Decision policy and result construction (P04-T05).

Thresholds are research values (D05 proposals). `calibration_status` stays UNCALIBRATED
until a frozen calibration file produced from the CALIBRATION family only is loaded
(see eval/calibrate.py); even then L0 synthetic calibration cannot pass a release gate.
Nothing here can emit OUTSIDE_CATALOGUE or a numeric confidence.

Evidence hierarchy (F03/F04, P04-T04): series → episode/work → edition → time.
- A level is named only when uniquely supported; otherwise the result stops one level up.
- Competing evidence from a *different* identity group (another work or series) within the
  margin blocks VERIFIED_MATCH (shared footage, stock scenes, recaps across series).
- Evidence strength uses distinct supporting frames, the query time they span, and their
  mean distance relative to the candidate radius. Frames of a slow scene are correlated,
  so a frame count alone overstates evidence (OF-01).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import CALIBRATION_STATUS_DEFAULT, GENERATOR_VERSION, INDEX_FORMAT_VERSION
from .index.builder import IndexBundle
from .index.descriptors import DescriptorFamily
from .schemas import PersistenceMode, RecognitionResult, ResultState, SegmentEvidence
from .verify import Hypothesis, segment_montage

RESULT_VALIDITY_MS = 15 * 60 * 1000  # until next scan or 15 minutes, whichever first (F03)


@dataclass(frozen=True)
class DecisionThresholds:
    calibration_version: str = "dev-uncalibrated-2"
    calibration_status: str = CALIBRATION_STATUS_DEFAULT
    min_qualified_frames: int = 4          # fewer → INSUFFICIENT_SIGNAL
    # VERIFIED_MATCH evidence
    verified_min_support: int = 6
    verified_min_support_fraction: float = 0.5
    verified_min_span_ms: int = 2500
    verified_max_mean_dist_frac: float = 0.8   # mean distance / candidate radius
    verified_min_margin: int = 3               # support over best competing identity group
    # POSSIBLE_MATCH evidence
    possible_min_support: int = 3
    possible_min_span_ms: int = 1000
    possible_max_mean_dist_frac: float = 0.9
    possible_on_competition: bool = False      # name one of two competing works as POSSIBLE?
    episode_margin: int = 3                    # support margin to name a specific episode
    # Candidate radii chosen on the DEV family only (ED-09, ED-10).
    hash_max_distance: float = 9.0     # DEV other-work p5 = 10 under gen-3 channel (ED-10)
    thumb32_max_distance: float = 120.0
    thumb144_max_distance: float = 300.0
    top_k: int = 12
    mirror_invariant: bool = True

    def radius(self, family: DescriptorFamily) -> float:
        return {
            DescriptorFamily.HASH64: self.hash_max_distance,
            DescriptorFamily.THUMB32: self.thumb32_max_distance,
            DescriptorFamily.THUMB144: self.thumb144_max_distance,
        }[family]

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass
class FrameSummary:
    offered: int = 0
    selected: int = 0
    qualified: int = 0
    unusable_feed: int = 0  # BLANK frames
    flags: List[str] = field(default_factory=list)


def _group_key(bundle: IndexBundle, h: Hypothesis) -> str:
    w = bundle.works[h.work_index]
    return f"SERIES:{w.series_id}" if w.series_id else f"WORK:{w.work_id}"


def _strong(h: Hypothesis, min_support: int, min_span: int, max_frac: float, radius: float) -> bool:
    return h.support >= min_support and h.span_ms >= min_span and h.mean_distance <= max_frac * radius


def decide(
    scan_id: str,
    generation: int,
    hyps: Sequence[Hypothesis],
    frames: FrameSummary,
    bundle: IndexBundle,
    now_monotonic_ms: int,
    thresholds: DecisionThresholds = DecisionThresholds(),
    entitlement_recheck: str = "PASS",
) -> RecognitionResult:
    """Map verified hypotheses + frame summary to exactly one RecognitionResult."""
    th = thresholds
    radius = th.radius(bundle.family)
    common = dict(
        scan_id=scan_id,
        cancellation_generation=generation,
        generator_version=GENERATOR_VERSION,
        index_format_version=INDEX_FORMAT_VERSION,
        calibration_version=th.calibration_version,
        calibration_status=th.calibration_status,
        local_entitlement_recheck=entitlement_recheck,
        created_at_monotonic_ms=now_monotonic_ms,
        expires_at_monotonic_ms=now_monotonic_ms + RESULT_VALIDITY_MS,
        validity_clock_basis="monotonic",
        persistence_mode=PersistenceMode.MEMORY_ONLY,
    )

    def plain(state: ResultState, flags: List[str]) -> RecognitionResult:
        return RecognitionResult(state=state, candidate_work_id=None, candidate_edition_id=None,
                                 candidate_episode_id=None, segments=[], ambiguity_flags=flags, **common)

    if entitlement_recheck != "PASS":
        return plain(ResultState.ERROR, ["ENTITLEMENT_RECHECK_FAILED"])
    if frames.selected > 0 and frames.unusable_feed == frames.selected:
        return plain(ResultState.UNSUPPORTED_CAPTURE, ["ALL_FRAMES_BLANK"])
    if frames.qualified < th.min_qualified_frames:
        return plain(ResultState.INSUFFICIENT_SIGNAL, [f"QUALIFIED_FRAMES={frames.qualified}"])
    if not hyps:
        return plain(ResultState.NO_CONFIDENT_MATCH, [])

    # ---- identity groups (a series is one group; each standalone work is its own group)
    groups: Dict[str, List[Hypothesis]] = {}
    for h in hyps:
        groups.setdefault(_group_key(bundle, h), []).append(h)
    for g in groups.values():
        g.sort(key=lambda h: (-h.support, h.mean_distance))
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1][0].support, kv[1][0].mean_distance))
    top_list = ranked[0][1]
    top = top_list[0]
    competitor = ranked[1][1][0] if len(ranked) > 1 else None
    margin = top.support - (competitor.support if competitor else 0)

    flags: List[str] = []

    # ---- montage: disjoint query ranges supported by different identity groups
    segments = segment_montage(hyps, min_support=th.possible_min_support)
    montage = len({_group_key(bundle, s) for s in segments}) > 1
    competing = competitor is not None and margin < th.verified_min_margin and not montage

    tw = bundle.works[top.work_index]
    episode_ambiguous = False
    if tw.series_id is not None:
        rivals = [h for h in top_list[1:] if h.work_index != top.work_index and h.support > top.support - th.episode_margin]
        episode_ambiguous = bool(rivals)
    if top.ambiguous_editions:
        flags.append("EDITION_AMBIGUOUS")
    if episode_ambiguous:
        flags.append("EPISODE_AMBIGUOUS")
    if montage:
        flags.append("MULTI_TITLE_SEGMENTS")
    if competing:
        flags.append("COMPETING_WORKS")

    def names(h: Hypothesis, ep_ambiguous: bool) -> Tuple[str, Optional[str], Optional[str]]:
        w = bundle.works[h.work_index]
        ed = w.editions[h.edition_index] if h.edition_index is not None else None
        if w.series_id:
            if ep_ambiguous:
                return w.series_id, None, None          # series level only
            return w.series_id, ed, w.episode_id
        return w.work_id, ed, None

    def seg(h: Hypothesis, ep_ambiguous: bool) -> SegmentEvidence:
        work, ed, _ = names(h, ep_ambiguous)
        unique_time = ed is not None and not ep_ambiguous
        return SegmentEvidence(
            work_id=work, edition_id=ed, query_start_ms=h.query_start_ms, query_end_ms=h.query_end_ms,
            reference_offset_ms=h.offset_ms if unique_time else None, supporting_frames=h.support,
        )

    def match(state: ResultState, h: Hypothesis, segs: List[SegmentEvidence], extra: List[str], ep_amb: bool) -> RecognitionResult:
        work, ed, ep = names(h, ep_amb)
        return RecognitionResult(state=state, candidate_work_id=work, candidate_edition_id=ed, candidate_episode_id=ep,
                                 segments=segs, ambiguity_flags=flags + extra, **common)

    def possible_strength(h: Hypothesis) -> bool:
        return _strong(h, th.possible_min_support, th.possible_min_span_ms, th.possible_max_mean_dist_frac, radius)

    if montage:
        strong_segs = [s for s in segments if possible_strength(s)]
        if not strong_segs:
            return plain(ResultState.NO_CONFIDENT_MATCH, flags)
        # Bounded segment-specific evidence; overall state is at most POSSIBLE_MATCH and
        # no single episode/time is asserted for the montage as a whole.
        return match(ResultState.POSSIBLE_MATCH, strong_segs[0], [seg(s, True) for s in strong_segs], [], True)

    frac = top.support / max(1, frames.qualified)
    verified = (
        not competing
        and _strong(top, th.verified_min_support, th.verified_min_span_ms, th.verified_max_mean_dist_frac, radius)
        and frac >= th.verified_min_support_fraction
        and margin >= th.verified_min_margin
    )
    if verified:
        return match(ResultState.VERIFIED_MATCH, top, [seg(top, episode_ambiguous)], [], episode_ambiguous)
    if competing and not th.possible_on_competition:
        return plain(ResultState.NO_CONFIDENT_MATCH, flags)
    if possible_strength(top):
        return match(ResultState.POSSIBLE_MATCH, top, [seg(top, episode_ambiguous)], ["WEAK_SUPPORT"], episode_ambiguous)
    return plain(ResultState.NO_CONFIDENT_MATCH, flags)
