"""Reproducible index builder (P03-T03) and payload serialisation.

The payload is a flat array of (descriptor || locator) vectors plus a small header.
Everything is derived from authorised assets in the asset manifest only. Build output is
deterministic for a given (generator, preprocessing, family, sampling interval, assets).
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .. import GENERATOR_VERSION, INDEX_FORMAT_VERSION, PREPROCESSING_VERSION
from ..quality import normalize
from ..synth.generator import Edition, EditionKind
from .descriptors import LOCATOR_BYTES, DescriptorFamily, Locator, describe

MAGIC = b"DACL0IDX"
HEADER_FMT = "<8sHHIId"  # magic, version, descriptor_bytes, vector_count, work_count, sampling_interval
HEADER_SIZE = struct.calcsize(HEADER_FMT)
TOTAL_INSTALLED_INDEX_BUDGET_BYTES = 250_000_000  # D10 default; decimal; total, not per pack
MAX_VECTORS = 20_000_000  # parser bound well above anything the budget allows


@dataclass
class WorkEntry:
    work_index: int
    work_id: str
    synthetic_title: str
    editions: List[str]
    durations_s: List[float]
    series_id: Optional[str] = None   # idx-flat-2: work→series/episode hierarchy (P04-T04)
    episode_id: Optional[str] = None


@dataclass
class IndexBundle:
    family: DescriptorFamily
    sampling_interval_s: float
    descriptors: np.ndarray  # (N, D) uint8
    locators: np.ndarray     # (N, 16) uint8
    works: List[WorkEntry]
    build_seconds: float = 0.0
    indexed_hours: float = 0.0
    stats: Dict[str, float] = field(default_factory=dict)

    @property
    def vector_count(self) -> int:
        return int(self.descriptors.shape[0])

    @property
    def payload_bytes(self) -> int:
        return HEADER_SIZE + self.vector_count * (self.family.descriptor_bytes + LOCATOR_BYTES) + len(self.metadata_json())

    @property
    def title_count(self) -> int:
        return len(self.works)

    def metadata_json(self) -> bytes:
        meta = {
            "index_format_version": INDEX_FORMAT_VERSION,
            "generator_version": GENERATOR_VERSION,
            "preprocessing_version": PREPROCESSING_VERSION,
            "family": self.family.value,
            "works": [w.__dict__ for w in self.works],
        }
        return json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()

    def hash_u64(self) -> np.ndarray:
        if self.family != DescriptorFamily.HASH64:
            raise ValueError("not a hash index")
        return np.ascontiguousarray(self.descriptors).view("<u8").ravel()

    def bytes_per_reference_hour(self) -> float:
        return self.payload_bytes / self.indexed_hours if self.indexed_hours > 0 else float("nan")

    # ------------------------------------------------------------------ serialisation
    def to_bytes(self) -> bytes:
        meta = self.metadata_json()
        header = struct.pack(HEADER_FMT, MAGIC, 1, self.family.descriptor_bytes, self.vector_count, len(self.works), self.sampling_interval_s)
        body = np.concatenate([self.descriptors, self.locators], axis=1).tobytes() if self.vector_count else b""
        return header + struct.pack("<I", len(meta)) + meta + body

    @classmethod
    def from_bytes(cls, data: bytes, max_payload_bytes: int = TOTAL_INSTALLED_INDEX_BUDGET_BYTES) -> "IndexBundle":
        """Untrusted parse with bounds (SEC-01). Raises ValueError on any inconsistency."""
        if len(data) > max_payload_bytes:
            raise ValueError("payload exceeds installed index budget")
        if len(data) < HEADER_SIZE + 4:
            raise ValueError("payload too short")
        magic, version, dbytes, n, nworks, interval = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
        if magic != MAGIC or version != 1:
            raise ValueError("bad magic/version")
        family = next((f for f in DescriptorFamily if f.descriptor_bytes == dbytes), None)
        if family is None:
            raise ValueError("unknown descriptor size")
        if not (0 <= n <= MAX_VECTORS) or not (0 <= nworks <= 1_000_000):
            raise ValueError("count out of bounds")
        if not (0.1 <= interval <= 60.0):
            raise ValueError("sampling interval out of bounds")
        (meta_len,) = struct.unpack("<I", data[HEADER_SIZE:HEADER_SIZE + 4])
        if meta_len > 64 * 1024 * 1024:
            raise ValueError("metadata too large")
        off = HEADER_SIZE + 4
        meta_raw = data[off:off + meta_len]
        if len(meta_raw) != meta_len:
            raise ValueError("truncated metadata")
        off += meta_len
        try:
            meta = json.loads(meta_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"metadata not valid JSON: {e}") from e
        if meta.get("index_format_version") != INDEX_FORMAT_VERSION:
            raise ValueError("incompatible index format version")
        if meta.get("family") != family.value:
            raise ValueError("metadata/header family mismatch")
        works_raw = meta.get("works")
        if not isinstance(works_raw, list) or len(works_raw) != nworks:
            raise ValueError("work table mismatch")
        works = []
        for w in works_raw:
            if not isinstance(w, dict) or set(w) != {"work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id"}:
                raise ValueError("bad work entry")
            works.append(WorkEntry(**w))
        vec = dbytes + LOCATOR_BYTES
        body = data[off:]
        if len(body) != n * vec:
            raise ValueError("body length mismatch")
        arr = np.frombuffer(body, dtype=np.uint8).reshape(n, vec) if n else np.zeros((0, vec), np.uint8)
        desc = np.ascontiguousarray(arr[:, :dbytes])
        locs = np.ascontiguousarray(arr[:, dbytes:])
        # Locator sanity: work/edition indices must exist in the table.
        if n:
            wi = locs.view("<u4")[:, 0]
            if wi.max() >= nworks:
                raise ValueError("locator references unknown work")
        b = cls(family, float(interval), desc, locs, works)
        b.indexed_hours = n * interval / 3600.0
        return b

    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


def build_index(editions: Sequence[Edition], family: DescriptorFamily, sampling_interval_s: float = 2.0) -> IndexBundle:
    """Build a flat index from authorised gallery editions.

    Sampling: one reference descriptor every `sampling_interval_s` seconds of each edition.
    """
    if not (0.1 <= sampling_interval_s <= 60.0):
        raise ValueError("sampling interval out of bounds")
    t0 = time.perf_counter()
    works: Dict[str, WorkEntry] = {}
    edition_order = [k.value for k in EditionKind]
    desc_rows: List[bytes] = []
    loc_rows: List[bytes] = []
    total_s = 0.0
    for ed in editions:
        wid = ed.work.work_id
        if wid not in works:
            works[wid] = WorkEntry(len(works), wid, ed.work.synthetic_title, [], [],
                                   getattr(ed.work, "series_id", None), getattr(ed.work, "episode_id", None))
        we = works[wid]
        if ed.edition_id in we.editions:
            raise ValueError(f"duplicate edition {ed.asset_id}")
        we.editions.append(ed.edition_id)
        we.durations_s.append(ed.duration_s)
        eidx = edition_order.index(ed.edition_id)
        n = int(np.floor(ed.duration_s / sampling_interval_s))
        for i in range(n):
            t = i * sampling_interval_s
            frame = normalize(ed.render_frame(t))
            desc_rows.append(describe(frame, family))
            loc_rows.append(Locator(we.work_index, eidx, int(round(t * 1000))).pack())
        total_s += n * sampling_interval_s
    d = family.descriptor_bytes
    desc = np.frombuffer(b"".join(desc_rows), dtype=np.uint8).reshape(-1, d) if desc_rows else np.zeros((0, d), np.uint8)
    locs = np.frombuffer(b"".join(loc_rows), dtype=np.uint8).reshape(-1, LOCATOR_BYTES) if loc_rows else np.zeros((0, LOCATOR_BYTES), np.uint8)
    bundle = IndexBundle(family, sampling_interval_s, desc.copy(), locs.copy(), list(works.values()))
    bundle.build_seconds = time.perf_counter() - t0
    bundle.indexed_hours = total_s / 3600.0
    bundle.stats = {
        "vector_count": bundle.vector_count,
        "payload_bytes": bundle.payload_bytes,
        "bytes_per_reference_hour": bundle.bytes_per_reference_hour(),
        "build_seconds": bundle.build_seconds,
    }
    return bundle


def duplicate_descriptor_ratio(bundle: IndexBundle) -> float:
    """Fraction of exactly duplicated descriptors (P03-T04b corruption/duplicate check)."""
    if bundle.vector_count == 0:
        return 0.0
    uniq = np.unique(bundle.descriptors, axis=0).shape[0]
    return 1.0 - uniq / bundle.vector_count
