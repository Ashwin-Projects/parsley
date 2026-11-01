"""Rules mode stays byte-identical to v1.1 on every held-out and fixture file.

``tests/golden/`` holds ``results.csv`` and ``summary.md`` from ``run_eval`` at commit
b7ed07c, generated before any LLM code existed. They pin behaviour, failures included, and
assert nothing about what the numbers should be, so they cannot serve as tuning targets.
"""

from pathlib import Path

import pytest

from parsley.eval import run_eval

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"


@pytest.fixture(scope="module")
def evaluation(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("rules_eval")
    assert run_eval.main(["--root", str(ROOT), "--out", str(out)]) == 0
    return out


@pytest.mark.parametrize(("produced", "golden"), [
    ("results.csv", "rules_results.csv"),
    ("summary.md", "rules_summary.md"),
])
def test_evaluation_output_is_byte_identical(evaluation: Path, produced: str, golden: str) -> None:
    assert (evaluation / produced).read_bytes() == (GOLDEN / golden).read_bytes()
