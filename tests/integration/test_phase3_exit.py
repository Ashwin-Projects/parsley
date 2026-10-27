"""Phase 3 exit: English ASTs equal independently parsed golden programs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict

import pytest

from parsley.compiler.ast_nodes import Program
from parsley.compiler.parser import parse
from parsley.pipeline import run
from parsley.session import Session


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

assert VALID_FIXTURES, "No valid fixtures were discovered"


@pytest.mark.parametrize(
    "fixture", VALID_FIXTURES, ids=lambda item: item["id"],
)
def test_english_ast_equals_parsed_golden_minilang(
    fixture: ValidFixture,
) -> None:
    session = Session()
    for name, kind in fixture["given"]["symbols"].items():
        assert kind in ("number", "string"), f"Unknown fixture type: {kind}"
        value = "0" if kind == "number" else '"text"'
        sentence = f"let {name} be {value}"
        setup = run(sentence, session)
        assert setup.status == "ok", (sentence, setup.diagnostics)
    assert session.ref_stack == fixture["given"]["ref_stack"], fixture["id"]

    context = f'{fixture["id"]}: {fixture["input"]!r}'
    result = run(fixture["input"], session)
    assert result.status == "ok", (
        context, result.diagnostics, result.question,
    )
    assert result.trace.ast is not None, context
    # Parse the fixture's gold, never code generated from the English AST.
    expected = parse(fixture["expected_minilang"])
    assert Program((result.trace.ast,)) == expected, context
