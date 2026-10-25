"""V1 templates: every AST node has a canonical English rendering."""

import pytest

from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, If, Let, Neg, Num, Print, Program, Repeat,
    Str, Var,
)
from parsley.verify import backtranslate


@pytest.mark.parametrize(
    "node, expected",
    [
        (Num("02.50"), "02.50"),
        (Str('say "Hi" at C:\\tmp'), '"say \\"Hi\\" at C:\\\\tmp"'),
        (Str("age"), '"age"'),
        (Var("totalAmount"), "totalAmount"),
        (Neg(Num("5")), "negative (5)"),
        (Neg(BinOp("+", Num("1"), Num("2"))),
         "negative ((1 plus 2))"),
        (BinOp("+", Num("1"), Num("2")), "(1 plus 2)"),
        (BinOp("-", Num("1"), Num("2")), "(1 minus 2)"),
        (BinOp("*", Num("1"), Num("2")), "(1 times 2)"),
        (BinOp("/", Num("1"), Num("2")), "(1 divided by 2)"),
        (Let("age", Num("20")), "create variable age with value 20."),
        (Assign("x", Num("5")), "set x to 5."),
        (Assign("x", BinOp("+", Var("x"), Num("5"))),
         "increase x by 5."),
        (Assign("x", BinOp("-", Var("x"), Num("5"))),
         "decrease x by 5."),
        (Assign("x", BinOp("*", Var("x"), Num("5"))),
         "multiply x by 5."),
        (Assign("x", BinOp("/", Var("x"), Num("5"))),
         "divide x by 5."),
        (Assign("x", BinOp("+", Var("y"), Num("5"))),
         "set x to (y plus 5)."),
        (Print(Str("Hello")), 'print "Hello".'),
        (If(Compare(">", Var("age"), Num("17")),
            (Print(Str("adult")),)),
         'if age is greater than 17 then begin print "adult" end.'),
        (If(Compare("==", Var("x"), Num("1")),
            (Print(Num("1")),), (Print(Num("0")),)),
         "if x is equal to 1 then begin print 1 end "
         "else begin print 0 end."),
        (Repeat(Num("3"), (Print(Str("hello")),)),
         'repeat 3 times begin print "hello" end.'),
        (Program((Let("x", Num("1")), Print(Var("x")))),
         "create variable x with value 1; print x."),
        (Program(()), ""),
    ],
)
def test_node_template(node, expected: str) -> None:
    assert backtranslate.backtranslate(node) == expected


@pytest.mark.parametrize(
    "op, phrase",
    [(">", "is greater than"), ("<", "is less than"),
     ("==", "is equal to"), ("!=", "is not equal to"),
     (">=", "is greater than or equal to"),
     ("<=", "is less than or equal to")],
)
def test_comparison_template(op: str, phrase: str) -> None:
    node = Compare(op, Var("x"), Num("2"))
    assert backtranslate.backtranslate(node) == f"x {phrase} 2"


def test_arithmetic_grouping_is_explicit() -> None:
    node = BinOp("*", BinOp("+", Num("1"), Num("2")), Num("3"))
    assert backtranslate.backtranslate(node) == "((1 plus 2) times 3)"


def test_update_amount_keeps_its_grouping() -> None:
    node = Assign(
        "x", BinOp("/", Var("x"), BinOp("+", Num("2"), Num("3"))),
    )
    assert backtranslate.backtranslate(node) == "divide x by (2 plus 3)."


def test_nested_blocks_have_explicit_boundaries() -> None:
    node = Repeat(Num("2"), (
        If(Compare("!=", Var("x"), Num("0")), (Print(Var("x")),)),
        Print(Str("done")),
    ))
    assert backtranslate.backtranslate(node) == (
        'repeat 2 times begin if x is not equal to 0 then begin print x end; '
        'print "done" end.'
    )


def test_unknown_node_is_a_clear_error() -> None:
    with pytest.raises(TypeError, match="Unsupported AST node"):
        backtranslate.backtranslate(object())
