"""End-to-end local recognition over a sequence of delivered frames (F04 chain).

capture adapter (simulated) → FrameSelector → quality → describe → retrieve → verify →
decide. Used by the LAB evaluation and by tests. No persistence of frames or descriptors:
per-frame descriptors live only in local variables for the duration of the call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

import cv2
import numpy as np

from . import GENERATOR_VERSION, INDEX_FORMAT_VERSION
from .decision import RESULT_VALIDITY_MS, DecisionThresholds, FrameSummary, decide
from .index.builder import IndexBundle
from .index.descriptors import DescriptorFamily, describe
from .index.retrieval import Candidate, FlatRetriever
from .quality import QualityFlag, assess, normalize, to_gray
from .sampler import FrameSelector
from .schemas import RecognitionResult, ResultState
from .verify import Hypothesis, verify


@dataclass
class Delivered:
    timestamp_ms: int
    frame_bgr: np.ndarray


def recognise(
    scan_id: str,
    generation: int,
    deliveries: Iterable[Delivered],
    retriever: FlatRetriever,
    now_monotonic_ms: int,
    thresholds: DecisionThresholds = DecisionThresholds(),
    selector: Optional[FrameSelector] = None,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> Tuple[RecognitionResult, List[Hypothesis], FrameSummary]:
    bundle: IndexBundle = retriever.bundle
    sel = selector or FrameSelector()
    summary = FrameSummary()
    per_frame: List[Tuple[int, List[Candidate]]] = []
    prev_gray = None
    radius = {
        DescriptorFamily.HASH64: thresholds.hash_max_distance,
        DescriptorFamily.THUMB32: thresholds.thumb32_max_distance,
        DescriptorFamily.THUMB144: thresholds.thumb144_max_distance,
    }[bundle.family]

    for d in deliveries:
        if is_cancelled():
            break
        summary.offered += 1
        if not sel.offer(d.timestamp_ms):
            continue  # OS buffer released immediately by the adapter
        try:
            frame = normalize(d.frame_bgr)
            rep = assess(frame, prev_gray)
            summary.selected += 1
            summary.flags.extend(rep.flags)
            if rep.unusable_feed:
                summary.unusable_feed += 1
                continue
            if not rep.qualified:
                continue
            summary.qualified += 1
            prev_gray = to_gray(frame)
            desc = describe(frame, bundle.family)
            cands = retriever.search(desc, top_k=thresholds.top_k, max_distance=radius)
            if thresholds.mirror_invariant:
                # Also search the horizontally flipped query; keep the closer hit per locator.
                flipped = retriever.search(describe(cv2.flip(frame, 1), bundle.family), top_k=thresholds.top_k, max_distance=radius)
                best = {}
                for c in list(cands) + list(flipped):
                    key = c.locator
                    if key not in best or c.distance < best[key].distance:
                        best[key] = c
                cands = sorted(best.values(), key=lambda c: c.distance)[: thresholds.top_k]
            per_frame.append((d.timestamp_ms, cands))
        finally:
            sel.release()
    sel.close()

    if is_cancelled():
        # Cancellation wins: discard per-frame evidence, publish nothing but CANCELLED.
        per_frame.clear()
        result = RecognitionResult(
            scan_id=scan_id, cancellation_generation=generation, state=ResultState.CANCELLED,
            candidate_work_id=None, candidate_edition_id=None, candidate_episode_id=None, segments=[],
            ambiguity_flags=["CANCELLED_DURING_WORK"], generator_version=GENERATOR_VERSION,
            index_format_version=INDEX_FORMAT_VERSION, calibration_version=thresholds.calibration_version,
            calibration_status=thresholds.calibration_status, local_entitlement_recheck="NOT_REQUIRED",
            created_at_monotonic_ms=now_monotonic_ms, expires_at_monotonic_ms=now_monotonic_ms + RESULT_VALIDITY_MS,
            validity_clock_basis="monotonic")
        return result, [], summary
    hyps = verify(per_frame, int(bundle.sampling_interval_s * 1000))
    result = decide(scan_id, generation, hyps, summary, bundle, now_monotonic_ms, thresholds)
    return result, hyps, summary
