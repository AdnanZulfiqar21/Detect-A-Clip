"""Minimal quality / eligibility checks and bounded normalisation (P04-T01).

These heuristics decide whether a frame is usable signal. They never certify privacy
and never classify public versus private content (roadmap F02: filtering is not a
boundary). UI_LIKE is a usability flag only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

from .sampler import FRAME_H, FRAME_W


class QualityFlag:
    OK = "OK"
    BLANK = "BLANK"            # near-black / near-uniform: unusable (UNSUPPORTED_CAPTURE candidate)
    FLAT = "FLAT"              # very low variance but not black
    STATIC = "STATIC"          # no change vs previous selected frame
    UI_LIKE = "UI_LIKE"        # flat regions + many axis-aligned edges; probably an app UI, not video
    LOW_DETAIL = "LOW_DETAIL"  # too little gradient energy to describe


@dataclass
class QualityReport:
    flags: List[str] = field(default_factory=list)
    mean_luma: float = 0.0
    std_luma: float = 0.0
    edge_energy: float = 0.0
    axis_edge_ratio: float = 0.0
    motion_vs_prev: Optional[float] = None

    @property
    def qualified(self) -> bool:
        return self.flags == [QualityFlag.OK]

    @property
    def unusable_feed(self) -> bool:
        return QualityFlag.BLANK in self.flags


def normalize(frame_bgr: np.ndarray) -> np.ndarray:
    """Bounded normalisation to a 640x360-equivalent BGR frame (letterbox-preserving resize)."""
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] not in (3, 4):
        raise ValueError("expected HxWx3 or HxWx4 frame")
    if frame_bgr.shape[2] == 4:
        frame_bgr = frame_bgr[:, :, :3]
    h, w = frame_bgr.shape[:2]
    if (w, h) == (FRAME_W, FRAME_H):
        return np.ascontiguousarray(frame_bgr)
    interp = cv2.INTER_AREA if w > FRAME_W else cv2.INTER_LINEAR
    return cv2.resize(frame_bgr, (FRAME_W, FRAME_H), interpolation=interp)


def _trim(flags: np.ndarray) -> tuple:
    lo, hi = 0, len(flags)
    while lo < hi and flags[lo]:
        lo += 1
    while hi > lo and flags[hi - 1]:
        hi -= 1
    return lo, hi


def crop_uniform_borders(frame_bgr: np.ndarray, dark_thresh: int = 16, flat_std: float = 3.0, min_keep: float = 0.4) -> np.ndarray:
    """Remove uniform outer borders, then rescale to 640x360 (PREPROCESSING prep-3).

    A border row/column is removed when it is near-black (letterbox/pillarbox) or has almost
    no luma variation (a flat app background around a picture-in-picture or scaled player).
    Rows and columns are trimmed alternately, outside-in, twice, so a uniform header bar
    followed by a flat background is removed before columns are measured. Applied
    identically to references and queries. At least `min_keep` of each dimension is kept;
    otherwise the frame is returned unchanged (quality checks flag mostly-flat frames).
    """
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    top, bot, left, right = 0, h, 0, w
    for _ in range(2):
        reg = g[top:bot, left:right]
        if reg.size == 0:
            break
        rows = (reg.max(axis=1) < dark_thresh) | (reg.std(axis=1) < flat_std)
        t, b = _trim(rows)
        top, bot = top + t, top + b
        reg = g[top:bot, left:right]
        if reg.size == 0:
            break
        cols = (reg.max(axis=0) < dark_thresh) | (reg.std(axis=0) < flat_std)
        l, r = _trim(cols)
        left, right = left + l, left + r
    if (bot - top) < min_keep * h or (right - left) < min_keep * w:
        return frame_bgr
    if (top, bot, left, right) == (0, h, 0, w):
        return frame_bgr
    return cv2.resize(frame_bgr[top:bot, left:right], (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)


# Backwards-compatible name used by descriptors.describe().
crop_black_bars = crop_uniform_borders


def to_gray(frame_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)


def assess(frame_bgr: np.ndarray, prev_gray: Optional[np.ndarray] = None) -> QualityReport:
    """Return quality flags for a normalised frame."""
    g = to_gray(frame_bgr)
    rep = QualityReport()
    rep.mean_luma = float(g.mean())
    rep.std_luma = float(g.std())

    if rep.mean_luma < 10.0 and rep.std_luma < 6.0:
        rep.flags.append(QualityFlag.BLANK)
    elif rep.std_luma < 6.0:
        rep.flags.append(QualityFlag.FLAT)

    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    rep.edge_energy = float(mag.mean())
    if rep.edge_energy < 2.0 and QualityFlag.BLANK not in rep.flags and QualityFlag.FLAT not in rep.flags:
        rep.flags.append(QualityFlag.LOW_DETAIL)

    # Axis-aligned edge ratio: UI screens have long perfectly horizontal/vertical edges and
    # large flat regions; natural video does not. Heuristic, not a privacy classifier.
    strong = mag > 40.0
    if strong.sum() > 200:
        ax = np.abs(gx[strong])
        ay = np.abs(gy[strong])
        axis_aligned = ((ax < 0.15 * ay) | (ay < 0.15 * ax)).mean()
        rep.axis_edge_ratio = float(axis_aligned)
        # Fraction of pixels that sit in large flat regions (quantised luma mode share).
        hist = np.bincount((g // 8).ravel(), minlength=32)
        flat_share = float(hist.max() / g.size)
        # Thresholds chosen on the synthetic fixtures (see tests); weak by design: flags
        # 4 of 7 synthetic screen classes and none of the synthetic works/natural scenes.
        if axis_aligned > 0.55 and flat_share > 0.5 and strong.sum() > 3000:
            rep.flags.append(QualityFlag.UI_LIKE)

    if prev_gray is not None and prev_gray.shape == g.shape:
        rep.motion_vs_prev = float(np.abs(g.astype(np.int16) - prev_gray.astype(np.int16)).mean())
        if rep.motion_vs_prev < 0.5:
            rep.flags.append(QualityFlag.STATIC)

    if not rep.flags:
        rep.flags.append(QualityFlag.OK)
    return rep
