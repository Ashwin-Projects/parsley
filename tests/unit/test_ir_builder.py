"""IR builder [D]: Candidate -> AST, one function per intent (Phase 3; ARCHITECTURE.md 2.9)."""

import json
from pathlib import Path

import pytest

from parsley.compiler.ast_nodes import Assign, BinOp, Compare, If, Let, Neg, Num, Print, Repeat, Str, Var
from parsley.compiler.ir_builder import IRBuildError, MissingSlotError, UnresolvedSlotError, build
from parsley.nlp.candidates import Candidate, generate

VALID = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "valid.json").read_text(encoding="utf-8"))
FIXTURES = {fx["id"]: fx for fx in VALID["fixtures"]}

# Hand-built expected ASTs (they match each fixture's expected_minilang).
EXPECTED = {
    "V01": Let("age", Num("20")),
    "V02": Let("totalAmount", Num("0")),
    "V03": Let("greeting", Str("Hello")),
    "V05": Assign("price", Num("2.5")),
    "V07": Assign("count", BinOp("+", Var("count"), Num("2"))),
    "V08": Assign("score", BinOp("+", Var("score"), Num("5"))),
    "V09": Assign("count", BinOp("-", Var("count"), Num("1"))),
    "V10": Assign("total", BinOp("*", Var("total"), Num("3"))),
    "V11": Assign("total", BinOp("/", Var("total"), Num("2"))),
    "V13": Print(Str("Hello")),
    "V23": Assign("x", Neg(Num("5"))),
    "V24": Let("x", Num("5")),
    "V25": Assign("x", BinOp("+", Var("x"), Num("2"))),
    "V28": Assign("x", BinOp("+", Var("x"), Num("2"))),
    "V29": Assign("x", BinOp("-", Var("x"), Num("2"))),
    "V30": Assign("x", Num("20")),
}

# Words fine, but the statement itself needs the symbol table (resolved in Phase 6).
NEEDS_CONTEXT = {"V06": "implicit declaration: LET instead of assignment needs the symbol table"}


def needs_resolution(slot):
    if isinstance(slot, dict):
        return slot.get("kind") in ("word", "pronoun") or any(needs_resolution(v) for v in slot.values())
    return False


def name(text):
    return {"kind": "name", "text": text}


def text(value):
    return {"kind": "string", "text": value, "quoted": False}


def number(value):
    return {"kind": "number", "text": value}


def statement(intent, **slots):
    return {"kind": "statement", "intent": intent, "slots": slots}


# Phase 3 exit test


def test_exit_set_is_every_fixture_needing_no_resolution():
    eligible = {
        fx_id for fx_id, fx in FIXTURES.items()
        if not needs_resolution(fx["expected_slots"]) and fx_id not in NEEDS_CONTEXT
    }
    assert eligible == set(EXPECTED)


@pytest.mark.parametrize("fx_id", sorted(EXPECTED))
def test_ir_builder_output_equals_hand_built_ast(fx_id):
    top = generate(FIXTURES[fx_id]["input"]).candidates[0]
    assert build(top) == EXPECTED[fx_id]


# Every intent, using candidates as the context resolver (Phase 6) will hand them over


def test_if_with_else():
    candidate = Candidate("if", {
        "condition": {"kind": "condition", "op": ">", "left": name("age"), "right": number("17")},
        "then": statement("print", value=text("adult")),
        "else": statement("print", value=text("minor")),
    }, 1.0, "IF2")
    assert build(candidate) == If(Compare(">", Var("age"), Num("17")), (Print(Str("adult")),), (Print(Str("minor")),))


def test_if_without_else_has_no_else_body():
    candidate = Candidate("if", {
        "condition": {"kind": "condition", "op": ">=", "left": name("score"), "right": number("10")},
        "then": statement("print", value=text("winner")),
    }, 1.0, "IF1")
    assert build(candidate) == If(Compare(">=", Var("score"), Num("10")), (Print(Str("winner")),))


def test_repeat():
    candidate = Candidate("repeat", {
        "count": {"kind": "count", "text": "3"},
        "body": statement("increment", name=name("i"), amount=number("1")),
    }, 1.0, "REP1")
    assert build(candidate) == Repeat(Num("3"), (Assign("i", BinOp("+", Var("i"), Num("1"))),))


def test_resolved_name_in_a_value_is_a_variable():
    assert build(Candidate("print", {"value": name("age")}, 1.0, "P1")) == Print(Var("age"))


def test_compound_amount_keeps_its_grouping():
    amount = {"kind": "binop", "op": "+", "left": number("2"), "right": number("3")}
    candidate = Candidate("multiply", {"name": name("x"), "amount": amount}, 1.0, "MUL1")
    assert build(candidate) == Assign("x", BinOp("*", Var("x"), BinOp("+", Num("2"), Num("3"))))


# Unresolved or missing slots are a clear error, never a guess


@pytest.mark.parametrize(
    "sentence, path",
    [
        ("print age", "value"),  # bare word
        ("set age to age plus 1", "value.left"),  # nested bare word
        ("add 5 to it", "name"),  # pronoun
        ("if score is at least 10 then print winner", "condition.left"),
        ("repeat 3 times print hello", "body.value"),
    ],
)
def test_unresolved_slot_raises_with_its_path(sentence, path):
    with pytest.raises(UnresolvedSlotError) as error:
        build(generate(sentence).candidates[0])
    assert error.value.path == path


def test_missing_slot_raises_with_its_path():
    with pytest.raises(MissingSlotError) as error:
        build(generate("increase score").candidates[0])
    assert error.value.path == "amount"


def test_errors_share_one_base_class():
    assert issubclass(UnresolvedSlotError, IRBuildError)
    assert issubclass(MissingSlotError, IRBuildError)


def test_unknown_intent_is_an_error():
    with pytest.raises(IRBuildError):
        build(Candidate("sort", {}, 1.0, "X"))


def test_unknown_slot_kind_is_an_error():
    with pytest.raises(IRBuildError):
        build(Candidate("print", {"value": {"kind": "list", "items": []}}, 1.0, "P1"))


# Malformed candidates always raise IRBuildError (never KeyError / AttributeError), with a path


@pytest.mark.parametrize(
    "candidate, path",
    [
        (Candidate("print", {"value": {"kind": "number"}}, 1.0, "P1"), "value.text"),
        (Candidate("print", {"value": "x"}, 1.0, "P1"), "value"),
        (Candidate("print", {"value": {"kind": "binop", "op": "+", "left": number("1")}}, 1.0, "P1"),
         "value.right"),
        (Candidate("print", {"value": {"kind": "binop", "op": "^", "left": number("1"), "right": number("2")}},
                   1.0, "P1"), "value.op"),
        (Candidate("if", {"condition": {"kind": "condition", "op": "??", "left": number("1"), "right": number("2")},
                          "then": statement("print", value=number("1"))}, 1.0, "IF1"), "condition.op"),
        (Candidate("repeat", {"count": {"kind": "count", "text": "2"}, "body": {"kind": "statement"}}, 1.0, "REP1"),
         "body.intent"),
        (Candidate("declare", {"name": name("let"), "value": number("1")}, 1.0, "D1"), "name"),
        (Candidate("declare", {"name": name("2x"), "value": number("1")}, 1.0, "D1"), "name"),
    ],
)
def test_malformed_candidate_raises_ir_build_error_with_path(candidate, path):
    with pytest.raises(IRBuildError) as error:
        build(candidate)
    assert error.value.path == path
