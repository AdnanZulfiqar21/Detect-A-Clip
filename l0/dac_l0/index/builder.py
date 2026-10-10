"""Reproducible index builder (P03-T03) and payload serialisation.

The payload is a flat array of (descriptor || locator) vectors plus a small header.
Everything is derived from authorised assets in the asset manifest only. Build output is
deterministic for a given (generator, preprocessing, family, sampling interval, assets).
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .. import EXACT_PREPROCESSING_VERSION, GENERATOR_VERSION, INDEX_FORMAT_VERSION, PREPROCESSING_VERSION
from ..quality import normalize
from ..synth.generator import Edition, EditionKind
from .descriptors import LOCATOR_BYTES, DescriptorFamily, Locator, describe
from .format import FORMAT_V5, SharedScene, SharedSceneMember, check_names, strict_json_loads, validate_locators, validate_metadata

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
    names: Dict[str, str] = field(default_factory=dict)  # idx-flat-3: locale tag -> display name (P04-T04a)
    aliases: List[str] = field(default_factory=list)     # idx-flat-4: alternative titles (P03-T01)


@dataclass
class IndexBundle:
    family: DescriptorFamily
    sampling_interval_s: float
    descriptors: np.ndarray  # (N, D) uint8
    locators: np.ndarray     # (N, 16) uint8
    works: List[WorkEntry]
    shared_scenes: List[SharedScene] = field(default_factory=list)   # idx-flat-4 metadata only
    series_names: Dict[str, Dict[str, str]] = field(default_factory=dict)  # idx-flat-5: series_id -> {locale: name}
    source_format: str = FORMAT_V5                                     # format the payload was read from
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
            "preprocessing_version": preprocessing_for(self.family),
            "family": self.family.value,
            "works": [dict(w.__dict__) for w in self.works],
            "shared_scenes": [{"group_id": g.group_id, "members": [m.__dict__ for m in g.members]} for g in self.shared_scenes],
            # Exactly the series the works reference (contract); names default to empty.
            "series": [{"series_id": s, "names": dict(self.series_names.get(s, {}))} for s in self.referenced_series()],
        }
        return json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()

    def referenced_series(self) -> List[str]:
        return sorted({w.series_id for w in self.works if w.series_id is not None})

    def hash_u64(self) -> np.ndarray:
        if not self.family.is_hash:
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
        if dbytes not in {f.descriptor_bytes for f in DescriptorFamily}:
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
            meta = strict_json_loads(meta_raw)
        except (UnicodeDecodeError, ValueError) as e:
            raise ValueError(f"metadata not valid JSON: {e}") from e
        fmt, works_raw, scenes, series_names = validate_metadata(meta, nworks)
        try:
            family = DescriptorFamily(meta["family"])
        except ValueError:
            raise ValueError("unknown descriptor family")
        if family.descriptor_bytes != dbytes:
            raise ValueError("metadata/header family mismatch")
        if meta["preprocessing_version"] != preprocessing_for(family):
            raise ValueError("preprocessing version does not match the descriptor family")
        works = [WorkEntry(**w) for w in works_raw]
        vec = dbytes + LOCATOR_BYTES
        body = data[off:]
        if len(body) != n * vec:
            raise ValueError("body length mismatch")
        arr = np.frombuffer(body, dtype=np.uint8).reshape(n, vec) if n else np.zeros((0, vec), np.uint8)
        desc = np.ascontiguousarray(arr[:, :dbytes])
        locs = np.ascontiguousarray(arr[:, dbytes:])
        validate_locators(locs, works_raw)
        b = cls(family, float(interval), desc, locs, works, scenes, series_names, fmt)
        b.indexed_hours = n * interval / 3600.0
        return b

    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


_check_names = check_names  # backwards-compatible name


def preprocessing_for(family: DescriptorFamily) -> str:
    return EXACT_PREPROCESSING_VERSION if family == DescriptorFamily.DACDHASH else PREPROCESSING_VERSION


def resolve_display_name(names: Dict[str, str], preferences: Sequence[str], fallback: str) -> str:
    """Exact locale, then same language, then English, then the lexicographically first name,
    then `fallback`. Never mixes names across works."""
    for p in preferences:
        if p in names:
            return names[p]
    for p in preferences:
        lang = p.split("-")[0]
        for k in sorted(names):
            if k.split("-")[0] == lang:
                return names[k]
    if "en" in names:
        return names["en"]
    return names[sorted(names)[0]] if names else fallback


def result_display_name(bundle: "IndexBundle", work_id: Optional[str], episode_id: Optional[str],
                        preferences: Sequence[str]) -> Optional[str]:
    """Name to show for a committed result: the episode's name, a plain work's name, or (series
    level, episode not unique) the series' own name from the idx-flat-5 series table. An ID
    absent from the pack, or a series without names, shows the ID itself; a result never
    borrows another work's name. No candidate -> None."""
    if work_id is None:
        return None
    for w in bundle.works:
        if episode_id is not None:
            hit = w.series_id == work_id and w.episode_id == episode_id
        else:
            hit = w.work_id == work_id and w.series_id is None
        if hit:
            return resolve_display_name(w.names, preferences, w.work_id)
    if episode_id is None and work_id in bundle.series_names:
        return resolve_display_name(bundle.series_names[work_id], preferences, work_id)
    return work_id


