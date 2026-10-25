"""End-to-end pipeline: normalize -> candidates -> context -> top -> IR -> semantic -> codegen -> V1.

The fixture tests are the exit test for this step: every valid fixture, run as a session,
gives exactly its expected MiniLang; context fixtures resolve (or ask) correctly; with
context off, the context-dependent fixtures fail cleanly.
"""

import json
from pathlib import Path

import pytest

from parsley.compiler.ast_nodes import Assign, BinOp, Let, Num, Var
from parsley.pipeline import run
from parsley.session import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Alternatives and operator scope belong to the ambiguity gate (next step).
GATE_ONLY = {"alternatives", "operator_scope"}


def load(category):
    return json.loads((FIXTURES / f"{category}.json").read_text(encoding="utf-8"))["fixtures"]


def session_from(given):
    """Build the fixture's session by running English declarations through the pipeline."""
    session = Session()
    for name, kind in given["symbols"].items():
        value = "0" if kind == "number" else '"text"'
        assert run(f"let {name} be {value}", session).status == "ok"
    assert session.ref_stack == given["ref_stack"]
    return session


def snapshot(session):
    return dict(session.symbols), list(session.ref_stack), list(session.history)


def needs_context(fixture):
    """Whether the fixture depends on N1: bare words, pronouns or implicit declaration."""
    text = json.dumps(fixture["expected_slots"])
    return '"word"' in text or '"pronoun"' in text or "warning" in fixture["expected_diagnostic_levels"]


# Exit test


@pytest.mark.parametrize("fixture", load("valid"), ids=lambda f: f["id"])
def test_valid_fixture_gives_expected_minilang(fixture):
    session = session_from(fixture["given"])
    result = run(fixture["input"], session)
    assert result.status == "ok", result.diagnostics
    assert result.minilang == fixture["expected_minilang"]
    assert result.back_translation
    assert [d.level for d in result.diagnostics] == fixture["expected_diagnostic_levels"]
    assert session.history[-1] == result.trace.ast


@pytest.mark.parametrize(
    "fixture", [f for f in load("ambiguous") if f["ambiguity"] not in GATE_ONLY], ids=lambda f: f["id"],
)
def test_context_and_missing_slot_fixtures_ask_their_question(fixture):
    session = session_from(fixture["given"])
    before = snapshot(session)
    result = run(fixture["input"], session)
    assert result.status == "needs_clarification"
    assert result.question == fixture["expected_question"]
    assert result.options == tuple(fixture["options"])
    assert result.minilang is None and result.trace.decision == "CLARIFY"
    assert snapshot(session) == before


@pytest.mark.parametrize("fixture", load("semantic"), ids=lambda f: f["id"])
def test_semantic_fixture_through_pipeline(fixture):
    session = session_from(fixture["given"])
    result = run(fixture["input"], session)
    assert [d.code for d in result.diagnostics if d.stage == "semantic"] == fixture["expected_diagnostic_codes"]


def test_context_dependent_fixtures_are_the_expected_ones():
    dependent = [f["id"] for f in load("valid") if needs_context(f)]
    assert dependent == ["V04", "V06", "V12", "V14", "V15", "V16", "V17", "V18", "V19", "V20", "V21", "V22"]


@pytest.mark.parametrize("fixture", load("valid"), ids=lambda f: f["id"])
def test_no_context_fails_cleanly_on_context_dependent_fixtures(fixture):
    session = session_from(fixture["given"])
    before = snapshot(session)
    result = run(fixture["input"], session, use_context=False)
    if needs_context(fixture):
        assert result.status == "error"
        assert result.minilang is None and result.back_translation is None
        assert any(d.level == "error" for d in result.diagnostics)
        assert snapshot(session) == before
    else:
        assert result.status == "ok"
        assert result.minilang == fixture["expected_minilang"]


def test_no_context_unresolved_word_is_an_ir_error():
    result = run("print hello", Session(), use_context=False)
    [d] = result.diagnostics
    assert (d.level, d.stage, d.code) == ("error", "ir", "E401")
    assert "hello" in d.message and "context" in d.message


# Session behaviour (plan Section 7 demo)


