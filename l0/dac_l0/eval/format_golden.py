"""Cross-language index-format contract cases (docs/PACK_FORMAT.md, dac_l0/index/format.py).

Each case is a complete DACDHASH payload in hex with the expected verdict. The generator
asserts that the Python parser agrees with the intended verdict before writing, so the file
encodes the contract; Kotlin (PackIndex) and Swift (PackIndex) must reproduce every verdict.

  python -m dac_l0.eval.format_golden --out ../android/app/src/test/resources/golden_format_cases.txt
"""
from __future__ import annotations

import argparse
import copy
import json
import struct
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .. import EXACT_PREPROCESSING_VERSION, GENERATOR_VERSION
from ..index.builder import HEADER_FMT, IndexBundle, MAGIC

DESC_BYTES = 8


def base_meta(fmt: str = "idx-flat-5") -> Dict:
    works = [
        {"work_index": 0, "work_id": "SW000", "synthetic_title": "SYNTHETIC WORK 000", "editions": ["E0_THEATRICAL", "E1_EXTENDED"],
         "durations_s": [60.0, 66.0], "series_id": None, "episode_id": None, "names": {"en": "Synthetic Work 000", "ur-Latn": "Masnooi Kaam 000"}},
        {"work_index": 1, "work_id": "SW100", "synthetic_title": "SYNTHETIC SERIES S-X EPISODE E01", "editions": ["E0_THEATRICAL"],
         "durations_s": [30.0], "series_id": "S-X", "episode_id": "E01", "names": {"en": "Synthetic Series X, Episode 1"}},
        {"work_index": 2, "work_id": "SW101", "synthetic_title": "SYNTHETIC SERIES S-X EPISODE E02", "editions": ["E2_BROADCAST"],
         "durations_s": [30.0], "series_id": "S-X", "episode_id": "E02", "names": {"en": "Synthetic Series X, Episode 2"}},
    ]
    meta = {"index_format_version": fmt, "generator_version": GENERATOR_VERSION, "preprocessing_version": EXACT_PREPROCESSING_VERSION,
            "family": "DACDHASH", "works": works}
    if fmt == "idx-flat-5":
        meta["series"] = [{"series_id": "S-X", "names": {"en": "Synthetic Series X", "ur-Latn": "Masnooi Series X"}}]
    if fmt in ("idx-flat-4", "idx-flat-5"):
        works[0]["aliases"] = ["Synthetic Work Zero"]
        works[1]["aliases"] = []
        works[2]["aliases"] = []
        meta["shared_scenes"] = [{"group_id": "intro-S-X", "members": [
            {"work_index": 1, "edition_index": 0, "start_ms": 0, "end_ms": 6000},
            {"work_index": 2, "edition_index": 0, "start_ms": 0, "end_ms": 6000}]}]
    return meta


def base_locators() -> List[Tuple[int, int, int, int, int]]:
    locs = [(0, 0, t, 0, 0) for t in range(0, 60000, 2000)] + [(0, 1, t, 0, 0) for t in range(0, 66000, 2000)]
    locs += [(1, 0, t, 0, 0) for t in range(0, 30000, 2000)] + [(2, 0, t, 0, 0) for t in range(0, 30000, 2000)]
    return locs


