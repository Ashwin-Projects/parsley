"""Runnable example sessions, derived from the development golden fixtures."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Protocol

import pytest

from parsley import pipeline
from parsley.diagnostics import Diagnostic
from parsley.session import Session


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
FIXTURES = {
    fixture["id"]: fixture
    for category in ("valid", "invalid", "ambiguous", "semantic")
    for fixture in json.loads(
        (ROOT / "tests" / "fixtures" / f"{category}.json")
        .read_text(encoding="utf-8")
    )["fixtures"]
}

# Replacements adapt fixture names/values without inventing English patterns.
Step = tuple[str, dict[str, str]]
SOURCES: dict[str, tuple[Step, ...]] = {
    "valid/age": (("V01", {}), ("V04", {}), ("V12", {})),
    "valid/greeting": (("V03", {}), ("V13", {})),
    "valid/conditional": (("V01", {}), ("V16", {})),
    "valid/repeat": (("V18", {}),),
    "valid/implicit-pronoun-x": (
        ("V06", {}), ("V20", {"score": "x"}), ("V23", {}),
    ),
    "valid/implicit-pronoun-score": (
        ("V06", {"x": "score", "5": "10"}), ("V20", {}), ("V19", {}),
    ),
    "valid/vocabulary": tuple((f"V{n}", {}) for n in range(24, 34)),
    "invalid/undefined-variable": (("M02", {}),),
    "invalid/division-by-zero": (
        ("V06", {"x": "total", "5": "10"}), ("M08", {}),
    ),
    "invalid/repeat-zero": (("M09", {}),),
    "invalid/unsupported-list": (("X02", {}),),
    "ambiguous/missing-increase": (
        ("V06", {"x": "score", "5": "10"}), ("A01", {}),
    ),
    "ambiguous/empty-reference": (("A02", {}),),
    "ambiguous/typo": (
        ("V06", {"x": "score", "5": "10"}), ("A04", {}),
    ),
    "ambiguous/a12-three-alternatives": (("A12", {}),),
    "ambiguous/a13-assignment-alternatives": (("V06", {}), ("A13", {})),
    "ambiguous/a14-quoted-alternatives": (("A14", {}),),
    "ambiguous/a15-division-scope": (
        ("V06", {"x": "total", "5": "10"}), ("A15", {}),
    ),
    "ambiguous/a16-block-scope": (("V06", {}), ("A16", {})),
    "ambiguous/a17-assignment-typo": (
        ("V06", {"x": "score", "5": "10"}), ("A17", {}),
    ),
    "ambiguous/a18-pronoun-before-amount": (("A18", {}),),
}
ERRORS = {
    "M02": "semantic E201: x is used before it is created",
    "M08": "semantic E206: cannot divide by zero",
    "M09": (
        "semantic E207: REPEAT needs a whole number of times from 1 to 1000, "
        "not 0"
    ),
}


class _PipelineResult(Protocol):
    """Test adapter's provisional view of the future pipeline result."""

    diagnostics: list[Diagnostic]
    question: str | None
    status: str
    notes: list[str]
    minilang: str | None


def _fixture_session(steps: tuple[Step, ...]) -> tuple[str, str]:
    sentences = []
    outputs = []
    for fixture_id, replacements in steps:
        fixture = FIXTURES[fixture_id]
        sentence = fixture["input"]
        if "expected_minilang" in fixture:
            output = fixture["expected_minilang"]
        elif "expected_question" in fixture:
            output = fixture["expected_question"]
        elif fixture_id in ERRORS:
            output = ERRORS[fixture_id]
        else:
            output = (
                f'{fixture["expected_status"]}: '
                f'{fixture["expected_reason_code"]}'
            )
        for original, replacement in replacements.items():
            sentence = sentence.replace(original, replacement)
            output = output.replace(original, replacement)
        sentences.append(sentence)
        outputs.append(output)
    return "\n".join(sentences) + "\n", "\n".join(outputs) + "\n"


