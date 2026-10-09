"""Procedural synthetic "works", editions, query transforms, negatives and private screens.

Everything is rendered from a seed with numpy/OpenCV. Assets are *virtual*: a frame at
time t is a pure function of (generator version, seed, parameters, t). Rendered media is
never required to exist on disk, which keeps binaries out of the repository while
keeping provenance reproducible (content hashes in the manifest).

Visibly synthetic: every work carries a title card "SYNTHETIC WORK nnn" and uses only
abstract shapes. Labels are synthetic and must never be presented as real titles.
"""
from __future__ import annotations

import enum
import functools
import hashlib
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .. import GENERATOR_VERSION
from ..sampler import FRAME_H, FRAME_W

W, H = FRAME_W, FRAME_H
NATIVE_FPS = 10
HASH_BASIS_FPS = 2  # content hash is computed over frames sampled at this rate


class EditionKind(str, enum.Enum):
    """Editions are different *cuts* of the same work (gallery-side)."""

    THEATRICAL = "E0_THEATRICAL"      # the base cut
    EXTENDED = "E1_EXTENDED"          # 6 s extra scene inserted at a seeded point
    BROADCAST = "E2_BROADCAST"        # one 8 s scene removed, letterboxed 16:9→2.35:1


class QueryTransform(str, enum.Enum):
    """Query-side edits (the "edited" evaluation family)."""

    NONE = "NONE"
    MIRRORED = "MIRRORED"
    CROPPED = "CROPPED"
    CAPTIONED = "CAPTIONED"
    COMPRESSED = "COMPRESSED"
    COLOR_SHIFT = "COLOR_SHIFT"
    SPEED_110 = "SPEED_110"
    ROTATED_3DEG = "ROTATED_3DEG"
    LETTERBOXED = "LETTERBOXED"


EDITED_TRANSFORMS = [t for t in QueryTransform if t != QueryTransform.NONE]


def _rng(*parts) -> np.random.Generator:
    key = "|".join(str(p) for p in parts).encode()
    seed = int.from_bytes(hashlib.sha256(key).digest()[:8], "little")
    return np.random.default_rng(seed)


# ----------------------------------------------------------------------------- works


@dataclass(frozen=True)
class SceneSpec:
    start_s: float
    end_s: float
    palette: Tuple[Tuple[int, int, int], Tuple[int, int, int]]
    shapes: Tuple[Tuple[int, float, float, float, float, float, float, Tuple[int, int, int], int], ...]
    # shape tuple: (kind, cx, cy, ax, ay, fx, fy, color, size)
    texture_key: Tuple[int, int] = (0, 0)  # (work seed, scene index) → cached background texture
    pan_px_s: Tuple[float, float] = (0.0, 0.0)  # slow camera pan, film-like (≤ ~30 px/s)


@dataclass(frozen=True)
class SynthWork:
    work_index: int
    seed: int
    duration_s: float = 60.0

    @property
    def work_id(self) -> str:
        return f"SW{self.work_index:03d}"

    @property
    def synthetic_title(self) -> str:
        return f"SYNTHETIC WORK {self.work_index:03d}"

    def scenes(self) -> List[SceneSpec]:
        return _scenes_cached(self.seed, self.duration_s)

    def render_frame(self, t_s: float) -> np.ndarray:
        """Render the THEATRICAL frame at time t (seconds). Deterministic."""
        if t_s < 0 or t_s >= self.duration_s:
            raise ValueError("t out of range")
        return _render_work_frame(self.scenes(), self.synthetic_title, self.work_id, self.duration_s, t_s)


# Film-like motion budget (synth-gen-2): shapes move ≤ ~70 px/s, background pans ≤ ~30 px/s.
# synth-gen-1 used up to ~480 px/s object motion and a near-identical gradient background in
# every work, which made every frame descriptor non-discriminative (see DECISIONS ED-08).
_PAN_MARGIN = 220


