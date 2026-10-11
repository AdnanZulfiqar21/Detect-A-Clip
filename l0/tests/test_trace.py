"""TRACE-01 (document-level): reconcile IDs in roadmap v4.2.1.

Counts are parsed from the roadmap file itself, so a missing or duplicated definition
fails the test rather than being assumed.
"""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = next(ROOT.glob("CineDetect_AI_Fable51_Revised_Roadmap_PROPOSED*.md"))
TEXT = ROADMAP.read_text(encoding="utf-8")


def _table_first_cells(section_start, section_end):
    s = TEXT[TEXT.index(section_start): TEXT.index(section_end)]
    return [m.group(1) for m in re.finditer(r"^\|\s*\**([A-Z][A-Z0-9\-]+[0-9])\**\s*(?:`[^`]*`)?\s*\|", s, re.M)]


def test_roadmap_is_v421():
    assert "v4.2.1 (PROPOSED)" in TEXT.splitlines()[0]


def test_86_task_ids_defined_once():
    tasks = re.findall(r"^\| (P\d\d-T\d\d) \|", TEXT, re.M)
    dup = [k for k, v in Counter(tasks).items() if v > 1]
    assert not dup, dup
    assert len(tasks) == 86


def test_54_test_ids_defined_once():
    ids = _table_first_cells("## F08.", "## F09.")
    ids = [i for i in ids if i != "Test"]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    assert not dup, dup
    assert len(ids) == 54, len(ids)


def test_13_concrete_gate_rows():
    s = TEXT[TEXT.index("## F09."): TEXT.index("Immediate stop for unauthorised")]
    gates = re.findall(r"^\| \**(G\d\d(?:-L[01])?)\** \|", s, re.M)
    assert len(gates) == 13 and len(set(gates)) == 13, gates
    assert "G03" not in gates  # G03 is the historical umbrella of G03-L0/L1


def test_11_decisions():
    ds = set(re.findall(r"\| \**(D\d\d)\**", TEXT[TEXT.index("| Owner decision"): TEXT.index("## F02.")]))
    assert ds == {f"D{i:02d}" for i in range(1, 12)}


def test_every_referenced_test_id_is_defined():
    defined = set(_table_first_cells("## F08.", "## F09."))
    refs = set(re.findall(r"\b((?:CONS|CAP|LIFE|DATA|RIGHTS|AI|SEC|OPS|REL|IDX|AUD|PRIV|UX|BETA|TRACE)-[A-Z]?\d\d)\b", TEXT))
    missing = sorted(r for r in refs if r not in defined)
    assert not missing, missing


def test_every_referenced_task_id_is_defined():
    defined = set(re.findall(r"^\| (P\d\d-T\d\d) \|", TEXT, re.M))
    refs = set(re.findall(r"\b(P\d\d-T\d\d)\b", TEXT))
    assert refs <= defined, sorted(refs - defined)
