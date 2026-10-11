"""DAC-DHASH-v1: a platform-exact 64-bit difference hash (P04-T08 preparation).

The LAB descriptor HASH64 uses OpenCV Gaussian blur and INTER_AREA resizing, which a Kotlin
or Swift engine cannot reproduce bit for bit. DAC-DHASH-v1 is defined with integer arithmetic
only, so Python, Kotlin and Swift produce identical bits (checked by golden vectors):

 1. Luma per pixel: Y = (77·R + 150·G + 29·B + 128) >> 8           (integer BT.601 approx.)
 2. 9×8 area means: column cell i spans x ∈ [⌊i·W/9⌋, ⌊(i+1)·W/9⌋), row cell j spans
    y ∈ [⌊j·H/8⌋, ⌊(j+1)·H/8⌋); mean = ⌊sum / count⌋.
 3. For each row j and column i in 0..7: bit = mean[j][i+1] > mean[j][i]; bits are taken
    row-major, most significant bit first, giving one unsigned 64-bit value.

Status: CANDIDATE. Not used by the LAB pipeline; adopting it for packs is a method change
that needs new calibration and a new sealed evaluation family.
"""
from __future__ import annotations

import numpy as np

SPEC = "DAC-DHASH-v1"


def luma_u8(rgb: np.ndarray) -> np.ndarray:
    """rgb: HxWx3 uint8 in R,G,B order."""
    r = rgb[:, :, 0].astype(np.int32)
    g = rgb[:, :, 1].astype(np.int32)
    b = rgb[:, :, 2].astype(np.int32)
    return ((77 * r + 150 * g + 29 * b + 128) >> 8).astype(np.int32)


def cell_means(y: np.ndarray, gx: int, gy: int) -> np.ndarray:
    """Integer area means on a gx×gy grid: cell i spans [⌊i·W/gx⌋, ⌊(i+1)·W/gx⌋)."""
    h, w = y.shape
    if w < gx or h < gy:
        raise ValueError("frame too small")
    means = np.zeros((gy, gx), dtype=np.int64)
    for j in range(gy):
        y0, y1 = (j * h) // gy, ((j + 1) * h) // gy
        for i in range(gx):
            x0, x1 = (i * w) // gx, ((i + 1) * w) // gx
            cell = y[y0:y1, x0:x1]
            means[j, i] = int(cell.sum()) // cell.size
    return means


def dhash_luma(y: np.ndarray) -> int:
    """DAC-DHASH-v1 on an integer luma array."""
    means = cell_means(y, 9, 8)
    v = 0
    for j in range(8):
        for i in range(8):
            v = (v << 1) | int(means[j, i + 1] > means[j, i])
    return v


def dac_dhash_v1(rgb: np.ndarray) -> int:
    return dhash_luma(luma_u8(rgb))


# ------------------------------------------------------------------ DAC-CROP-v1
CROP_SPEC = "DAC-CROP-v1"
BORDER_DARK_MAX = 16      # a line whose max luma is below this is dark border
BORDER_FLAT_RANGE = 8     # a line whose (max - min) luma is at most this is flat border


def _trim(flags) -> tuple:
    lo, hi = 0, len(flags)
    while lo < hi and flags[lo]:
        lo += 1
    while hi > lo and flags[hi - 1]:
        hi -= 1
    return lo, hi


def crop_rect(y: np.ndarray) -> tuple:
    """Integer border crop. Rows then columns, outside-in, two passes. A line is border when
    max < BORDER_DARK_MAX or (max - min) <= BORDER_FLAT_RANGE over the current region.
    At least 40 % of each dimension is kept (10·kept ≥ 4·full), else the full frame.
    Returns (top, bottom, left, right), half-open."""
    h, w = y.shape
    top, bot, left, right = 0, h, 0, w
    for _ in range(2):
        reg = y[top:bot, left:right]
        if reg.size == 0:
            break
        mx, mn = reg.max(axis=1), reg.min(axis=1)
        t, b = _trim((mx < BORDER_DARK_MAX) | (mx - mn <= BORDER_FLAT_RANGE))
        top, bot = top + t, top + b
        reg = y[top:bot, left:right]
        if reg.size == 0:
            break
        mx, mn = reg.max(axis=0), reg.min(axis=0)
        l, r = _trim((mx < BORDER_DARK_MAX) | (mx - mn <= BORDER_FLAT_RANGE))
        left, right = left + l, left + r
    if 10 * (bot - top) < 4 * h or 10 * (right - left) < 4 * w:
        return 0, h, 0, w
    return top, bot, left, right


