"""Frame descriptors and the 16-byte locator (F05 capacity table rows).

Families (payload bytes per vector = descriptor + 16 B locator):
- HASH64   : 64-bit difference hash          →  8 + 16 = 24 B
- THUMB32  : 8x4 grey thumbnail (uint8)      → 32 + 16 = 48 B  (table row "48")
- THUMB144 : 16x9 grey thumbnail (uint8)     → 144 + 16 = 160 B (closest to the 144 B row)
- THUMB512 : 32x16 grey thumbnail (uint8)    → 512 + 16 = 528 B (the 528 B row)
- DACDHASH : DAC-CROP-v1 + DAC-DHASH-v1, integer-exact (device engine) → 8 + 16 = 24 B
"""
from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

import cv2
import numpy as np

LOCATOR_BYTES = 16
_LOCATOR_FMT = "<IHIHI"  # work u32, edition u16, t_ms u32, segment u16, reserved u32 = 16 B
assert struct.calcsize(_LOCATOR_FMT) == LOCATOR_BYTES


class DescriptorFamily(str, enum.Enum):
    HASH64 = "HASH64"
    THUMB32 = "THUMB32"
    THUMB144 = "THUMB144"
    THUMB512 = "THUMB512"
    DACDHASH = "DACDHASH"

    @property
    def descriptor_bytes(self) -> int:
        return {"HASH64": 8, "THUMB32": 32, "THUMB144": 144, "THUMB512": 512, "DACDHASH": 8}[self.value]

    @property
    def is_hash(self) -> bool:
        """64-bit hashes compared by Hamming distance."""
        return self.value in ("HASH64", "DACDHASH")

    @property
    def vector_bytes(self) -> int:
        return self.descriptor_bytes + LOCATOR_BYTES


@dataclass(frozen=True)
class Locator:
    work_index: int
    edition_index: int
    t_ms: int
    segment: int = 0
    reserved: int = 0

    def pack(self) -> bytes:
        return struct.pack(_LOCATOR_FMT, self.work_index, self.edition_index, self.t_ms, self.segment, self.reserved)

    @classmethod
    def unpack(cls, b: bytes) -> "Locator":
        if len(b) != LOCATOR_BYTES:
            raise ValueError("locator must be 16 bytes")
        return cls(*struct.unpack(_LOCATOR_FMT, b))


def _gray_small(frame_bgr: np.ndarray, w: int, h: int) -> np.ndarray:
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
    # Slight blur before downsampling stabilises the hash under compression/rescale.
    g = cv2.GaussianBlur(g, (5, 5), 0)
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_AREA)


def dhash64(frame_bgr: np.ndarray) -> int:
    s = _gray_small(frame_bgr, 9, 8).astype(np.int16)
    bits = (s[:, 1:] > s[:, :-1]).ravel()  # 64 bits, MSB first
    return int.from_bytes(np.packbits(bits).tobytes(), "big")


def dhash64_bytes(frame_bgr: np.ndarray) -> bytes:
    return dhash64(frame_bgr).to_bytes(8, "little")


def thumb_bytes(frame_bgr: np.ndarray, w: int, h: int) -> bytes:
    s = _gray_small(frame_bgr, w, h)
    # Normalise brightness/contrast so colour shifts and gamma changes matter less.
    s = s.astype(np.float32)
    s = (s - s.mean()) / (s.std() + 1e-3)
    s = np.clip(s * 40.0 + 128.0, 0, 255).astype(np.uint8)
    return s.tobytes()


def describe(frame_bgr: np.ndarray, family: DescriptorFamily) -> bytes:
    if family == DescriptorFamily.DACDHASH:
        from .exact import exact_describe  # integer-exact device path; no OpenCV preprocessing

        return exact_describe(np.ascontiguousarray(frame_bgr[:, :, 2::-1])).to_bytes(8, "little")
    from ..quality import crop_black_bars  # local import avoids a cycle

    frame_bgr = crop_black_bars(frame_bgr)
    if family == DescriptorFamily.HASH64:
        return dhash64_bytes(frame_bgr)
    if family == DescriptorFamily.THUMB32:
        return thumb_bytes(frame_bgr, 8, 4)
    if family == DescriptorFamily.THUMB144:
        return thumb_bytes(frame_bgr, 16, 9)
    if family == DescriptorFamily.THUMB512:
        return thumb_bytes(frame_bgr, 32, 16)
    raise ValueError(family)


def hamming64(a: np.ndarray, b: np.uint64) -> np.ndarray:
    """Hamming distances between an array of uint64 and a scalar uint64."""
    x = np.bitwise_xor(a, np.uint64(b))
    return np.bitwise_count(x).astype(np.int32)
