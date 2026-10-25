"""Semantic analyzer (Phase 4): checks, diagnostics, and session updates.

The fixture tests at the bottom are the Phase 4 exit test. They go English -> candidates
-> context resolver -> IR -> semantic.
"""

import json
from pathlib import Path

import pytest

from parsley.compiler import ir_builder
from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, If, Let, Neg, Num, Print, Program, Repeat, Str, Var,
)
from parsley.compiler.semantic import analyze
from parsley.compiler.symbols import Symbol, SymbolTable
from parsley.nlp.candidates import generate
from parsley.nlp.context import resolve
from parsley.session import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def session_with(**types):
    table = SymbolTable()
    for i, (name, kind) in enumerate(types.items()):
        table.declare(name, kind, i)
    return Session(symbol_table=table, ref_stack=list(types))


def codes(stmt, session):
    return [d.code for d in analyze(stmt, session)]


# Clean statements


def test_clean_declaration_has_no_diagnostics():
    assert analyze(Let("age", Num("20")), Session()) == []


def test_clean_program_across_sentences():
    session = Session()
    for stmt in [
        Let("score", Num("10")),
        Assign("score", BinOp("+", Var("score"), Num("5"))),
        Let("name", Str("Ann")),
        Print(BinOp("+", Var("name"), Str("!"))),
        If(Compare("==", Var("name"), Str("Bob")), (Print(Var("score")),), (Print(Str("no")),)),
        Repeat(Num("3"), (Assign("score", BinOp("*", Var("score"), Neg(Num("2")))),)),
        Print(BinOp("/", Var("score"), Num("0.5"))),
    ]:
        assert analyze(stmt, session) == []


# E201: used before created


def test_undefined_variable_in_value():
    [d] = analyze(Print(Var("score")), Session())
    assert (d.level, d.stage, d.code) == ("error", "semantic", "E201")
    assert d.message == "score is used before it is created"


def test_assignment_to_undefined_variable():
    assert codes(Assign("x", Num("1")), Session()) == ["E201"]


def test_let_cannot_read_the_name_it_creates():
    assert codes(Let("x", BinOp("+", Var("x"), Num("1"))), Session()) == ["E201"]


def test_undefined_variable_inside_blocks_and_conditions():
    session = session_with(n="number")
    assert codes(If(Compare(">", Var("a"), Num("1")), (Print(Var("b")),)), session) == ["E201", "E201"]
    assert codes(Repeat(Num("2"), (Assign("c", Num("1")),)), session) == ["E201"]


def test_each_use_is_reported_once_per_occurrence():
    assert codes(Print(BinOp("+", Var("x"), Var("x"))), Session()) == ["E201", "E201"]


# E202: LET inside a block


def test_let_inside_if_block():
    [d] = analyze(If(Compare(">", Num("1"), Num("0")), (Let("x", Num("1")),)), Session())
    assert (d.level, d.code) == ("error", "E202")
    assert d.message == "variables must be created outside IF and REPEAT blocks"


def test_let_inside_else_and_repeat_blocks():
    cond = Compare(">", Num("1"), Num("0"))
    assert codes(If(cond, (Print(Num("1")),), (Let("x", Num("1")),)), Session()) == ["E202"]
    assert codes(Repeat(Num("2"), (Let("x", Num("1")),)), Session()) == ["E202"]


# E203 / E204 / E205: types


@pytest.mark.parametrize("op", ["-", "*", "/"])
def test_arithmetic_on_text(op):
    session = session_with(name="string")
    [d] = analyze(Print(BinOp(op, Var("name"), Num("2"))), session)
    assert (d.level, d.code) == ("error", "E203")
    assert "name is text" in d.message


def test_arithmetic_on_text_literal_on_the_right():
    assert codes(Print(BinOp("*", Num("2"), Str("a"))), Session()) == ["E203"]


def test_negating_text():
    [d] = analyze(Print(Neg(Str("a"))), Session())
    assert d.code == "E203"
    assert '"a" is text' in d.message


def test_text_plus_number():
    session = session_with(name="string")
    [d] = analyze(Assign("name", BinOp("+", Var("name"), Num("5"))), session)
    assert (d.level, d.code) == ("error", "E204")
    assert d.message == "cannot add text and a number: name is text and 5 is a number"


def test_text_compared_with_number():
    session = session_with(name="string")
    [d] = analyze(If(Compare("==", Num("3"), Var("name")), (Print(Num("1")),)), session)
    assert d.code == "E204"
    assert d.message == "cannot compare text with a number: 3 is a number and name is text"