def pack(meta: Dict, locs, interval: float = 2.0, magic: bytes = MAGIC, version: int = 1, dbytes: int = DESC_BYTES,
         n_override=None, works_override=None, body_trim: int = 0, mj_edit=None) -> bytes:
    mj = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
    if mj_edit is not None:
        edited = mj_edit(mj)
        assert edited != mj, "metadata edit did not apply"
        mj = edited
    n = len(locs) if n_override is None else n_override
    nw = len(meta["works"]) if works_override is None else works_override
    head = struct.pack(HEADER_FMT, magic, version, dbytes, n, nw, interval) + struct.pack("<I", len(mj)) + mj
    body = b"".join(((0x9E3779B97F4A7C15 * (i + 1)) & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little") +
                    struct.pack("<IHIHI", *loc) for i, loc in enumerate(locs))
    data = head + body
    return data[:len(data) - body_trim] if body_trim else data


Case = Tuple[str, bool, bytes]


def cases() -> List[Case]:
    out: List[Case] = []
    M, L = base_meta, base_locators

    def mut(fn: Callable[[Dict], None], fmt="idx-flat-5") -> Dict:
        m = copy.deepcopy(M(fmt))
        fn(m)
        return m

    # ---- valid
    out.append(("valid_v5_series_names_aliases_shared_scene", True, pack(M(), L())))
    out.append(("valid_v4_migration_no_series", True, pack(M("idx-flat-4"), L())))
    out.append(("valid_v5_series_without_names", True, pack(mut(lambda m: m["series"][0].__setitem__("names", {})), L())))
    # ---- series table (idx-flat-5)
    out.append(("v4_with_series_key", False, pack(mut(lambda m: m.__setitem__("series", []), "idx-flat-4"), L())))
    out.append(("v5_series_table_missing", False, pack(mut(lambda m: m.pop("series")), L())))
    out.append(("v5_series_table_empty", False, pack(mut(lambda m: m.__setitem__("series", [])), L())))
    out.append(("v5_series_unreferenced_entry", False, pack(mut(lambda m: m["series"].append({"series_id": "S-Z", "names": {}})), L())))
    out.append(("v5_series_duplicate_entry", False, pack(mut(lambda m: m["series"].append({"series_id": "S-X", "names": {}})), L())))
    out.append(("v5_series_entry_extra_key", False, pack(mut(lambda m: m["series"][0].__setitem__("aliases", [])), L())))
    out.append(("v5_series_bad_locale", False, pack(mut(lambda m: m["series"][0]["names"].__setitem__("English", "x")), L())))
    out.append(("v5_series_name_too_long", False, pack(mut(lambda m: m["series"][0]["names"].__setitem__("en", "x" * 201)), L())))
    out.append(("v5_series_id_equals_work_id", False, pack(mut(lambda m: (m["works"][1].__setitem__("series_id", "SW000"), m["works"][2].__setitem__("series_id", "SW000"),
                                                                            m["series"][0].__setitem__("series_id", "SW000"))), L())))
    out.append(("valid_v3_migration_no_aliases", True, pack(M("idx-flat-3"), L())))
    out.append(("valid_only_non_first_edition_E2", True, pack(M(), L())))  # work 2 has only E2_BROADCAST at index 0
    out.append(("valid_reordered_editions", True, pack(mut(lambda m: (m["works"][0].__setitem__("editions", ["E1_EXTENDED", "E0_THEATRICAL"]),
                                                                       m["works"][0].__setitem__("durations_s", [66.0, 60.0]))),
                                 [(w, (1 - e) if w == 0 else e, t, sg, r) for (w, e, t, sg, r) in L()])))
    out.append(("valid_empty_body", True, pack(M(), [])))
    # ---- header / framing
    out.append(("bad_magic", False, pack(M(), L(), magic=b"DACL0IDY")))
    out.append(("bad_header_version", False, pack(M(), L(), version=2)))
    out.append(("interval_out_of_range", False, pack(M(), L(), interval=0.05)))
    out.append(("body_truncated", False, pack(M(), L(), body_trim=3)))
    out.append(("vector_count_inflated", False, pack(M(), L(), n_override=len(L()) + 1)))
    out.append(("work_count_mismatch", False, pack(M(), L(), works_override=4)))
    out.append(("unknown_format_version", False, pack(mut(lambda m: m.__setitem__("index_format_version", "idx-flat-9")), L())))
    out.append(("family_bytes_mismatch", False, pack(mut(lambda m: m.__setitem__("family", "THUMB32")), L())))
    out.append(("preprocessing_mismatch", False, pack(mut(lambda m: m.__setitem__("preprocessing_version", "prep-other")), L())))
    out.append(("extra_metadata_key", False, pack(mut(lambda m: m.__setitem__("debug", True)), L())))
    out.append(("v3_with_shared_scenes_key", False, pack(mut(lambda m: m.__setitem__("shared_scenes", []), "idx-flat-3"), L())))
    out.append(("v3_work_with_aliases", False, pack(mut(lambda m: m["works"][0].__setitem__("aliases", []), "idx-flat-3"), L())))
    # ---- works
    out.append(("work_index_out_of_order", False, pack(mut(lambda m: m["works"][1].__setitem__("work_index", 5)), L())))
    out.append(("duplicate_work_id", False, pack(mut(lambda m: m["works"][2].__setitem__("work_id", "SW100")), L())))
    out.append(("bad_work_id", False, pack(mut(lambda m: m["works"][0].__setitem__("work_id", "../SW000")), L())))
    out.append(("episode_without_series", False, pack(mut(lambda m: m["works"][0].__setitem__("episode_id", "E09")), L())))
    out.append(("duplicate_episode", False, pack(mut(lambda m: m["works"][2].__setitem__("episode_id", "E01")), L())))
    out.append(("empty_editions", False, pack(mut(lambda m: (m["works"][2].__setitem__("editions", []), m["works"][2].__setitem__("durations_s", []))), [l for l in L() if l[0] != 2])))
    out.append(("duplicate_edition", False, pack(mut(lambda m: m["works"][0].__setitem__("editions", ["E0_THEATRICAL", "E0_THEATRICAL"])), L())))
    out.append(("durations_length_mismatch", False, pack(mut(lambda m: m["works"][0].__setitem__("durations_s", [60.0])), L())))
    out.append(("non_positive_duration", False, pack(mut(lambda m: m["works"][1].__setitem__("durations_s", [0.0])), L())))
    out.append(("bad_locale_tag", False, pack(mut(lambda m: m["works"][0]["names"].__setitem__("English", "x")), L())))
    out.append(("control_char_in_name", False, pack(mut(lambda m: m["works"][0]["names"].__setitem__("en", "a\nb")), L())))
    out.append(("duplicate_alias", False, pack(mut(lambda m: m["works"][0].__setitem__("aliases", ["A", "A"])), L())))
    out.append(("empty_synthetic_title", False, pack(mut(lambda m: m["works"][0].__setitem__("synthetic_title", "")), L())))
    # ---- shared scenes
    out.append(("shared_scene_single_member", False, pack(mut(lambda m: m["shared_scenes"][0]["members"].pop()), L())))
    out.append(("shared_scene_missing_edition", False, pack(mut(lambda m: m["shared_scenes"][0]["members"][0].__setitem__("edition_index", 3)), L())))
    out.append(("shared_scene_interval_beyond_duration", False, pack(mut(lambda m: m["shared_scenes"][0]["members"][0].__setitem__("end_ms", 30001)), L())))
    out.append(("shared_scene_empty_interval", False, pack(mut(lambda m: m["shared_scenes"][0]["members"][0].__setitem__("end_ms", 0)), L())))
    out.append(("shared_scene_duplicate_group", False, pack(mut(lambda m: m["shared_scenes"].append(copy.deepcopy(m["shared_scenes"][0]))), L())))
    # ---- locators
    out.append(("locator_unknown_work", False, pack(M(), L() + [(3, 0, 0, 0, 0)])))
    out.append(("locator_edition_beyond_work_list", False, pack(M(), L() + [(2, 1, 4000, 0, 0)])))   # the old global-index bug
    out.append(("locator_time_beyond_duration", False, pack(M(), L() + [(1, 0, 30001, 0, 0)])))
    out.append(("locator_segment_nonzero", False, pack(M(), L()[:-1] + [(2, 0, 28000, 1, 0)])))
    out.append(("locator_reserved_nonzero", False, pack(M(), L()[:-1] + [(2, 0, 28000, 0, 7)])))
    out.append(("duplicate_locator", False, pack(M(), L() + [(0, 0, 0, 0, 0)])))
    # ---- JSON acceptance parity (raw metadata text)
    out.append(("work_id_with_trailing_newline", False, pack(mut(lambda m: m["works"][0].__setitem__("work_id", "SW000\n")), L())))
    out.append(("integer_field_as_float", False, pack(mut(lambda m: m["works"][1].__setitem__("work_index", 1.0)), L())))
    out.append(("boolean_as_integer", False, pack(mut(lambda m: m["shared_scenes"][0]["members"][0].__setitem__("start_ms", False)), L())))
    out.append(("non_ascii_name_ok", True, pack(mut(lambda m: m["works"][0]["names"].__setitem__("ur", "مصنوعی کام ۰۰۰")), L())))
    out.append(("astral_alias_length_ok", True, pack(mut(lambda m: m["works"][0].__setitem__("aliases", ["\U0001F3AC" * 200])), L())))
    out.append(("astral_alias_too_long", False, pack(mut(lambda m: m["works"][0].__setitem__("aliases", ["\U0001F3AC" * 201])), L())))
    out.append(("duplicate_json_key", False, pack(M(), L(), mj_edit=lambda b: b.replace(b'"family":"DACDHASH"', b'"family":"DACDHASH","family":"DACDHASH"', 1))))
    out.append(("nan_literal", False, pack(M(), L(), mj_edit=lambda b: b.replace(b'[30.0]', b'[NaN]', 1))))
    return out


DISPLAY_QUERIES = [
    ("SW000", None, ["ur-PK"]), ("SW000", None, ["ur-Latn", "en"]), ("SW000", None, ["ko"]), ("SW000", None, []),
    ("SW000", None, ["fr-CA", "ur"]), ("S-X", "E02", ["en"]), ("S-X", "E01", ["de"]), ("S-X", None, ["en"]),
    ("SW100", None, ["en"]), ("SW999", None, ["en"]), (None, None, ["en"]),
    ("S-X", None, ["ur-PK"]), ("S-X", None, ["ko"]), ("S-Y", None, ["en"]), ("S-X", "E09", ["en"]),
]


def write(out: Path) -> None:
    lines = ["# golden_format_cases v1: CASE <name> <ACCEPT|REJECT> <payload hex>; generated by l0/dac_l0/eval/format_golden.py"]
    for name, ok, data in cases():
        try:
            IndexBundle.from_bytes(data)
            got = True
        except ValueError:
            got = False
        if got != ok:
            raise AssertionError(f"Python parser disagrees with the contract on {name}: expected {ok}, got {got}")
        lines.append(f"CASE {name} {'ACCEPT' if ok else 'REJECT'} {data.hex()}")
    # Result display (P04-T04): DISPLAY <work|-> <episode|-> <prefs,comma|-> <expected UTF-8 hex|->
    # against the accepted valid_v5_series_names_aliases_shared_scene pack.
    from ..index.builder import result_display_name
    v4 = IndexBundle.from_bytes(dict((n, d) for n, _, d in cases())["valid_v5_series_names_aliases_shared_scene"])
    lines.append("# DISPLAY cases use the valid_v5_series_names_aliases_shared_scene pack")
    for wid, ep, prefs in DISPLAY_QUERIES:
        got = result_display_name(v4, wid, ep, prefs)
        lines.append(" ".join(["DISPLAY", wid or "-", ep or "-", ",".join(prefs) or "-",
                               "-" if got is None else got.encode("utf-8").hex()]))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    write(Path(ap.parse_args(argv).out))
    print("ok")


if __name__ == "__main__":
    main()
