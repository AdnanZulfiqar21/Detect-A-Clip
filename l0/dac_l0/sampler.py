"""Bounded frame selection (roadmap F05 intake/buffers; CAP-A01 criteria).

OS delivery frequency and selected processing frequency are different. The selector
accepts at most one frame per `min_spacing_ms` (≤2 fps at 500 ms), requires monotonic
timestamps, and bounds the number of app-owned decoded frames including in-flight work.
Surplus deliveries are counted as drops and must be released by the caller immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

FRAME_W, FRAME_H = 640, 360
RGBA_BYTES_PER_FRAME = FRAME_W * FRAME_H * 4  # 921,600 B
MAX_APP_OWNED_FRAMES = 3                      # incl. in-flight → 2,764,800 B ≈ 2.76 MB


class SelectorError(RuntimeError):
    pass


@dataclass
class SelectorStats:
    delivered: int = 0
    selected: int = 0
    dropped_spacing: int = 0
    dropped_buffer_full: int = 0
    rejected_non_monotonic: int = 0
    peak_buffer: int = 0
    selected_timestamps_ms: List[int] = field(default_factory=list)

    def delivery_rate_hz(self, window_ms: int) -> float:
        return self.delivered * 1000.0 / window_ms if window_ms > 0 else 0.0

    def min_gap_ms(self) -> Optional[int]:
        ts = self.selected_timestamps_ms
        if len(ts) < 2:
            return None
        return min(b - a for a, b in zip(ts, ts[1:]))


class FrameSelector:
    """Decides, per delivered frame, whether the app may take ownership of it."""

    def __init__(self, min_spacing_ms: int = 500, max_buffer: int = MAX_APP_OWNED_FRAMES):
        if min_spacing_ms <= 0 or max_buffer <= 0:
            raise ValueError("spacing and buffer must be positive")
        self.min_spacing_ms = min_spacing_ms
        self.max_buffer = max_buffer
        self._last_selected_ms: Optional[int] = None
        self._last_delivered_ms: Optional[int] = None
        self._owned = 0  # decoded frames the app currently owns (queued + in-flight)
        self.stats = SelectorStats()
        self.closed = False

    @property
    def owned(self) -> int:
        return self._owned

    def offer(self, timestamp_ms: int) -> bool:
        """Return True if the caller should take ownership of this frame.

        A False return means the caller must release the OS buffer immediately.
        """
        if self.closed:
            return False
        self.stats.delivered += 1
        if self._last_delivered_ms is not None and timestamp_ms <= self._last_delivered_ms:
            # Non-monotonic timestamps are rejected rather than reordered.
            self.stats.rejected_non_monotonic += 1
            return False
        self._last_delivered_ms = timestamp_ms

        if self._last_selected_ms is not None and timestamp_ms - self._last_selected_ms < self.min_spacing_ms:
            self.stats.dropped_spacing += 1
            return False
        if self._owned >= self.max_buffer:
            self.stats.dropped_buffer_full += 1
            return False

        self._owned += 1
        self.stats.peak_buffer = max(self.stats.peak_buffer, self._owned)
        self._last_selected_ms = timestamp_ms
        self.stats.selected += 1
        self.stats.selected_timestamps_ms.append(timestamp_ms)
        return True

    def release(self) -> None:
        """Caller finished with one owned frame (processed or discarded)."""
        if self._owned <= 0:
            raise SelectorError("release without ownership")
        self._owned -= 1

    def close(self) -> None:
        """Stop intake. Owned frames may still be released; nothing new is accepted."""
        self.closed = True

    def owned_bytes_upper_bound(self) -> int:
        return self._owned * RGBA_BYTES_PER_FRAME
