"""Index payload format contract: idx-flat-4 (writer) with idx-flat-3 migration (reader).

One contract for Python, Kotlin and Swift. docs/PACK_FORMAT.md is the prose version; the
cross-language cases in android/app/src/test/resources/golden_format_cases.txt are generated
from this module and must be accepted/rejected identically by every parser.

Binary layout (little endian):
  header   magic "DACL0IDX" | u16 version=1 | u16 descriptor_bytes | u32 vector_count |
           u32 work_count | f64 sampling_interval_s (0.1..60)
  u32 metadata_length (<= 64 MiB) | metadata UTF-8 JSON
  body     vector_count x (descriptor_bytes descriptor | 16-byte locator)
  locator  u32 work_index | u16 edition_index | u32 t_ms | u16 segment (=0) | u32 reserved (=0)

Metadata (exact key sets):
  index_format_version  "idx-flat-3" | "idx-flat-4"
  generator_version, preprocessing_version, family     non-empty strings; family matches bytes
  works                 list, works[i].work_index == i
  shared_scenes         idx-flat-4 only (v3 migrates to [])
Work entry keys: work_index, work_id, synthetic_title, editions, durations_s, series_id,
  episode_id, names, and (idx-flat-4) aliases.
  - work_id unique, ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$; series_id null or the same pattern
  - episode_id null or ^[A-Za-z0-9_.-]{1,64}$, only with a series_id; (series, episode) unique
  - editions 1..16 unique ^[A-Za-z0-9_]{1,64}$; durations_s same length, finite, 0 < d <= 1e6
  - synthetic_title 1..200 chars without control characters
  - names <= 16 entries {locale tag: 1..200 chars}; aliases <= 32 unique 1..200-char strings
Locators: work < work_count; edition < len(works[work].editions) (the *work's own* edition
  list position); t_ms <= ceil(duration_ms); segment == 0; reserved == 0; no duplicate
  (work, edition, t_ms).
Shared scenes (metadata only; declares identical footage across works, never used to name a
  title): list <= 10000 of {group_id unique id, members: 2..64 of {work_index, edition_index,
  start_ms, end_ms}} with valid references and 0 <= start_ms < end_ms <= duration_ms.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

FORMAT_V3 = "idx-flat-3"
FORMAT_V4 = "idx-flat-4"
SUPPORTED_FORMATS = (FORMAT_V3, FORMAT_V4)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_EPISODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_EDITION = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")
MAX_EDITIONS = 16
MAX_NAMES = 16
MAX_ALIASES = 32
MAX_TEXT = 200
MAX_SHARED_SCENES = 10_000
MAX_SCENE_MEMBERS = 64

WORK_KEYS_V3 = {"work_index", "work_id", "synthetic_title", "editions", "durations_s", "series_id", "episode_id", "names"}
WORK_KEYS_V4 = WORK_KEYS_V3 | {"aliases"}
META_KEYS_V3 = {"index_format_version", "generator_version", "preprocessing_version", "family", "works"}
META_KEYS_V4 = META_KEYS_V3 | {"shared_scenes"}


@dataclass
class SharedSceneMember:
    work_index: int
    edition_index: int
    start_ms: int
    end_ms: int


@dataclass
class SharedScene:
    group_id: str
    members: List[SharedSceneMember] = field(default_factory=list)


def strict_json_loads(raw: bytes):
    """JSON with the same acceptance as the native parsers: duplicate keys, NaN and Infinity
    are rejected (Python's json module would otherwise accept them silently)."""
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError("duplicate JSON key")
            d[k] = v
        return d

    def no_constants(name):
        raise ValueError(f"JSON constant {name} not allowed")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=no_constants)


def _text(v, what: str, max_len: int = MAX_TEXT) -> str:
    if not isinstance(v, str) or not (0 < len(v) <= max_len) or any(ord(c) < 32 for c in v):
        raise ValueError(f"bad {what}")
    return v


def _int(v, what: str) -> int:
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValueError(f"bad {what}")
    return v


def check_names(names) -> Dict[str, str]:
    if not isinstance(names, dict) or len(names) > MAX_NAMES:
        raise ValueError("bad names table")
    for k, v in names.items():
        if not isinstance(k, str) or not _LOCALE.fullmatch(k):
            raise ValueError("bad locale tag")
        _text(v, "display name")
    return dict(names)


def check_aliases(aliases) -> List[str]:
    if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES:
        raise ValueError("bad aliases")
    out = [_text(a, "alias") for a in aliases]
    if len(set(out)) != len(out):
        raise ValueError("duplicate alias")
    return out