def build_index(editions: Sequence[Edition], family: DescriptorFamily, sampling_interval_s: float = 2.0,
                shared_scenes: Optional[Sequence[Tuple[str, Sequence[Tuple[str, str, int, int]]]]] = None,
                series_names: Optional[Dict[str, Dict[str, str]]] = None) -> IndexBundle:
    """Build a flat index from authorised gallery editions.

    Sampling: one reference descriptor every `sampling_interval_s` seconds of each edition.
    Locator edition indices are positions in *that work's own* edition list (format contract).
    shared_scenes: optional declarations (group_id, [(work_id, edition_id, start_ms, end_ms), ...]).
    series_names: optional {series_id: {locale: name}}; a referenced series without an entry gets
    the work's `series_names` attribute or the synthetic default {"en": "SYNTHETIC SERIES <id>"}.
    """
    if not (0.1 <= sampling_interval_s <= 60.0):
        raise ValueError("sampling interval out of bounds")
    t0 = time.perf_counter()
    works: Dict[str, WorkEntry] = {}
    desc_rows: List[bytes] = []
    loc_rows: List[bytes] = []
    total_s = 0.0
    for ed in editions:
        wid = ed.work.work_id
        if wid not in works:
            works[wid] = WorkEntry(len(works), wid, ed.work.synthetic_title, [], [],
                                   getattr(ed.work, "series_id", None), getattr(ed.work, "episode_id", None),
                                   dict(getattr(ed.work, "display_names", None) or {"en": ed.work.synthetic_title}),
                                   list(getattr(ed.work, "aliases", None) or []))
        we = works[wid]
        if ed.edition_id in we.editions:
            raise ValueError(f"duplicate edition {ed.asset_id}")
        we.editions.append(ed.edition_id)
        we.durations_s.append(ed.duration_s)
        eidx = len(we.editions) - 1   # position in this work's own edition list
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
    scenes: List[SharedScene] = []
    for gid, members in (shared_scenes or []):
        ms = []
        for wid, eid, s_ms, e_ms in members:
            we = works[wid]
            ms.append(SharedSceneMember(we.work_index, we.editions.index(eid), int(s_ms), int(e_ms)))
        scenes.append(SharedScene(gid, ms))
    names_by_series: Dict[str, Dict[str, str]] = dict(series_names or {})
    for ed in editions:
        sid = getattr(ed.work, "series_id", None)
        if sid is not None and sid not in names_by_series:
            names_by_series[sid] = dict(getattr(ed.work, "series_names", None) or {"en": f"SYNTHETIC SERIES {sid}"})
    bundle = IndexBundle(family, sampling_interval_s, desc.copy(), locs.copy(), list(works.values()), scenes, names_by_series)
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
