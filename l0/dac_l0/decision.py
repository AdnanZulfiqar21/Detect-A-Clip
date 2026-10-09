"""Calibrated decision policy and result construction (P04-T05 preparation).

Thresholds here are DEVELOPMENT defaults with calibration_status UNCALIBRATED. They
guide research only (D05). Nothing in this module can emit OUTSIDE_CATALOGUE or a
numeric confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from . import CALIBRATION_STATUS_DEFAULT, GENERATOR_VERSION, INDEX_FORMAT_VERSION
from .index.builder import IndexBundle
from .schemas import PersistenceMode, RecognitionResult, ResultState, SegmentEvidence
from .verify import Hypothesis, segment_montage

RESULT_VALIDITY_MS = 15 * 60 * 1000  # until next scan or 15 minutes, whichever first (F03)


@dataclass(frozen=True)
class DecisionThresholds:
    calibration_version: str = "dev-uncalibrated-1"
    calibration_status: str = CALIBRATION_STATUS_DEFAULT
    min_qualified_frames: int = 4          # fewer → INSUFFICIENT_SIGNAL
    verified_min_support: int = 6          # supporting frames for VERIFIED_MATCH
    verified_min_support_fraction: float = 0.5
    verified_min_margin: int = 3           # support margin over best *other* work
    possible_min_support: int = 3
    # Candidate radii chosen on the DEV split only (works in SplitFamilies.dev_works), set just
    # below the 5th percentile of the nearest *other-work* distance at 2 s reference sampling
    # (measured 2026-10-09: HASH64 p5=14, THUMB32 p5=156, THUMB144 p5=387). Not calibrated.
    hash_max_distance: float = 10.0        # Hamming radius for HASH64 candidates
    thumb32_max_distance: float = 120.0    # L2 radius for THUMB32
    thumb144_max_distance: float = 300.0   # L2 radius for THUMB144
    top_k: int = 12
    mirror_invariant: bool = True       # search query and its horizontal flip


@dataclass
class FrameSummary:
    offered: int = 0
    selected: int = 0
    qualified: int = 0
    unusable_feed: int = 0  # BLANK frames
    flags: List[str] = field(default_factory=list)


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

    # Feed unusable: every selected frame was blank/black (secure window, no video).
    if frames.selected > 0 and frames.unusable_feed == frames.selected:
        return plain(ResultState.UNSUPPORTED_CAPTURE, ["ALL_FRAMES_BLANK"])
    if frames.qualified < th.min_qualified_frames:
        return plain(ResultState.INSUFFICIENT_SIGNAL, [f"QUALIFIED_FRAMES={frames.qualified}"])

    if not hyps:
        return plain(ResultState.NO_CONFIDENT_MATCH, [])

    top = hyps[0]
    others = [h for h in hyps if h.work_index != top.work_index]
    second_support = others[0].support if others else 0
    margin = top.support - second_support
    frac = top.support / max(1, frames.qualified)

    segments = segment_montage(hyps)
    montage = len({s.work_index for s in segments}) > 1
    flags: List[str] = []
    if top.ambiguous_editions:
        flags.append("EDITION_AMBIGUOUS")
    if montage:
        flags.append("MULTI_TITLE_SEGMENTS")

    def work_id(h: Hypothesis) -> str:
        return bundle.works[h.work_index].work_id

    def edition_id(h: Hypothesis) -> Optional[str]:
        if h.edition_index is None:
            return None
        return bundle.works[h.work_index].editions[h.edition_index]

    def seg(h: Hypothesis) -> SegmentEvidence:
        return SegmentEvidence(
            work_id=work_id(h), edition_id=edition_id(h), query_start_ms=h.query_start_ms,
            query_end_ms=h.query_end_ms,
            # Time offset only when the edition is uniquely supported (F03: no time unless unique).
            reference_offset_ms=h.offset_ms if h.edition_index is not None else None,
            supporting_frames=h.support,
        )

    verified = top.support >= th.verified_min_support and frac >= th.verified_min_support_fraction and margin >= th.verified_min_margin
    possible = top.support >= th.possible_min_support

    if montage:
        # Bounded segment-specific evidence; the overall state is at most POSSIBLE_MATCH.
        state = ResultState.POSSIBLE_MATCH if possible else ResultState.NO_CONFIDENT_MATCH
        if state == ResultState.NO_CONFIDENT_MATCH:
            return plain(state, flags)
        return RecognitionResult(state=state, candidate_work_id=work_id(top), candidate_edition_id=edition_id(top),
                                 candidate_episode_id=None, segments=[seg(s) for s in segments],
                                 ambiguity_flags=flags, **common)
    if verified:
        return RecognitionResult(state=ResultState.VERIFIED_MATCH, candidate_work_id=work_id(top),
                                 candidate_edition_id=edition_id(top), candidate_episode_id=None,
                                 segments=[seg(top)], ambiguity_flags=flags, **common)
    if possible:
        return RecognitionResult(state=ResultState.POSSIBLE_MATCH, candidate_work_id=work_id(top),
                                 candidate_edition_id=edition_id(top), candidate_episode_id=None,
                                 segments=[seg(top)], ambiguity_flags=flags + ["WEAK_SUPPORT"], **common)
    return plain(ResultState.NO_CONFIDENT_MATCH, flags)