@functools.lru_cache(maxsize=256)
def _scenes_cached(seed: int, duration_s: float) -> List[SceneSpec]:
    rng = _rng(GENERATOR_VERSION, "scenes", seed)
    scenes: List[SceneSpec] = []
    t = 0.0
    i = 0
    while t < duration_s:
        length = float(rng.uniform(5.0, 12.0))
        end = min(duration_s, t + length)
        p1 = tuple(int(v) for v in rng.integers(10, 140, size=3))
        p2 = tuple(int(v) for v in rng.integers(80, 240, size=3))
        n_shapes = int(rng.integers(3, 7))
        shapes = []
        for _ in range(n_shapes):
            kind = int(rng.integers(0, 3))
            cx, cy = float(rng.uniform(0.15, 0.85)), float(rng.uniform(0.15, 0.85))
            ax, ay = float(rng.uniform(0.03, 0.15)), float(rng.uniform(0.03, 0.12))
            fx, fy = float(rng.uniform(0.02, 0.12)), float(rng.uniform(0.02, 0.12))
            color = tuple(int(v) for v in rng.integers(40, 255, size=3))
            size = int(rng.integers(18, 70))
            shapes.append((kind, cx, cy, ax, ay, fx, fy, color, size))
        pan = (float(rng.uniform(-18.0, 18.0)), float(rng.uniform(-8.0, 8.0)))
        scenes.append(SceneSpec(t, end, (p1, p2), tuple(shapes), (seed, i), pan))
        t = end
        i += 1
    return scenes


@functools.lru_cache(maxsize=512)
def _scene_texture(work_seed: int, scene_index: int, p1: Tuple[int, int, int], p2: Tuple[int, int, int]) -> np.ndarray:
    """Seeded multi-octave value-noise texture mapped between the scene's palette colours.
    Larger than the frame so a slow pan never runs off the edge."""
    rng = _rng(GENERATOR_VERSION, "texture", work_seed, scene_index)
    th, tw = H + 2 * _PAN_MARGIN, W + 2 * _PAN_MARGIN
    acc = np.zeros((th, tw), np.float32)
    for octave, (gh, gw, amp) in enumerate([(4, 6, 1.0), (8, 12, 0.5), (16, 24, 0.25)]):
        grid = rng.random((gh, gw), dtype=np.float32)
        acc += amp * cv2.resize(grid, (tw, th), interpolation=cv2.INTER_CUBIC)
    acc = (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)
    c1 = np.array(p1, np.float32)
    c2 = np.array(p2, np.float32)
    tex = c1[None, None, :] * (1 - acc[..., None]) + c2[None, None, :] * acc[..., None]
    return tex.clip(0, 255).astype(np.uint8)


