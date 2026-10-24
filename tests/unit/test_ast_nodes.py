"""AST nodes are frozen, comparable dataclasses (Phase 3 step 1; ARCHITECTURE.md 2.8)."""

import dataclasses

import pytest

from parsley.compiler.ast_nodes import (
    Assign,
    BinOp,
    Compare,
    If,
    Let,
    Neg,
    Num,
    Print,
    Program,
    Repeat,
    Str,
    Var,
)


def sample_program():
    """IF age > 17 THEN { PRINT "adult"; } ELSE { x = -(x + 1); } REPEAT 2 TIMES { PRINT x; }"""
    return Program(
        statements=(
            Let(name="age", value=Num("20")),
            If(
                condition=Compare(op=">", left=Var("age"), right=Num("17")),
                then_body=(Print(Str("adult")),),
                else_body=(Assign(name="x", value=Neg(BinOp("+", Var("x"), Num("1")))),),
            ),
            Repeat(count=Num("2"), body=(Print(Var("x")),)),
        )
    )


def test_structurally_equal_trees_are_equal():
    assert sample_program() == sample_program()


def test_equal_trees_hash_equal():
    assert hash(sample_program()) == hash(sample_program())


@pytest.mark.parametrize(
    "left, right",
    [
        (Num("2"), Num("2.0")),
        (Str("hello"), Str("Hello")),
        (Var("x"), Str("x")),
        (Neg(Num("5")), Num("5")),
        (BinOp("+", Var("x"), Num("1")), BinOp("-", Var("x"), Num("1"))),
        (BinOp("*", BinOp("+", Num("1"), Num("2")), Num("3")),
         BinOp("+", Num("1"), BinOp("*", Num("2"), Num("3")))),
        (Compare(">", Var("a"), Num("1")), Compare(">=", Var("a"), Num("1"))),
        (Let("x", Num("1")), Assign("x", Num("1"))),
        (If(Compare("==", Var("a"), Num("1")), (Print(Var("a")),), None),
         If(Compare("==", Var("a"), Num("1")), (Print(Var("a")),), ())),
    ],
)
def test_different_trees_are_not_equal(left, right):
    assert left != right


def test_if_without_else_defaults_to_none():
    node = If(Compare("<", Var("a"), Num("1")), (Print(Var("a")),))
    assert node.else_body is None


@pytest.mark.parametrize(
    "node, field",
    [
        (Num("1"), "text"),
        (Str("a"), "value"),
        (Var("a"), "name"),
        (Neg(Num("1")), "operand"),
        (BinOp("+", Num("1"), Num("2")), "op"),
        (Compare("<", Num("1"), Num("2")), "right"),
        (Let("a", Num("1")), "name"),
        (Assign("a", Num("1")), "value"),
        (Print(Num("1")), "value"),
        (If(Compare("<", Num("1"), Num("2")), ()), "then_body"),
        (Repeat(Num("1"), ()), "count"),
        (Program(()), "statements"),
    ],
)
def test_nodes_are_immutable(node, field):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(node, field, None)