@pytest.mark.parametrize("op,phrase", [
    (">", "is greater than"), ("<", "is less than"),
    (">=", "is greater than or equal to"), ("<=", "is less than or equal to"),
])
def test_text_supports_only_equality_comparisons(op, phrase):
    [d] = analyze(If(Compare(op, Str("a"), Str("b")), (Print(Num("1")),)), Session())
    assert (d.level, d.code) == ("error", "E205")
    assert phrase in d.message


@pytest.mark.parametrize("op", ["==", "!="])
def test_text_equality_is_allowed(op):
    assert codes(If(Compare(op, Str("a"), Str("b")), (Print(Num("1")),)), Session()) == []


def test_text_concatenation_is_allowed():
    assert codes(Print(BinOp("+", Str("a"), Str("b"))), Session()) == []


def test_concatenation_result_is_text():
    assert codes(Print(BinOp("-", BinOp("+", Str("a"), Str("b")), Num("1"))), Session()) == ["E203"]


def test_undefined_operand_does_not_cascade_into_type_errors():
    assert codes(Print(BinOp("+", Var("ghost"), Str("a"))), Session()) == ["E201"]
    assert codes(If(Compare(">", Var("ghost"), Str("a")), (Print(Num("1")),)), Session()) == ["E201"]


def test_mixed_subexpression_does_not_cascade():
    assert codes(Print(BinOp("+", BinOp("+", Str("a"), Num("1")), Num("2"))), Session()) == ["E204"]


# E206: division by literal zero


@pytest.mark.parametrize("zero", [Num("0"), Num("0.0"), Neg(Num("0"))])
def test_division_by_literal_zero(zero):
    [d] = analyze(Print(BinOp("/", Num("4"), zero)), Session())
    assert (d.level, d.code, d.message) == ("error", "E206", "cannot divide by zero")


def test_division_by_zero_variable_is_not_a_literal():
    assert codes(Print(BinOp("/", Num("4"), Var("z"))), session_with(z="number")) == []


@pytest.mark.parametrize("text", ["nan", "inf", "1_0", "²"])
def test_odd_number_text_is_not_zero_and_does_not_crash(text):
    assert codes(Print(BinOp("/", Num("4"), Num(text))), Session()) == []


def test_zero_numerator_is_fine():
    assert codes(Print(BinOp("/", Num("0"), Num("4"))), Session()) == []


# E207: REPEAT count


@pytest.mark.parametrize("count", ["1", "1000"])
def test_repeat_count_bounds_are_inclusive(count):
    assert codes(Repeat(Num(count), (Print(Num("1")),)), Session()) == []


@pytest.mark.parametrize("count", ["0", "1001", "2.5", "3.0", "²", "①"])
def test_repeat_count_outside_range_or_not_whole(count):
    [d] = analyze(Repeat(Num(count), (Print(Num("1")),)), Session())
    assert (d.level, d.code) == ("error", "E207")
    assert count in d.message


# W208: redeclaration


def test_redeclaration_is_a_warning():
    session = session_with(age="number")
    [d] = analyze(Let("age", Num("3")), session)
    assert (d.level, d.code) == ("warning", "W208")
    assert "age" in d.message


def test_redeclaration_still_updates_the_session():
    session = session_with(age="number")
    analyze(Let("age", Str("old")), session)
    assert session.symbols["age"] == Symbol("age", "string", 0)
    assert session.history == [Let("age", Str("old"))]


# Session updates


def test_accepted_declaration_writes_symbol_table_and_history():
    session = Session()
    analyze(Let("age", Num("20")), session)
    analyze(Let("name", Str("Ann")), session)
    assert session.symbols["age"] == Symbol("age", "number", 0)
    assert session.symbols["name"] == Symbol("name", "string", 1)
    assert session.history == [Let("age", Num("20")), Let("name", Str("Ann"))]


def test_statement_with_an_error_changes_nothing():
    session = session_with(n="number")
    before = (dict(session.symbols), list(session.ref_stack), list(session.history))
    analyze(Let("x", Var("ghost")), session)
    analyze(Assign("n", BinOp("/", Var("n"), Num("0"))), session)
    assert (dict(session.symbols), session.ref_stack, session.history) == before


def test_assignment_must_keep_the_type():
    session = session_with(x="number")
    [d] = analyze(Assign("x", Str("hi")), session)
    assert (d.level, d.code) == ("error", "E209")
    assert d.message == "x is a number, so it cannot be set to text"
    assert session.symbols["x"] == Symbol("x", "number", 0)


def test_assignment_inside_a_block_must_keep_the_type():
    session = session_with(name="string")
    cond = Compare("==", Var("name"), Str("a"))
    assert codes(If(cond, (Assign("name", Num("1")),)), session) == ["E209"]
    assert session.symbols["name"].type == "string"


def test_let_at_top_level_may_change_the_type():
    session = session_with(x="number")
    assert codes(Let("x", Str("hi")), session) == ["W208"]
    assert codes(Print(BinOp("+", Var("x"), Str("!"))), session) == []


