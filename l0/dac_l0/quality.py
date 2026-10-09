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


def crop_black_bars(frame_bgr: np.ndarray, thresh: int = 16, min_keep: float = 0.5) -> np.ndarray:
    """Remove uniform near-black letterbox/pillarbox bars, then rescale to 640x360.

    Applied identically to references and queries (PREPROCESSING_VERSION prep-2) so that
    letterboxed editions and letterboxed queries describe the same picture area. Rows or
    columns are cut only from the outside in and only while their max luma stays below
    `thresh`; at least `min_keep` of each dimension is always kept.
    """
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    row_dark = g.max(axis=1) < thresh
    col_dark = g.max(axis=0) < thresh
    top = 0
    while top < h and row_dark[top]:
        top += 1
    bot = h
    while bot > top and row_dark[bot - 1]:
        bot -= 1
    left = 0
    while left < w and col_dark[left]:
        left += 1
    right = w
    while right > left and col_dark[right - 1]:
        right -= 1
    if (bot - top) < min_keep * h or (right - left) < min_keep * w:
        return frame_bgr  # mostly dark: leave untouched; quality checks will flag it
    if (top, bot, left, right) == (0, h, 0, w):
        return frame_bgr
    return cv2.resize(frame_bgr[top:bot, left:right], (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)


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
