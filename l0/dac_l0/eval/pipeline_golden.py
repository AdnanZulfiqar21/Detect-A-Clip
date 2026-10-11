"""Golden vectors for the *full* device recognition pipeline (P04-T08 preparation):
delivered frames (100 ms) -> FrameSelector (>=500 ms) -> DAC-CROP-v1 -> DAC-QUAL-v1 ->
DAC-DHASH-v1 (+ mirrored) -> flat retrieval -> merge -> temporal verification -> decision.

Python runs the real `pipeline.extract_evidence` exact path; Kotlin RecognitionSession must
produce the same frame summary and decision. Frames are composed from the shared xorshift
content source plus integer nearest-neighbour scaling (identical rule in both languages):
  src_x = (x * src_w) // dst_w, src_y = (y * src_h) // dst_h.

  python -m dac_l0.eval.pipeline_golden --out ../android/app/src/test/resources/golden_pipeline.txt
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import List, Tuple

import numpy as np

from ..decision import DecisionThresholds, decide
from ..index.builder import IndexBundle, WorkEntry
from ..index.descriptors import DescriptorFamily, Locator
from ..index.exact import content_frame, crop_rect, dhash_luma, luma_u8
from ..index.retrieval import FlatRetriever
from ..pipeline import Delivered, extract_evidence

W, H = 64, 36
REF_STEP_MS = 500
DURATION_MS = 20_000
WORKS = [(0, "SW000", None, None, 10_000), (1, "SW001", None, None, 20_000), (2, "SW002", None, None, 30_000),
         (3, "SW100", "S-P", "E01", 40_000), (4, "SW101", "S-P", "E02", 50_000)]
SHARED_INTRO_MS = 4_000
INTRO_SEED = 90_000


def seed_at(work: int, t_ms: int) -> int:
    seg = t_ms // REF_STEP_MS
    w = WORKS[work]
    if w[2] is not None and t_ms < SHARED_INTRO_MS:
        return INTRO_SEED + seg
    return w[4] + seg


def scale_nearest(img: np.ndarray, nw: int, nh: int) -> np.ndarray:
    h, w = img.shape[:2]
    ys = (np.arange(nh) * h) // nh
    xs = (np.arange(nw) * w) // nw
    return img[ys][:, xs]


def compose(seed: int, variant: str, bright: int) -> np.ndarray:
    """RGB frame. variants: full, letterbox, pillarbox, pip, mirror, black."""
    if variant == "black":
        return np.zeros((H, W, 3), np.uint8)
    c = content_frame(seed, W, H)
    if variant == "full":
        out = c
    elif variant == "mirror":
        out = c[:, ::-1]
    elif variant == "letterbox":
        out = np.zeros((H, W, 3), np.uint8)
        out[5:31] = scale_nearest(c, W, 26)
    elif variant == "pillarbox":
        out = np.zeros((H, W, 3), np.uint8)
        out[:, 8:56] = scale_nearest(c, 48, H)
    elif variant == "pip":
        out = np.full((H, W, 3), 235, np.uint8)
        out[0:5] = 60
        out[9:31, 12:52] = scale_nearest(c, 40, 22)
    else:
        raise ValueError(variant)
    if bright:
        out = np.clip(out.astype(np.int16) + bright, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(out)


def build_pack() -> IndexBundle:
    desc, locs, works = [], [], []
    for wi, wid, series, ep, _ in WORKS:
        works.append(WorkEntry(wi, wid, f"SYNTHETIC {wid}", ["E0_THEATRICAL"], [DURATION_MS / 1000], series, ep, {"en": f"Synthetic {wid}"}, []))
        for t in range(0, DURATION_MS, REF_STEP_MS):
            y = luma_u8(compose(seed_at(wi, t), "full", 0))
            tt, bb, ll, rr = crop_rect(y)
            desc.append(dhash_luma(y[tt:bb, ll:rr]).to_bytes(8, "little"))
            locs.append(Locator(wi, 0, t).pack())
    d = np.frombuffer(b"".join(desc), np.uint8).reshape(-1, 8).copy()
    l = np.frombuffer(b"".join(locs), np.uint8).reshape(-1, 16).copy()
    b = IndexBundle(DescriptorFamily.DACDHASH, REF_STEP_MS / 1000, d, l, works)
    b.indexed_hours = len(desc) * REF_STEP_MS / 3_600_000
    return b


# (name, list of (delivery t_ms, work or -1 absent, source t_ms, variant, brightness))
def queries() -> List[Tuple[str, List[Tuple[int, int, int, str, int]]]]:
    dl = range(0, 8000, 100)
    q = [
        ("full_SW001", [(t, 1, 6_000 + t, "full", 0) for t in dl]),
        ("letterbox_SW002", [(t, 2, 2_000 + t, "letterbox", 0) for t in dl]),
        ("pillarbox_SW000", [(t, 0, 9_000 + t, "pillarbox", 3) for t in dl]),
        ("pip_SW001", [(t, 1, 1_000 + t, "pip", 0) for t in dl]),
        ("mirror_SW002", [(t, 2, 11_000 + t, "mirror", 0) for t in dl]),
        ("absent", [(t, -1, t, "full", 0) for t in dl]),
        ("black_feed", [(t, 0, t, "black", 0) for t in dl]),
        ("static_frame", [(t, 1, 5_000, "full", 0) for t in dl]),
        ("montage_SW000_SW002", [(t, 0 if t < 4000 else 2, (3_000 if t < 4000 else 12_000) + t, "full", 0) for t in dl]),
        ("series_shared_intro", [(t, 3, t // 2, "full", 0) for t in dl]),
        ("series_unique_E02", [(t, 4, 8_000 + t, "full", 0) for t in dl]),
        ("jittered_timestamps_SW000", [(t + (37 if (t // 100) % 3 == 0 else 0), 0, 4_000 + t, "full", 0) for t in dl]),
    ]
    return q


def query_seed(work: int, src_t: int) -> int:
    return 777_000 + src_t // REF_STEP_MS if work < 0 else seed_at(work, src_t)


def write(out: Path) -> None:
    b = build_pack()
    th = replace(DecisionThresholds(dacdhash_max_distance=9.0), mirror_invariant=True, top_k=12)
    retr = FlatRetriever(b)
    L = ["# golden_pipeline v1 — full exact pipeline; generated by l0/dac_l0/eval/pipeline_golden.py",
         f"SIZE {W} {H}",
         "PACKHEX " + b.to_bytes().hex(),
         "TH " + " ".join(str(v) for v in [th.min_qualified_frames, th.verified_min_support, repr(th.verified_min_support_fraction),
                                          th.verified_min_span_ms, repr(th.verified_max_mean_dist_frac), th.verified_min_margin,
                                          th.possible_min_support, th.possible_min_span_ms, repr(th.possible_max_mean_dist_frac),
                                          int(th.possible_on_competition), th.episode_margin, repr(th.dacdhash_max_distance), th.top_k])]
    for name, frames in queries():
        L.append(f"Q {name} {len(frames)}")
        deliveries = []
        for t, wi, src, variant, bright in frames:
            seed = query_seed(wi, src)
            L.append(f"QF {t} {seed} {variant} {bright}")
            deliveries.append(Delivered(t, np.ascontiguousarray(compose(seed, variant, bright)[:, :, ::-1])))  # RGB -> BGR
        hyps, summ, _ = extract_evidence(deliveries, retr, th)
        r = decide("pipe", 1, hyps, summ, b, 0, th)
        segs = "|".join(f"{s.work_id}@{s.edition_id or '-'}@{s.query_start_ms}@{s.query_end_ms}@"
                        f"{'-' if s.reference_offset_ms is None else s.reference_offset_ms}@{s.supporting_frames}" for s in r.segments) or "-"
        L.append(f"S {summ.offered} {summ.selected} {summ.qualified} {summ.unusable_feed}")
        L.append(f"R {r.state.value} {r.candidate_work_id or '-'} {r.candidate_edition_id or '-'} {r.candidate_episode_id or '-'} "
                 f"{','.join(r.ambiguity_flags) or '-'} {segs}")
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    write(Path(ap.parse_args(argv).out))
    print("ok")


if __name__ == "__main__":
    main()
