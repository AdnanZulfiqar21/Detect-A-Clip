"""Result wording parity (P05-T04b): every canonical outcome has the same honest text on Android
(res/values/strings.xml result_*) and iOS (LabFlow.outcomeText), and OUTSIDE_CATALOGUE /
REMOTE_UNAVAILABLE stay unreachable (no text, no enum case)."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUTCOMES = ["VERIFIED_MATCH", "POSSIBLE_MATCH", "NO_CONFIDENT_MATCH", "INSUFFICIENT_SIGNAL", "UNSUPPORTED_CAPTURE",
            "PERMISSION_DENIED", "CANCELLED", "ERROR"]


def _camel(s: str) -> str:
    a, *b = s.lower().split("_")
    return a + "".join(x.title() for x in b)


def test_android_and_ios_result_text_match():
    xml = (REPO / "android/app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
    android = {m.group(1).upper(): m.group(2).replace("\'", "'") for m in re.finditer(r'<string name="result_([a-z_]+)">([^<]*)</string>', xml)}
    swift = (REPO / "ios/DetectAClipLab/Sources/LabFlow.swift").read_text(encoding="utf-8")
    body = swift[swift.index("func outcomeText"):swift.index("func resultLine")]
    ios = {m.group(1): m.group(2) for m in re.finditer(r'case \.(\w+): return "([^"]*)"', body)}
    for o in OUTCOMES:
        assert o in android, o
        assert android[o] == ios[_camel(o)], o
        assert android[o] != o, f"{o} shows a raw code"
    assert len(ios) == len(OUTCOMES)
    for reserved in ("OUTSIDE_CATALOGUE", "REMOTE_UNAVAILABLE"):
        assert reserved not in android
        assert _camel(reserved) not in swift