def test_assignment_of_unknown_type_is_not_a_type_change():
    assert codes(Assign("x", Var("ghost")), session_with(x="number")) == ["E201"]


def test_reference_stack_puts_assigned_name_last():
    session = session_with(a="number", b="number", c="number")
    analyze(Assign("a", BinOp("+", Var("b"), Num("1"))), session)
    assert session.ref_stack == ["c", "b", "a"]


def test_reference_stack_tracks_reads_and_has_no_duplicates():
    session = session_with(a="number", b="number")
    analyze(Print(Var("a")), session)
    assert session.ref_stack == ["b", "a"]
    analyze(If(Compare(">", Var("b"), Num("0")), (Print(Str("x")),)), session)
    assert session.ref_stack == ["a", "b"]


def test_reference_stack_after_declaration():
    session = Session()
    analyze(Let("score", Num("10")), session)
    assert session.ref_stack == ["score"]


def test_print_of_literal_leaves_reference_stack_alone():
    session = session_with(a="number")
    analyze(Print(Str("hello")), session)
    assert session.ref_stack == ["a"]


def test_nested_blocks_are_checked_and_recorded():
    session = session_with(a="number", b="number")
    inner = Repeat(Num("2"), (Assign("a", BinOp("+", Var("b"), Num("1"))),))
    stmt = If(Compare(">", Var("b"), Num("0")), (inner,))
    assert codes(stmt, session) == []
    assert session.ref_stack == ["b", "a"]
    nested_let = If(Compare(">", Num("1"), Num("0")), (Repeat(Num("2"), (Let("z", Num("1")),)),))
    assert codes(nested_let, session) == ["E202"]
    assert "z" not in session.symbols


def test_assignment_in_block_to_undefined_name_is_not_recorded():
    session = Session()
    assert codes(Repeat(Num("2"), (Assign("c", Num("1")),)), session) == ["E201"]
    assert session.history == [] and "c" not in session.symbols


@pytest.mark.parametrize("node", [Program((Print(Num("1")),)), "PRINT 1;", None])
def test_unknown_node_raises_type_error(node):
    session = Session()
    with pytest.raises(TypeError):
        analyze(node, session)  # type: ignore[arg-type]
    assert session.history == []


def test_unknown_expression_raises_type_error():
    with pytest.raises(TypeError):
        analyze(Print(Compare("==", Num("1"), Num("1"))), Session())  # type: ignore[arg-type]


def test_diagnostics_are_in_source_order():
    stmt = If(Compare(">", Var("u"), Num("1")),
              (Print(BinOp("/", Num("1"), Num("0"))),),
              (Let("y", Num("1")),))
    assert codes(stmt, Session()) == ["E201", "E206", "E202"]


# Phase 4 exit test: semantic fixtures from English


def _load(category):
    return json.loads((FIXTURES / f"{category}.json").read_text(encoding="utf-8"))["fixtures"]


def _session_from(given):
    table = SymbolTable()
    for i, (name, kind) in enumerate(given["symbols"].items()):
        table.declare(name, kind, i)
    return Session(symbol_table=table, ref_stack=list(given["ref_stack"]))


def _english_to_stmt(fixture, session):
    result = generate(fixture["input"])
    assert result.status == "ok", result
    [best, *_] = resolve(result.candidates, session)
    assert best.question is None, best.question
    return ir_builder.build(best.candidate)


@pytest.mark.parametrize("fixture", _load("semantic"), ids=lambda f: f["id"])
def test_semantic_fixture_produces_expected_diagnostics(fixture):
    session = _session_from(fixture["given"])
    stmt = _english_to_stmt(fixture, session)
    diagnostics = analyze(stmt, session)
    assert [d.code for d in diagnostics] == fixture["expected_diagnostic_codes"]
    assert all(d.stage == "semantic" and d.message for d in diagnostics)


@pytest.mark.parametrize("fixture", _load("valid"), ids=lambda f: f["id"])
def test_valid_fixture_produces_no_semantic_diagnostics(fixture):
    session = _session_from(fixture["given"])
    stmt = _english_to_stmt(fixture, session)
    assert analyze(stmt, session) == []


def test_check_only_mode_reports_but_records_nothing():
    session = session_with(n="number")
    before = (dict(session.symbols), list(session.ref_stack), list(session.history))
    assert analyze(Let("x", Num("1")), session, record=False) == []
    assert [d.code for d in analyze(Let("n", Num("2")), session, record=False)] == ["W208"]
    assert (dict(session.symbols), session.ref_stack, session.history) == before
    assert analyze(Let("x", Num("1")), session) == [] and "x" in session.symbols
