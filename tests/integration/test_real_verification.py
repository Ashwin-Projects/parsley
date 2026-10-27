"""Real V2/V3 checks and CLI summaries for the valid development corpus."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal, TypedDict

import pytest

from parsley.compiler.ast_nodes import Program
from parsley.compiler.codegen import generate
from parsley.pipeline import PipelineResult, run
from parsley.session import Session
from parsley.verify import ast_eval, interpreter, roundtrip


class Given(TypedDict):
    symbols: dict[str, Literal["number", "string"]]
    ref_stack: list[str]


class ValidFixture(TypedDict):
    id: str
    input: str
    given: Given
    expected_minilang: str


ROOT = Path(__file__).resolve().parents[2]
VALID_FIXTURES: list[ValidFixture] = json.loads(
    (ROOT / "tests/fixtures/valid.json").read_text(encoding="utf-8"),
)["fixtures"]
VALID_SESSIONS = sorted((ROOT / "examples/valid").glob("*.txt"))
SUMMARY = "V1 ok | V2 ok | V3 ok"

assert VALID_FIXTURES, "No valid fixtures were discovered"
assert VALID_SESSIONS, "No valid example sessions were discovered"


def _setup_sentences(given: Given) -> list[str]:
    """Seed executable history in the fixture's symbol insertion order."""
    sentences = []
    for name, kind in given["symbols"].items():
        assert kind in ("number", "string"), f"Unknown fixture type: {kind}"
        value = "0" if kind == "number" else '"text"'
        sentences.append(f"let {name} be {value}")
    return sentences


def _assert_verified(
    result: PipelineResult, session: Session, context: str,
) -> None:
    assert result.status == "ok", (
        context, result.status, result.diagnostics, result.question,
    )
    assert result.minilang is not None, context
    assert result.trace.ast is not None, context
    verification = result.verification
    assert verification is not None, context
    assert verification.back_translation == result.back_translation, context
    assert verification.back_translation, context
    assert verification.v2_match is True, (context, verification.details)
    assert verification.v3_match is True, (context, verification.details)
    assert result.trace.verification == verification, context

    # Call the public layers as well: no fake functions or skipped modules.
    difference = roundtrip.check(result.minilang, Program((result.trace.ast,)))
    assert difference is None, (context, difference)
    program = Program(tuple(session.history))
    from_ast = ast_eval.run(program)
    from_source = interpreter.run(generate(program))
    assert from_ast == from_source, (context, from_ast, from_source)
    # Agreement on a run-time error is insufficient for this valid corpus.
    assert from_ast[2] == [], (context, from_ast[2])


def _assert_cli(source: Path, sentences: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "parsley", "--file", str(source)],
        cwd=ROOT, env=env, input="", capture_output=True,
        encoding="utf-8", timeout=15, check=False,
    )
    context = (source.name, sentences, completed.stdout, completed.stderr)
    assert completed.returncode == 0, context
    summaries = [
        line for line in completed.stdout.splitlines()
        if line.startswith("V1 ")
    ]
    assert summaries == [SUMMARY] * len(sentences), context


@pytest.mark.parametrize(
    "fixture", VALID_FIXTURES, ids=lambda item: item["id"],
)
def test_valid_fixture_passes_real_v2_and_v3(fixture: ValidFixture) -> None:
    session = Session()
    for sentence in _setup_sentences(fixture["given"]):
        _assert_verified(
            run(sentence, session), session, f"setup: {sentence!r}",
        )
    assert session.ref_stack == fixture["given"]["ref_stack"], fixture["id"]
    context = f'{fixture["id"]}: {fixture["input"]!r}'
    result = run(fixture["input"], session)
    _assert_verified(result, session, context)
    assert result.minilang == fixture["expected_minilang"], context


@pytest.mark.parametrize(
    "fixture", VALID_FIXTURES, ids=lambda item: item["id"],
)
def test_valid_fixture_cli_reports_all_layers_ok(
    fixture: ValidFixture, tmp_path: Path,
) -> None:
    sentences = [*_setup_sentences(fixture["given"]), fixture["input"]]
    source = tmp_path / f'{fixture["id"]}.txt'
    source.write_text("\n".join(sentences) + "\n", encoding="utf-8")
    _assert_cli(source, sentences)


@pytest.mark.parametrize("source", VALID_SESSIONS, ids=lambda path: path.stem)
def test_valid_example_session_passes_real_v2_and_v3(source: Path) -> None:
    session = Session()
    outputs: list[str] = []
    for line_number, sentence in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1,
    ):
        if not sentence.strip():
            continue
        context = f"{source.name}:{line_number}: {sentence!r}"
        result = run(sentence, session)
        _assert_verified(result, session, context)
        assert result.minilang is not None, context
        outputs.append(result.minilang)
    assert outputs, source
    expected = source.with_suffix(".expected").read_text(encoding="utf-8")
    assert "\n".join(outputs) + "\n" == expected, source


@pytest.mark.parametrize("source", VALID_SESSIONS, ids=lambda path: path.stem)
def test_valid_example_cli_reports_all_layers_ok(source: Path) -> None:
    sentences = [
        line for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert sentences, source
    _assert_cli(source, sentences)
