"""Rules mode stays byte-identical to v1.1 on every held-out and fixture file.

``tests/golden/`` holds ``results.csv`` and ``summary.md`` from ``run_eval`` at commit
b7ed07c, generated before any LLM code existed. They pin behaviour, failures included, and
assert nothing about what the numbers should be, so they cannot serve as tuning targets.
"""

from pathlib import Path

import pytest

from parsley.eval import run_eval
from parsley.eval.dataset import Item, load_development, load_held_out
from parsley.llm.provider import ProviderError
from parsley.pipeline import PipelineResult, run

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
HELD_OUT = load_held_out(ROOT / "tests" / "eval_data")
FIXTURES = load_development(ROOT / "tests" / "fixtures")


class Exploding:
    """Rules mode must never reach this."""

    name = "exploding"

    def propose(self, sentence: str, context: object) -> list[object]:
        raise AssertionError(f"the LLM was called for {sentence!r}")


class Down:
    """A provider that always fails."""

    name = "down"

    def propose(self, sentence: str, context: object) -> list[object]:
        raise ProviderError("down")


def item_result(item: Item, **options: object) -> PipelineResult:
    session = run_eval._setup(item)
    assert session is not None, item.id
    return run(item.input, session, **options)


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


def test_the_data_is_all_there() -> None:
    assert len(HELD_OUT) >= 168
    assert len(FIXTURES) >= 72


@pytest.mark.parametrize("item", [*HELD_OUT, *FIXTURES], ids=lambda item: f"{item.source}-{item.id}")
def test_explicit_rules_mode_equals_the_default_and_never_calls_the_llm(item: Item) -> None:
    assert item_result(item, mode="rules", provider=Exploding()) == item_result(item)


@pytest.mark.parametrize("item", FIXTURES, ids=lambda item: item.id)
def test_hybrid_with_a_dead_provider_compiles_what_rules_compiles(item: Item) -> None:
    rules, hybrid = item_result(item), item_result(item, mode="hybrid", provider=Down())
    assert (hybrid.status, hybrid.minilang, hybrid.question) == (rules.status, rules.minilang, rules.question)
    assert [d for d in hybrid.diagnostics if d.stage != "llm"] == list(rules.diagnostics)