def _render_work_frame(scenes: List[SceneSpec], synthetic_title: str, work_id: str, duration_s: float, t_s: float) -> np.ndarray:
    scene = next(s for s in scenes if s.start_s <= t_s < s.end_s)
    tex = _scene_texture(scene.texture_key[0], scene.texture_key[1], scene.palette[0], scene.palette[1])
    local_t = t_s - scene.start_s
    ox = int(round(_PAN_MARGIN + max(-_PAN_MARGIN, min(_PAN_MARGIN, scene.pan_px_s[0] * local_t))))
    oy = int(round(_PAN_MARGIN + max(-_PAN_MARGIN, min(_PAN_MARGIN, scene.pan_px_s[1] * local_t))))
    frame = np.ascontiguousarray(tex[oy:oy + H, ox:ox + W])
    # Shapes with seeded, slow sinusoidal kinematics.
    for kind, cx, cy, ax, ay, fx, fy, color, size in scene.shapes:
        x = int((cx + ax * math.sin(2 * math.pi * fx * t_s)) * W)
        y = int((cy + ay * math.cos(2 * math.pi * fy * t_s)) * H)
        if kind == 0:
            cv2.circle(frame, (x, y), size, color, -1, lineType=cv2.LINE_AA)
        elif kind == 1:
            cv2.rectangle(frame, (x - size, y - size // 2), (x + size, y + size // 2), color, -1)
        else:
            pts = np.array([[x, y - size], [x + size, y + size], [x - size, y + size]], np.int32)
            cv2.fillPoly(frame, [pts], color, lineType=cv2.LINE_AA)
    # Visible synthetic title card for the first 2 s and a persistent corner tag.
    if t_s < 2.0:
        cv2.rectangle(frame, (60, 140), (W - 60, 220), (0, 0, 0), -1)
        cv2.putText(frame, synthetic_title, (80, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    cv2.putText(frame, f"SYNTH {work_id}", (8, H - 8), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), 1)
    return frame


@dataclass(frozen=True)
class Edition:
    work: SynthWork
    kind: EditionKind

    @property
    def edition_id(self) -> str:
        return self.kind.value

    @property
    def asset_id(self) -> str:
        return f"{self.work.work_id}-{self.edition_id}"

    # Edition time maps. EXTENDED inserts a 6 s scene (a re-coloured replay of an earlier
    # moment) at a seeded point; BROADCAST removes an 8 s window and letterboxes.
    def _insert_point(self) -> float:
        return float(_rng(GENERATOR_VERSION, "ext", self.work.seed).uniform(15.0, 40.0))

    def _cut_window(self) -> Tuple[float, float]:
        s = float(_rng(GENERATOR_VERSION, "cut", self.work.seed).uniform(10.0, 45.0))
        return s, s + 8.0

    @property
    def duration_s(self) -> float:
        if self.kind == EditionKind.EXTENDED:
            return self.work.duration_s + 6.0
        if self.kind == EditionKind.BROADCAST:
            return self.work.duration_s - 8.0
        return self.work.duration_s

    def render_frame(self, t_s: float) -> np.ndarray:
        if t_s < 0 or t_s >= self.duration_s:
            raise ValueError("t out of range for edition")
        if self.kind == EditionKind.THEATRICAL:
            return self.work.render_frame(t_s)
        if self.kind == EditionKind.EXTENDED:
            ip = self._insert_point()
            if t_s < ip:
                return self.work.render_frame(t_s)
            if t_s < ip + 6.0:
                # Inserted scene: replay of t∈[2,8) with inverted colours so it is distinct.
                base = self.work.render_frame(2.0 + (t_s - ip))
                return cv2.bitwise_not(base)
            return self.work.render_frame(t_s - 6.0)
        # BROADCAST
        cs, ce = self._cut_window()
        src_t = t_s if t_s < cs else t_s + 8.0
        base = self.work.render_frame(src_t)
        return apply_transform(base, QueryTransform.LETTERBOXED, src_t)


# ------------------------------------------------------------------- query transforms


def apply_transform(frame: np.ndarray, kind: QueryTransform, t_s: float = 0.0) -> np.ndarray:
    if kind == QueryTransform.NONE:
        return frame
    if kind == QueryTransform.MIRRORED:
        return cv2.flip(frame, 1)
    if kind == QueryTransform.CROPPED:
        h, w = frame.shape[:2]
        y0, x0 = int(h * 0.1), int(w * 0.1)
        return cv2.resize(frame[y0:h - y0, x0:w - x0], (w, h), interpolation=cv2.INTER_LINEAR)
    if kind == QueryTransform.CAPTIONED:
        out = frame.copy()
        h, w = out.shape[:2]
        cv2.rectangle(out, (0, h - 56), (w, h), (0, 0, 0), -1)
        cv2.putText(out, "SYNTHETIC CAPTION TEXT LINE", (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        return out
    if kind == QueryTransform.COMPRESSED:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 22])
        assert ok
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if kind == QueryTransform.COLOR_SHIFT:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[:, :, 0] = (hsv[:, :, 0] + 25) % 180
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 0.8, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    if kind == QueryTransform.SPEED_110:
        # Time remap is applied by the caller (see Clip); pixels unchanged here.
        return frame
    if kind == QueryTransform.ROTATED_3DEG:
        h, w = frame.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), 3.0, 1.0)
        return cv2.warpAffine(frame, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if kind == QueryTransform.LETTERBOXED:
        h, w = frame.shape[:2]
        inner_h = int(h * 0.75)
        inner = cv2.resize(frame, (w, inner_h), interpolation=cv2.INTER_AREA)
        out = np.zeros_like(frame)
        y0 = (h - inner_h) // 2
        out[y0:y0 + inner_h] = inner
        return out
    raise ValueError(kind)


@dataclass(frozen=True)
class Clip:
    """A bounded query clip taken from an edition with an optional transform."""

    edition: Edition
    start_s: float
    length_s: float
    transform: QueryTransform = QueryTransform.NONE

    def frame_at(self, rel_t_s: float) -> np.ndarray:
        if rel_t_s < 0 or rel_t_s > self.length_s:
            raise ValueError("rel_t out of clip")
        src_rel = rel_t_s * (1.10 if self.transform == QueryTransform.SPEED_110 else 1.0)
        t = min(self.start_s + src_rel, self.edition.duration_s - 1e-3)
        return apply_transform(self.edition.render_frame(t), self.transform, t)


# ---------------------------------------------------------------- negatives / screens


@dataclass(frozen=True)
class NaturalScene:
    """Unmarked smooth value-noise texture drifting over time. Not in any gallery."""

    index: int
    seed: int
    duration_s: float = 20.0

    @property
    def asset_id(self) -> str:
        return f"NAT{self.index:03d}"

    def render_frame(self, t_s: float) -> np.ndarray:
        rng = _rng(GENERATOR_VERSION, "nat", self.seed)
        small = rng.random((9, 16, 3), dtype=np.float32)
        small2 = rng.random((9, 16, 3), dtype=np.float32)
        a = 0.5 + 0.5 * math.sin(0.4 * t_s)
        mix = (small * (1 - a) + small2 * a)
        img = cv2.resize(mix, (W, H), interpolation=cv2.INTER_CUBIC)
        img = np.roll(img, int(t_s * 25) % W, axis=1)
        return (img * 255).clip(0, 255).astype(np.uint8)


class PrivateScreenKind(str, enum.Enum):
    CHAT = "CHAT"
    PASSWORD_FORM = "PASSWORD_FORM"
    NOTIFICATION_BANNER = "NOTIFICATION_BANNER"  # overlay class (CAP-04)
    INCOMING_CALL = "INCOMING_CALL"
    KEYBOARD = "KEYBOARD"
    SHARE_SHEET = "SHARE_SHEET"
    PIP_WINDOW = "PIP_WINDOW"


_FAKE_WORDS = ["lorem", "ipsum", "dolor", "sit", "amet", "fictus", "nomen", "synth", "testus", "nullus"]


def _fake_text(rng: np.random.Generator, n: int) -> str:
    return " ".join(_FAKE_WORDS[int(i)] for i in rng.integers(0, len(_FAKE_WORDS), size=n))


@dataclass(frozen=True)
class PrivateScreen:
    """Synthetic private/sensitive-looking screens with seeded FICTIONAL text.

    Used only as negative/overlay fixtures (CAP-04, P04-T01). No real private pixels.
    """

    kind: PrivateScreenKind
    seed: int

    @property
    def asset_id(self) -> str:
        return f"PRIV-{self.kind.value}-{self.seed}"

    def render_frame(self, t_s: float = 0.0, underlay: Optional[np.ndarray] = None) -> np.ndarray:
        rng = _rng(GENERATOR_VERSION, "priv", self.kind.value, self.seed)
        frame = underlay.copy() if underlay is not None else np.full((H, W, 3), 245, np.uint8)
        k = self.kind
        if k == PrivateScreenKind.CHAT:
            frame[:] = 245
            y = 40
            for i in range(7):
                left = bool(rng.integers(0, 2))
                txt = _fake_text(rng, int(rng.integers(2, 6)))
                x0 = 20 if left else W - 20 - 12 * len(txt)
                col = (230, 230, 230) if left else (120, 200, 120)
                cv2.rectangle(frame, (x0, y), (x0 + 12 * len(txt), y + 36), col, -1)
                cv2.putText(frame, txt, (x0 + 8, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 1)
                y += 44
        elif k == PrivateScreenKind.PASSWORD_FORM:
            frame[:] = 250
            cv2.putText(frame, "Sign in (SYNTHETIC)", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2)
            for i, label in enumerate(["user", "password"]):
                y = 110 + i * 80
                cv2.rectangle(frame, (40, y), (W - 40, y + 50), (200, 200, 200), 2)
                cv2.putText(frame, label, (50, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (90, 90, 90), 1)
                cv2.putText(frame, "********" if i else _fake_text(rng, 1), (55, y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        elif k == PrivateScreenKind.NOTIFICATION_BANNER:
            cv2.rectangle(frame, (20, 10), (W - 20, 80), (40, 40, 40), -1)
            cv2.putText(frame, "Synthetic App  now", (36, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
            cv2.putText(frame, _fake_text(rng, 5), (36, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        elif k == PrivateScreenKind.INCOMING_CALL:
            frame[:] = (30, 30, 30)
            cv2.circle(frame, (W // 2, 120), 50, (120, 120, 120), -1)
            cv2.putText(frame, "Incoming call (SYNTHETIC)", (W // 2 - 170, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
            cv2.circle(frame, (W // 2 - 120, 300), 36, (60, 60, 220), -1)
            cv2.circle(frame, (W // 2 + 120, 300), 36, (60, 200, 60), -1)
        elif k == PrivateScreenKind.KEYBOARD:
            y0 = H - 150
            cv2.rectangle(frame, (0, y0), (W, H), (210, 210, 210), -1)
            for r in range(3):
                for c in range(10):
                    x = 8 + c * 62
                    y = y0 + 12 + r * 44
                    cv2.rectangle(frame, (x, y), (x + 54, y + 36), (255, 255, 255), -1)
        elif k == PrivateScreenKind.SHARE_SHEET:
            cv2.rectangle(frame, (0, H // 2), (W, H), (235, 235, 235), -1)
            for i in range(5):
                cv2.circle(frame, (70 + i * 120, H // 2 + 70), 30, (150, 150, 150), -1)
            cv2.putText(frame, "Share to (SYNTHETIC)", (20, H // 2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 40), 2)
        elif k == PrivateScreenKind.PIP_WINDOW:
            cv2.rectangle(frame, (W - 220, H - 140), (W - 20, H - 20), (10, 10, 10), -1)
            cv2.putText(frame, "PiP", (W - 150, H - 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2)
        return frame


def blank_frame(level: int = 0) -> np.ndarray:
    return np.full((H, W, 3), level, np.uint8)


# ----------------------------------------------------------------------------- hashing


def content_hash(render, duration_s: float, fps: int = HASH_BASIS_FPS) -> str:
    """SHA-256 over frames sampled at `fps` (BGR uint8, 640x360). Provenance fingerprint."""
    h = hashlib.sha256()
    n = int(math.floor(duration_s * fps))
    for i in range(n):
        f = render(i / fps)
        if f.shape != (H, W, 3):
            raise ValueError("unexpected frame shape")
        h.update(f.tobytes())
    h.update(f"{GENERATOR_VERSION}|{fps}|{n}".encode())
    return h.hexdigest()


def gallery_works(n: int = 20, base_seed: int = 1000) -> List[SynthWork]:
    return [SynthWork(i, base_seed + i) for i in range(n)]


def absent_works(n: int = 10, base_seed: int = 5000, first_index: int = 900) -> List[SynthWork]:
    """Works that are never indexed (unknown-work family). Distinct seeds and IDs."""
    return [SynthWork(first_index + i, base_seed + i) for i in range(n)]