def validate_metadata(meta, work_count: int):
    """Returns (format_version, works_as_dicts, shared_scenes). Raises ValueError."""
    if not isinstance(meta, dict):
        raise ValueError("metadata not an object")
    fmt = meta.get("index_format_version")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError("incompatible index format version")
    if set(meta) != (META_KEYS_V4 if fmt == FORMAT_V4 else META_KEYS_V3):
        raise ValueError("metadata keys mismatch")
    for k in ("generator_version", "preprocessing_version", "family"):
        _text(meta[k], k)
    works_raw = meta["works"]
    if not isinstance(works_raw, list) or len(works_raw) != work_count:
        raise ValueError("work table mismatch")
    keys = WORK_KEYS_V4 if fmt == FORMAT_V4 else WORK_KEYS_V3
    works = []
    seen_ids, seen_eps = set(), set()
    for i, w in enumerate(works_raw):
        if not isinstance(w, dict) or set(w) != keys:
            raise ValueError("bad work entry")
        if _int(w["work_index"], "work_index") != i:
            raise ValueError("work_index out of order")
        wid = w["work_id"]
        if not isinstance(wid, str) or not _ID.fullmatch(wid):
            raise ValueError("bad work_id")
        if wid in seen_ids:
            raise ValueError("duplicate work_id")
        seen_ids.add(wid)
        _text(w["synthetic_title"], "synthetic_title")
        eds, durs = w["editions"], w["durations_s"]
        if not isinstance(eds, list) or not (1 <= len(eds) <= MAX_EDITIONS):
            raise ValueError("bad editions")
        if any(not isinstance(e, str) or not _EDITION.fullmatch(e) for e in eds) or len(set(eds)) != len(eds):
            raise ValueError("bad or duplicate edition id")
        if not isinstance(durs, list) or len(durs) != len(eds):
            raise ValueError("durations/editions mismatch")
        for d in durs:
            if not isinstance(d, (int, float)) or isinstance(d, bool) or not math.isfinite(d) or not (0 < d <= 1e6):
                raise ValueError("bad duration")
        sid, eid = w["series_id"], w["episode_id"]
        if sid is not None and (not isinstance(sid, str) or not _ID.fullmatch(sid)):
            raise ValueError("bad series_id")
        if eid is not None:
            if sid is None:
                raise ValueError("episode_id without series_id")
            if not isinstance(eid, str) or not _EPISODE.fullmatch(eid):
                raise ValueError("bad episode_id")
            if (sid, eid) in seen_eps:
                raise ValueError("duplicate episode")
            seen_eps.add((sid, eid))
        check_names(w["names"])
        aliases = check_aliases(w["aliases"]) if fmt == FORMAT_V4 else []
        works.append({**{k: w[k] for k in WORK_KEYS_V3}, "aliases": aliases})
    scenes: List[SharedScene] = []
    if fmt == FORMAT_V4:
        raw = meta["shared_scenes"]
        if not isinstance(raw, list) or len(raw) > MAX_SHARED_SCENES:
            raise ValueError("bad shared_scenes")
        gids = set()
        for g in raw:
            if not isinstance(g, dict) or set(g) != {"group_id", "members"}:
                raise ValueError("bad shared scene")
            gid = g["group_id"]
            if not isinstance(gid, str) or not _ID.fullmatch(gid) or gid in gids:
                raise ValueError("bad or duplicate shared scene group_id")
            gids.add(gid)
            mem = g["members"]
            if not isinstance(mem, list) or not (2 <= len(mem) <= MAX_SCENE_MEMBERS):
                raise ValueError("shared scene needs 2..64 members")
            members = []
            for m in mem:
                if not isinstance(m, dict) or set(m) != {"work_index", "edition_index", "start_ms", "end_ms"}:
                    raise ValueError("bad shared scene member")
                wi, ei = _int(m["work_index"], "member work"), _int(m["edition_index"], "member edition")
                s, e = _int(m["start_ms"], "member start"), _int(m["end_ms"], "member end")
                if not (0 <= wi < work_count) or not (0 <= ei < len(works[wi]["editions"])):
                    raise ValueError("shared scene references a missing work/edition")
                if not (0 <= s < e <= math.ceil(works[wi]["durations_s"][ei] * 1000)):
                    raise ValueError("shared scene interval out of range")
                members.append(SharedSceneMember(wi, ei, s, e))
            scenes.append(SharedScene(gid, members))
    return fmt, works, scenes


def validate_locators(locs: np.ndarray, works: List[dict]) -> None:
    """locs: (N, 16) uint8. Vectorised contract checks."""
    n = locs.shape[0]
    if n == 0:
        return
    raw = np.ascontiguousarray(locs).tobytes()
    rec = np.frombuffer(raw, dtype=np.dtype([("w", "<u4"), ("e", "<u2"), ("t", "<u4"), ("s", "<u2"), ("r", "<u4")]))
    w = rec["w"].astype(np.int64)
    if (w >= len(works)).any():
        raise ValueError("locator references unknown work")
    n_ed = np.array([len(x["editions"]) for x in works], dtype=np.int64)
    e = rec["e"].astype(np.int64)
    if (e >= n_ed[w]).any():
        raise ValueError("locator references unknown edition")
    max_ed = int(n_ed.max())
    dur = np.zeros((len(works), max_ed), dtype=np.int64)
    for i, x in enumerate(works):
        for j, d in enumerate(x["durations_s"]):
            dur[i, j] = math.ceil(d * 1000)
    if (rec["t"].astype(np.int64) > dur[w, e]).any():
        raise ValueError("locator time beyond the edition duration")
    if (rec["s"] != 0).any() or (rec["r"] != 0).any():
        raise ValueError("locator segment/reserved fields must be zero")
    key = (w << 40) | (e << 32) | rec["t"].astype(np.int64)
    if np.unique(key).shape[0] != n:
        raise ValueError("duplicate locator")
