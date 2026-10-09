"""The committed golden vectors must match the current Python reference, so the Kotlin port
(RecognitionGoldenTest) is always checked against today's verify/decide behaviour."""
from pathlib import Path

from dac_l0.eval.golden import write

COMMITTED = Path(__file__).resolve().parents[2] / "android" / "app" / "src" / "test" / "resources" / "golden_recognition.txt"


def test_golden_file_is_current(tmp_path):
    out = tmp_path / "g.txt"
    write(out)
    def norm(t: str) -> str:
        return t.replace("\r\n", "\n")

    assert norm(out.read_bytes().decode("utf-8")) == norm(COMMITTED.read_bytes().decode("utf-8")), \
        "Python reference changed: regenerate with `python -m dac_l0.eval.golden --out ../android/app/src/test/resources/golden_recognition.txt` and rerun android/run-jvm-tests.sh"