# ------------------------------------------------------------------ DAC-QUAL-v1
QUAL_SPEC = "DAC-QUAL-v1"


def quality_v1(region: np.ndarray, prev_means):
    """Integer quality flags on 16×9 cell means of the cropped region.
    BLANK: max mean < 12. FLAT: max - min < 6. STATIC: every mean within ±1 of the previous
    qualified frame's means. Otherwise OK. Returns (flag, means)."""
    m = cell_means(region, 16, 9)
    if int(m.max()) < 12:
        return "BLANK", m
    if int(m.max() - m.min()) < 6:
        return "FLAT", m
    if prev_means is not None and int(np.abs(m - prev_means).max()) <= 1:
        return "STATIC", m
    return "OK", m


def exact_describe(rgb: np.ndarray, mirrored: bool = False) -> int:
    """Device descriptor: luma → DAC-CROP-v1 rectangle → DAC-DHASH-v1 (optionally mirrored)."""
    y = luma_u8(rgb)
    t, b, l, r = crop_rect(y)
    reg = y[t:b, l:r]
    return dhash_luma(reg[:, ::-1] if mirrored else reg)


class XorShift32:
    """Deterministic test-frame source shared with the Kotlin/Swift golden tests."""

    def __init__(self, seed: int):
        self.s = (seed & 0xFFFFFFFF) or 0x9E3779B9

    def next(self) -> int:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s & 0xFFFFFFFF
        return self.s


def test_frame(seed: int, w: int, h: int) -> np.ndarray:
    """Smooth gradient + a seeded rectangle + low-amplitude noise, consumed in y→x→channel order."""
    rng = XorShift32(seed)
    rx, ry = rng.next() % w, rng.next() % h
    rw, rh = 1 + rng.next() % (w // 2), 1 + rng.next() % (h // 2)
    col = (rng.next() & 255, rng.next() & 255, rng.next() & 255)
    out = np.zeros((h, w, 3), dtype=np.uint8)
    for yy in range(h):
        for xx in range(w):
            inside = rx <= xx < rx + rw and ry <= yy < ry + rh
            for ch in range(3):
                base = col[ch] if inside else ((xx * 255) // max(1, w - 1) + (yy * 255) // max(1, h - 1) * (ch + 1)) & 255
                noise = (rng.next() >> 28) - 8  # −8..7
                out[yy, xx, ch] = max(0, min(255, base + noise))
    return out


GOLDEN_SIZES = [(9, 8), (16, 9), (64, 36), (97, 53), (160, 90), (320, 180)]


def write_golden(path, seeds=range(1, 8)) -> None:
    lines = [f"# {SPEC} golden vectors: X <seed> <width> <height> <hash hex>; generated by l0/dac_l0/index/exact.py"]
    for seed in seeds:
        for (w, h) in GOLDEN_SIZES:
            lines.append(f"X {seed} {w} {h} {dac_dhash_v1(test_frame(seed, w, h)):016x}")
    from pathlib import Path

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    import sys

    write_golden(sys.argv[1])
    print("wrote", sys.argv[1])


def content_frame(seed: int, w: int, h: int, bx: int = 16, by: int = 9) -> np.ndarray:
    """Discriminative test content: a bx×by grid of seeded random colour blocks (block size
    w//bx × h//by, remainder filled by the last block) plus ±8 noise. Consumption order:
    block colours row-major (3 draws each), then per-pixel noise y→x→channel."""
    rng = XorShift32(seed)
    cols = [[(rng.next() & 255, rng.next() & 255, rng.next() & 255) for _ in range(bx)] for _ in range(by)]
    out = np.zeros((h, w, 3), dtype=np.uint8)
    bw, bh = max(1, w // bx), max(1, h // by)
    for yy in range(h):
        cy = min(by - 1, yy // bh)
        for xx in range(w):
            cx = min(bx - 1, xx // bw)
            for ch in range(3):
                v = cols[cy][cx][ch] + (rng.next() >> 28) - 8
                out[yy, xx, ch] = max(0, min(255, v))
    return out
