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


def test_dac_dhash_golden_file_is_current(tmp_path):
    from dac_l0.index.exact import write_golden

    out = tmp_path / "x.txt"
    write_golden(out)
    committed = COMMITTED.parent / "golden_dac_dhash_v1.txt"
    assert out.read_bytes().replace(b"\r\n", b"\n") == committed.read_bytes().replace(b"\r\n", b"\n")


def test_e2e_golden_file_is_current(tmp_path):
    from dac_l0.eval.e2e_golden import write as write_e2e

    out = tmp_path / "e.txt"
    write_e2e(out)
    committed = COMMITTED.parent / "golden_e2e.txt"
    assert out.read_bytes().replace(b"\r\n", b"\n") == committed.read_bytes().replace(b"\r\n", b"\n")


def test_exact_path_golden_file_is_current(tmp_path):
    from dac_l0.eval.exact_golden import write as write_exact

    out = tmp_path / "x.txt"
    write_exact(out)
    committed = COMMITTED.parent / "golden_exact.txt"
    assert out.read_bytes().replace(b"\r\n", b"\n") == committed.read_bytes().replace(b"\r\n", b"\n")


def test_format_contract_cases_are_current(tmp_path):
    from dac_l0.eval.format_golden import write as write_cases

    out = tmp_path / "f.txt"
    write_cases(out)    # also asserts the Python parser agrees with every intended verdict
    committed = COMMITTED.parent / "golden_format_cases.txt"
    assert out.read_bytes().replace(b"\r\n", b"\n") == committed.read_bytes().replace(b"\r\n", b"\n")


def test_pipeline_golden_file_is_current(tmp_path):
    from dac_l0.eval.pipeline_golden import write as write_pipeline

    out = tmp_path / "p.txt"
    write_pipeline(out)
    committed = COMMITTED.parent / "golden_pipeline.txt"
    assert out.read_bytes().replace(b"\r\n", b"\n") == committed.read_bytes().replace(b"\r\n", b"\n")