def test_demo_session():
    session = Session()
    first = run("make a variable called score and set it to 10", session)
    assert (first.status, first.minilang) == ("ok", "LET score = 10;")
    assert first.back_translation == "create variable score with value 10."

    second = run("add 5 to it", session)
    assert (second.minilang, second.back_translation) == ("score = score + 5;", "increase score by 5.")

    assert run("print total", session).minilang == 'PRINT "total";'

    typo = run("print scroe", session)
    assert (typo.status, typo.question) == ("needs_clarification", "Did you mean the variable score?")

    missing = run("increase score", session)
    assert missing.question == "By how much should score increase?"

    rejected = run("store 50 in bonus", session)
    assert rejected.status == "unsupported" and rejected.trace.decision == "REJECT"
    assert rejected.notes == ("NO_MATCH",)
    assert [d.code for d in rejected.diagnostics] == ["E101"]

    assert session.history == [
        Let("score", Num("10")),
        Assign("score", BinOp("+", Var("score"), Num("5"))),
        session.history[2],
    ]


def test_semantic_error_returns_no_code_and_keeps_session():
    session = Session()
    result = run("print x times 2", session)
    assert result.status == "error"
    assert result.minilang is None and result.back_translation is None
    assert [d.code for d in result.diagnostics] == ["E201"]
    assert session.history == []


def test_missing_value_for_undeclared_target_asks_the_spec_question():
    result = run("set x to", Session())
    assert (result.status, result.question) == ("needs_clarification", "What value should x be set to?")


@pytest.mark.parametrize("text,question", [
    ("increase it", 'Which variable does "it" refer to?'),
    ("set it to", 'Which variable does "it" refer to?'),
])
def test_unresolvable_pronoun_is_asked_before_the_missing_slot(text, question):
    assert run(text, Session()).question == question


def test_typo_is_asked_before_the_missing_slot():
    session = Session()
    run("let score be 1", session)
    assert run("increase scroe", session).question == "Did you mean the variable score?"


def test_typo_in_assignment_target_never_creates_a_variable():
    session = Session()
    run("let score be 1", session)
    before = snapshot(session)
    result = run("set scroe to 7", session)
    assert result.status == "needs_clarification" and snapshot(session) == before


def test_implicit_declaration_does_not_apply_inside_a_block():
    session = Session()
    run("let score be 1", session)
    result = run("if score is at least 10 then set y to 3", session)
    assert [d.code for d in result.diagnostics] == ["E201"]


def test_operand_that_is_not_an_identifier_is_an_ir_error():
    result = run("print hello world plus 1", Session())
    assert result.status == "error"
    assert [(d.stage, d.code) for d in result.diagnostics] == [("ir", "E401")]


def test_no_context_still_asks_for_missing_slots():
    session = Session()
    run("let score be 1", session)
    assert run("increase score", session, use_context=False).question == "By how much should score increase?"


def test_implicit_declaration_warning_is_reported():
    result = run("set x to 5", Session())
    assert result.status == "ok" and result.minilang == "LET x = 5;"
    assert [(d.level, d.code) for d in result.diagnostics] == [("warning", "W301")]


# Trace data


def test_trace_has_candidates_scores_decision_and_ast():
    session = Session()
    run("let score be 1", session)
    result = run("add 5 to it", session)
    trace = result.trace
    assert trace.input == "add 5 to it"
    assert trace.normalized == "add 5 to it"
    assert trace.decision == "ACCEPT"
    assert trace.candidates and all(0.0 <= c.score <= 1.0 for c in trace.candidates)
    assert trace.candidates[0].slots["name"]["kind"] == "pronoun"          # raw, before context
    assert trace.chosen.slots["name"] == {"kind": "name", "text": "score"}   # after context
    assert trace.chosen.rule_id == "INC2"
    assert trace.ast == Assign("score", BinOp("+", Var("score"), Num("5")))


def test_trace_for_rejected_input():
    result = run("sort the list descending", Session())
    assert result.trace.candidates == () and result.trace.chosen is None and result.trace.ast is None
    assert result.trace.decision == "REJECT"


@pytest.mark.parametrize("bad,reason", [
    ("", "EMPTY_INPUT"), ("!!!", "EMPTY_INPUT"), ('print "oops', "UNTERMINATED_QUOTE"),
    ("x" * 600, "INPUT_TOO_LONG"), ("set x to 5 and set y to 6", "REJECT_AND_CONTINUATION"),
])
def test_unsupported_input_is_rejected_cleanly_with_its_reason(bad, reason):
    result = run(bad, Session())
    assert result.status == "unsupported" and result.minilang is None
    assert result.notes == (reason,)
    [d] = result.diagnostics
    assert (d.level, d.stage, d.code) == ("error", "candidates", "E101")


def test_accepted_result_has_no_notes():
    assert run('print "hi"', Session()).notes == ()