def test_examples_have_exactly_one_expected_partner() -> None:
    inputs = {
        path.relative_to(EXAMPLES).with_suffix("").as_posix()
        for path in EXAMPLES.glob("*/*.txt")
    }
    expected = {
        path.relative_to(EXAMPLES).with_suffix("").as_posix()
        for path in EXAMPLES.glob("*/*.expected")
    }
    assert inputs == expected == set(SOURCES)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_example_matches_its_source_fixtures(name: str) -> None:
    text, expected = _fixture_session(SOURCES[name])
    assert (EXAMPLES / f"{name}.txt").read_text(encoding="utf-8") == text
    assert (EXAMPLES / f"{name}.expected").read_text(
        encoding="utf-8",
    ) == expected


@pytest.fixture
def compile_sentence() -> Callable[..., _PipelineResult]:
    # The concurrent pipeline tests establish run(text, session) as the API.
    # Do not silently skip API mismatches once the pipeline is implemented.
    entry = getattr(pipeline, "run", None)
    if not callable(entry):
        body = ast.parse(inspect.getsource(pipeline)).body
        docstring_only = (
            len(body) == 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )
        if not body or docstring_only:
            pytest.skip(
                "parsley.pipeline is unimplemented; end-to-end example "
                "comparison awaits pipeline wiring"
            )
        pytest.fail(
            "Pipeline is implemented: update the example adapter to its "
            "public sentence entry point"
        )
    return entry


def _result_text(result: _PipelineResult) -> str:
    """Project a pipeline result to code, a question, or an error.

    TODO: Align field access with the pipeline owner's final result type.
    Trace, back-translation and warnings are not part of the golden projection.
    Errors take precedence so erroneous code cannot look like a successful run.
    """
    if result.status == "unsupported":
        assert result.notes, "Unsupported results must explain their reason"
        return "unsupported: " + ", ".join(sorted(result.notes))
    if result.question is not None:
        return result.question
    errors = [d for d in result.diagnostics if d.level == "error"]
    if errors:
        return "\n".join(f"{d.stage} {d.code}: {d.message}" for d in errors)
    assert result.minilang, "Accepted sentences must produce MiniLang"
    return result.minilang


@pytest.mark.parametrize(
    "result, expected",
    [
        (SimpleNamespace(
            diagnostics=[
                Diagnostic("error", "candidates", "E101", "rejected"),
            ],
            status="unsupported", notes=["NO_MATCH"], question=None,
            minilang=None,
        ), "unsupported: NO_MATCH"),
        (SimpleNamespace(
            diagnostics=[Diagnostic("error", "ambiguity", "E102", "clarify")],
            status="ambiguous", notes=[], question="What should be printed?",
            minilang=None,
        ), "What should be printed?"),
        (SimpleNamespace(
            diagnostics=[Diagnostic("error", "semantic", "E201", "undefined")],
            status="ok", notes=[], question=None, minilang="PRINT x;",
        ), "semantic E201: undefined"),
        (SimpleNamespace(
            diagnostics=[Diagnostic("warning", "context", "W101", "implicit")],
            status="ok", notes=[], question=None, minilang="LET x = 5;",
        ), "LET x = 5;"),
    ],
)
def test_golden_projection(result: SimpleNamespace, expected: str) -> None:
    assert _result_text(result) == expected


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_example_through_pipeline(
    name: str, compile_sentence: Callable[..., _PipelineResult],
) -> None:
    session = Session()
    outputs = []
    text = (EXAMPLES / f"{name}.txt").read_text(encoding="utf-8")
    for sentence in text.splitlines():
        if sentence.strip():
            result = compile_sentence(sentence, session=session)
            outputs.append(_result_text(result))
    expected = (EXAMPLES / f"{name}.expected").read_text(encoding="utf-8")
    assert "\n".join(outputs) + "\n" == expected
