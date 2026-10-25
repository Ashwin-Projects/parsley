"""Canonical MiniLang output, checked against independent hand-built ASTs."""

import json
from pathlib import Path

import pytest

from parsley.compiler import codegen
from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, If, Let, Neg, Num, Print, Program, Repeat,
    Str, Var,
)
from test_ir_builder import EXPECTED as IR_ASTS


FIXTURES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "valid.json")
    .read_text(encoding="utf-8")
)["fixtures"]
ASTS = {
    **IR_ASTS,
    "V04": Assign("age", BinOp("+", Var("age"), Num("1"))),
    "V06": Let("x", Num("5")),
    "V12": Print(Var("age")),
    "V14": Print(Str("hello world")),
    "V15": Print(Str("total")),
    "V16": If(
        Compare(">", Var("age"), Num("17")),
        (Print(Str("adult")),), (Print(Str("minor")),),
    ),
    "V17": If(
        Compare(">=", Var("score"), Num("10")), (Print(Str("winner")),),
    ),
    "V18": Repeat(Num("3"), (Print(Str("hello")),)),
    "V19": Repeat(Num("2"), (Print(Var("score")),)),
    "V20": Assign("score", BinOp("+", Var("score"), Num("5"))),
    "V21": Print(Str("y")),
    "V22": Print(Str("store")),
}


def test_hand_built_asts_cover_every_valid_fixture() -> None:
    assert set(ASTS) == {fixture["id"] for fixture in FIXTURES}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda fx: fx["id"])
def test_valid_fixture_matches_exactly(fixture: dict) -> None:
    actual = codegen.generate(ASTS[fixture["id"]])
    assert actual == fixture["expected_minilang"]


@pytest.mark.parametrize(
    "expression, expected",
    [
        (BinOp("*", BinOp("+", Num("1"), Num("2")), Num("3")),
         "(1 + 2) * 3"),
        (BinOp("*", Var("x"), BinOp("+", Num("2"), Num("3"))),
         "x * (2 + 3)"),
        (BinOp("+", BinOp("*", Var("x"), Num("2")), Num("3")),
         "x * 2 + 3"),
        (BinOp("-", Var("a"), BinOp("-", Var("b"), Var("c"))),
         "a - (b - c)"),
        (BinOp("/", Var("a"), BinOp("*", Var("b"), Var("c"))),
         "a / (b * c)"),
        (BinOp("+", Var("a"), BinOp("+", Var("b"), Var("c"))),
         "a + (b + c)"),
        (BinOp("*", Var("a"), BinOp("/", Var("b"), Var("c"))),
         "a * (b / c)"),
        (BinOp("/", BinOp("*", Var("a"), Var("b")), Var("c")),
         "a * b / c"),
        (Neg(BinOp("+", Var("a"), Var("b"))), "-(a + b)"),
        (Neg(Neg(Var("x"))), "--x"),
        (BinOp("-", Var("a"), Neg(Num("5"))), "a - -5"),
        (BinOp("*", Neg(Var("x")), Num("2")), "-x * 2"),
        (Num("002.50"), "002.50"),
        (Str('say "Hi" at C:\\tmp'), '"say \\"Hi\\" at C:\\\\tmp"'),
        (Str(""), '""'),
    ],
)
def test_expression_grouping_and_literals(expression, expected: str) -> None:
    assert codegen.generate(expression) == expected


@pytest.mark.parametrize("op", [">", "<", "==", ">=", "<=", "!="])
def test_comparison_spacing(op: str) -> None:
    assert codegen.generate(Compare(op, Var("x"), Num("2"))) == f"x {op} 2"


def test_program_lines_have_no_trailing_newline() -> None:
    program = Program((Let("x", Num("1")), Print(Var("x"))))
    assert codegen.generate(program) == "LET x = 1;\nPRINT x;"


def test_empty_program() -> None:
    assert codegen.generate(Program(())) == ""


def test_block_statements_stay_on_one_line() -> None:
    node = Repeat(Num("2"), (Print(Num("1")), Print(Num("2"))))
    assert codegen.generate(node) == "REPEAT 2 TIMES { PRINT 1; PRINT 2; }"


def test_unknown_node_is_a_clear_error() -> None:
    with pytest.raises(TypeError, match="Unsupported AST node"):
        codegen.generate(object())
