"""End-to-end pipeline: normalize -> candidates -> context -> top -> IR -> semantic -> codegen -> V1.

The fixture tests are the exit test for this step: every valid fixture, run as a session,
gives exactly its expected MiniLang; context fixtures resolve (or ask) correctly; with
context off, the context-dependent fixtures fail cleanly.
"""

import json
from pathlib import Path

import pytest

from parsley.compiler.ast_nodes import Assign, BinOp, Let, Num, Var
from parsley.pipeline import answer, run
from parsley.session import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

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


@pytest.mark.parametrize("fixture", load("ambiguous"), ids=lambda f: f["id"])
def test_every_ambiguous_fixture_asks_its_question(fixture):
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
    assert dependent == ["V04", "V06", "V12", "V14", "V15", "V16", "V17", "V18", "V19", "V20", "V21", "V22",
                         "V26", "V27", "V31", "V32", "V33"]


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


# Answering a clarification (REPL flow) and confirmation


def declared(*sentences):
    session = Session()
    for sentence in sentences:
        assert run(sentence, session).status == "ok"
    return session


@pytest.mark.parametrize("setup,text,reply,minilang", [
    (["let score be 1"], "increase score", "2", "score = score + 2;"),
    (["let score be 1"], "print scroe", "yes", "PRINT score;"),
    (["let score be 1"], "print scroe", "no", 'PRINT "scroe";'),
    (["let score be 1"], "set scroe to 7", "no", "LET scroe = 7;"),
    (["let score be 1"], "set scroe to 7", "yes", "score = 7;"),
    (["let x be 1"], "set x to 10 or 20", "20", "x = 20;"),
    (["let x be 1"], "multiply x by 2 plus 3", "1", "x = x * 2 + 3;"),
    (["let x be 1"], "multiply x by 2 plus 3", "2", "x = x * (2 + 3);"),
    (["let score be 1"], "add 5 to it", None, "score = score + 5;"),
    ([], "increase it", "x", None),
    ([], "repeat print hello", "3", 'REPEAT 3 TIMES { PRINT "hello"; }'),
    ([], "print", "hello", 'PRINT "hello";'),
])
def test_answer_is_merged_and_the_candidate_re_run(setup, text, reply, minilang):
    session = declared(*setup)
    result = run(text, session)
    if reply is not None:
        assert result.status == "needs_clarification"
        result = answer(result, reply, session)
    if minilang is None:
        assert result.status != "ok"
    else:
        assert (result.status, result.minilang) == ("ok", minilang)
        assert session.history[-1] == result.trace.ast


def test_answer_keeps_context_warnings():
    result = answer(run("set scroe to 7", declared("let score be 1")), "no", declared("let score be 1"))
    assert [d.code for d in result.diagnostics] == ["W301"]


def test_unclear_answer_asks_again_and_changes_nothing():
    session = declared("let x be 1")
    first = run("set x to 10 or 20", session)
    before = snapshot(session)
    again = answer(first, "30", session)
    assert (again.status, again.question, again.options) == ("needs_clarification", first.question, first.options)
    assert snapshot(session) == before


def test_answer_can_lead_to_the_next_question():
    session = declared("let x be 1", "let score be 1")
    first = run("set x to scroe or 20", session)
    assert first.question == "scroe or 20?"
    second = answer(first, "scroe", session)
    assert second.question == "Did you mean the variable score?"
    third = answer(second, "yes", session)
    assert (third.status, third.minilang) == ("ok", "x = score;")


def test_answer_to_a_settled_result_is_rejected():
    with pytest.raises(ValueError):
        answer(run('print "hi"', Session()), "yes", Session())


def test_needs_clarification_result_carries_the_clarification():
    result = run("increase score", declared("let score be 1"))
    assert result.clarification is not None and result.clarification.kind == "missing_slot"


def test_confirmed_interpretation_is_recorded():
    seen = []
    session = Session()
    result = run("let x be 1", session, confirm=lambda text: seen.append(text) or True)
    assert seen == ["create variable x with value 1."]
    assert result.status == "ok" and "x" in session.symbols


def test_rejected_interpretation_is_not_recorded():
    session = Session()
    result = run("let x be 1", session, confirm=lambda text: False)
    assert result.status == "error" and result.minilang is None
    assert [(d.stage, d.code) for d in result.diagnostics] == [("ambiguity", "E103")]
    assert snapshot(session) == ({}, [], [])


def test_confirm_is_not_asked_when_the_statement_has_errors():
    asked = []
    result = run("print x times 2", Session(), confirm=lambda text: asked.append(text) or True)
    assert asked == [] and [d.code for d in result.diagnostics] == ["E201"]


# Review fixes: accepted names persist, operator scope after the target question, long amounts


def test_refused_typo_stays_refused_across_later_questions():
    session = declared("let score be 1")
    first = run("increase scor", session)
    assert first.question == "Did you mean the variable score?"
    second = answer(first, "no", session)
    assert second.question == "By how much should scor increase?"
    third = answer(second, "5", session)
    assert third.question is None
    assert [d.code for d in third.diagnostics] == ["E201", "E201"]  # scor = scor + 5: two uses


def test_refused_typo_in_assignment_then_missing_value():
    session = declared("let score be 1")
    second = answer(run("set scor to", session), "no", session)
    assert second.question == "What value should scor be set to?"
    third = answer(second, "5", session)
    assert (third.status, third.minilang) == ("ok", "LET scor = 5;")


@pytest.mark.parametrize("text,first_reply", [
    ("multiply scor by 2 plus 3", "yes"),
    ("multiply it by 2 plus 3", None),
])
def test_target_question_comes_before_operator_scope(text, first_reply):
    session = declared("let score be 1")
    result = run(text, session)
    if first_reply is not None:
        assert result.question == "Did you mean the variable score?"
        result = answer(result, first_reply, session)
    assert result.question == "Do you mean (score times 2) plus 3, or score times (2 plus 3)?"
    done = answer(result, "1", session)
    assert (done.status, done.minilang) == ("ok", "score = score * 2 + 3;")


def test_typo_inside_the_amount_is_asked_before_operator_scope():
    session = declared("let x be 1", "let score be 1")
    result = answer(run("multiply x by scor plus 3", session), "yes", session)
    assert result.question == "Do you mean (x times score) plus 3, or x times (score plus 3)?"
    assert answer(result, "1", session).minilang == "x = x * score + 3;"


@pytest.mark.parametrize("text,left,right", [
    ("multiply x by 2 minus 3 minus 4", "x = x * 2 - 3 - 4;", "x = x * (2 - 3 - 4);"),
    ("multiply x by 2 plus 3 plus 4", "x = x * 2 + 3 + 4;", "x = x * (2 + 3 + 4);"),
    ("divide x by 2 times 3 plus 4", "x = x / 2 * 3 + 4;", "x = x / (2 * 3 + 4);"),
])
def test_longer_amounts_group_left_by_standard_precedence(text, left, right):
    session = declared("let x be 1")
    first = run(text, session)
    assert answer(first, "1", declared("let x be 1")).minilang == left
    assert answer(first, "2", declared("let x be 1")).minilang == right


def test_longer_amount_options_show_the_grouping():
    result = run("multiply x by 2 minus 3 minus 4", declared("let x be 1"))
    assert result.options == ("((x times 2) minus 3) minus 4", "x times (2 minus 3 minus 4)")


@pytest.mark.parametrize("reply", ["3", "0", "x", ""])
def test_operator_scope_bad_answer_asks_again(reply):
    session = declared("let x be 1")
    first = run("multiply x by 2 plus 3", session)
    assert answer(first, reply, session) is first


@pytest.mark.parametrize("text,codes", [
    ("sort the list descending", "NO_MATCH"),
    ("set x to 5 and set y to 6", "REJECT_AND_CONTINUATION"),
])
def test_unsupported_message_names_its_reason_codes(text, codes):
    [d] = run(text, Session()).diagnostics
    _, named, after = d.message.partition(f"({codes})")
    assert named and (after == "" or after.startswith(". "))  # N4 guidance may follow the codes


# Phase 7 verification integration (V1 back-translation, V2 round-trip, V3 execution
# equivalence). The real V2/V3 modules are teammates' work; these tests use fakes.

from parsley.compiler.ast_nodes import Print, Program, Str  # noqa: E402
from parsley.verify import Verification, ast_eval, interpreter, roundtrip  # noqa: E402


def test_unavailable_layers_are_skipped_and_never_fail(monkeypatch):
    monkeypatch.delattr(roundtrip, "check", raising=False)
    monkeypatch.delattr(interpreter, "run", raising=False)
    result = run("make a variable called age and set it to 20", Session())
    assert result.status == "ok"
    v = result.verification
    assert isinstance(v, Verification)
    assert (v.back_translation, v.v2_match, v.v3_match) == ("create variable age with value 20.", None, None)
    assert "V2 skipped: not available" in "\n".join(v.details)
    assert "V3 skipped: not available" in "\n".join(v.details)
    assert result.trace.verification == v


def test_v2_pass_calls_roundtrip_with_the_statement(monkeypatch):
    calls = []
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: calls.append((source, expected)), raising=False)
    v = run("let age be 20", Session()).verification
    assert v.v2_match is True
    assert calls == [("LET age = 20;", Program((Let("age", Num("20")),)))]


def test_v2_fail_reports_the_first_difference(monkeypatch):
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: "value: Num('20') != Num('21')", raising=False)
    result = run("let age be 20", Session())
    assert result.status == "ok" and result.verification.v2_match is False
    assert any("Num('20') != Num('21')" in d for d in result.verification.details)


@pytest.mark.parametrize("error,expected", [(NotImplementedError(), None), (ValueError("boom"), False)])
def test_v2_exception_is_skip_or_failure_never_a_crash(monkeypatch, error, expected):
    def check(source, expected_program):
        raise error
    monkeypatch.setattr(roundtrip, "check", check, raising=False)
    result = run("let age be 20", Session())
    assert result.status == "ok" and result.verification.v2_match is expected
    if expected is False:
        assert any("boom" in d for d in result.verification.details)


def _fake_evaluators(monkeypatch, ast_result, interp_result, seen):
    def evaluate(program):
        seen.append(("ast_eval", program))
        return ast_result

    def interpret(source):
        seen.append(("interpreter", source))
        return interp_result

    monkeypatch.setattr(ast_eval, "run", evaluate, raising=False)
    monkeypatch.setattr(interpreter, "run", interpret, raising=False)


def test_v3_runs_both_evaluators_on_the_whole_session_program(monkeypatch):
    seen = []
    _fake_evaluators(monkeypatch, ({"x": 1}, ["hi"], []), ({"x": 1}, ["hi"], []), seen)
    session = Session()
    run("let x be 1", session)
    seen.clear()
    v = run('print "hi"', session).verification
    assert v.v3_match is True
    program = Program((Let("x", Num("1")), Print(Str("hi"))))
    assert seen == [("ast_eval", program), ("interpreter", 'LET x = 1;\nPRINT "hi";')]


def test_v3_fail_when_the_evaluators_disagree(monkeypatch):
    _fake_evaluators(monkeypatch, ({"x": 1}, [], []), ({"x": 2}, [], []), [])
    v = run("let x be 1", Session()).verification
    assert v.v3_match is False
    assert any("V3 failed" in d and "{'x': 1}" in d and "{'x': 2}" in d for d in v.details)


def test_v3_skipped_when_only_one_evaluator_exists(monkeypatch):
    monkeypatch.delattr(interpreter, "run", raising=False)
    monkeypatch.setattr(ast_eval, "run", lambda program: ({}, [], []), raising=False)
    assert run("let x be 1", Session()).verification.v3_match is None


def test_v3_evaluator_crash_is_a_failure_not_a_crash(monkeypatch):
    def boom(program):
        raise ZeroDivisionError("division by zero")
    monkeypatch.setattr(ast_eval, "run", boom, raising=False)
    monkeypatch.setattr(interpreter, "run", lambda source: ({}, [], []), raising=False)
    result = run("let x be 1", Session())
    assert result.status == "ok" and result.verification.v3_match is False


@pytest.mark.parametrize("text", ["print x times 2", "sort the list descending", "increase score"])
def test_no_verification_without_accepted_code(text):
    result = run(text, Session())
    assert result.verification is None and result.trace.verification is None


def test_verification_never_changes_the_session(monkeypatch):
    _fake_evaluators(monkeypatch, ({}, [], []), ({}, [], []), [])
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: None, raising=False)
    session = Session()
    run("let x be 1", session)
    assert session.history == [Let("x", Num("1"))]


# Verification review fixes


def test_details_are_immutable():
    v = run("let x be 1", Session()).verification
    assert isinstance(v.details, tuple)
    hash(v)


def test_layer_calling_sys_exit_does_not_escape(monkeypatch):
    def check(source, expected):
        raise SystemExit(3)
    monkeypatch.setattr(roundtrip, "check", check, raising=False)
    result = run("let x be 1", Session())
    assert result.status == "ok" and result.verification.v2_match is False


def test_keyboard_interrupt_still_reaches_the_user(monkeypatch):
    def check(source, expected):
        raise KeyboardInterrupt
    monkeypatch.setattr(roundtrip, "check", check, raising=False)
    with pytest.raises(KeyboardInterrupt):
        run("let x be 1", Session())


class _Nasty(Exception):
    def __str__(self):
        raise RuntimeError("no str for you")


def test_exception_whose_text_raises_is_still_reported(monkeypatch):
    def check(source, expected):
        raise _Nasty()
    monkeypatch.setattr(roundtrip, "check", check, raising=False)
    v = run("let x be 1", Session()).verification
    assert v.v2_match is False and any("_Nasty" in d for d in v.details)


def test_huge_results_are_truncated_in_details(monkeypatch):
    _fake_evaluators(monkeypatch, ({"x": "a" * 10_000}, [], []), ({}, [], []), [])
    v = run("let x be 1", Session()).verification
    assert v.v3_match is False and all(len(d) < 600 for d in v.details)


@pytest.mark.parametrize("returned", [False, 0, ["diff"]])
def test_roundtrip_result_outside_the_contract_is_a_reported_failure(monkeypatch, returned):
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: returned, raising=False)
    v = run("let x be 1", Session()).verification
    assert v.v2_match is False and any("str or None" in d for d in v.details)


def test_v3_skips_before_generating_the_session_program(monkeypatch):
    monkeypatch.delattr(interpreter, "run", raising=False)
    from parsley import pipeline as pipeline_module
    calls = []
    real = pipeline_module.codegen.generate
    monkeypatch.setattr(pipeline_module.codegen, "generate", lambda node: calls.append(node) or real(node))
    run("let x be 1", Session())
    assert all(not isinstance(node, Program) for node in calls)


def test_declined_confirmation_never_runs_the_layers(monkeypatch):
    seen = []
    _fake_evaluators(monkeypatch, ({}, [], []), ({}, [], []), seen)
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: seen.append("V2"), raising=False)
    result = run("let x be 1", Session(), confirm=lambda text: False)
    assert result.verification is None and seen == []


def test_verification_after_an_answered_question(monkeypatch):
    monkeypatch.setattr(roundtrip, "check", lambda source, expected: None, raising=False)
    session = declared("let x be 1")
    done = answer(run("set x to 10 or 20", session), "20", session)
    assert done.verification is not None and done.verification.v2_match is True


# V3 compares (variables, output, errors)


@pytest.mark.parametrize("ast_result,interp_result,expected", [
    (({"x": 1}, ["1"], []), ({"x": 1}, ["1"], []), True),
    (({"x": 1}, ["1"], []), ({"x": 1}, ["2"], []), False),          # output differs
    (({"x": 1}, [], []), ({"x": 1}, [], ["division by zero"]), False),  # errors differ
    (({"x": 1}, [], ["E"]), ({"x": 1}, [], ["E"]), True),            # same run-time error
])
def test_v3_passes_only_if_variables_output_and_errors_match(monkeypatch, ast_result, interp_result, expected):
    _fake_evaluators(monkeypatch, ast_result, interp_result, [])
    assert run("let x be 1", Session()).verification.v3_match is expected


@pytest.mark.parametrize("bad", [({"x": 1}, []), "nonsense", None])
def test_v3_result_outside_the_contract_is_a_reported_failure(monkeypatch, bad):
    _fake_evaluators(monkeypatch, bad, bad, [])
    v = run("let x be 1", Session()).verification
    assert v.v3_match is False
    assert any("(variables, output, errors)" in d for d in v.details)


# N4 suggestion hook (parsley.nlp.suggest is a teammate's module; these tests use fakes)

from parsley.nlp import suggest as suggest_module  # noqa: E402


def test_suggestion_is_none_while_suggest_is_not_implemented(monkeypatch):
    from parsley.nlp import suggest
    monkeypatch.delattr(suggest, "suggest", raising=False)
    result = run("store 50 in bonus", Session())
    assert result.status == "unsupported" and result.suggestion is None


def test_suggestion_from_suggest_with_text_and_reason_code(monkeypatch):
    calls = []
    def fake(text, reason_code):
        calls.append((text, reason_code))
        return "set bonus to 50"
    monkeypatch.setattr(suggest_module, "suggest", fake, raising=False)
    result = run("store 50 in bonus", Session())
    assert result.suggestion == "set bonus to 50"
    assert calls == [("store 50 in bonus", "NO_MATCH")]


def test_suggest_gets_the_specific_reason_code(monkeypatch):
    calls = []
    monkeypatch.setattr(suggest_module, "suggest", lambda text, code: calls.append(code), raising=False)
    run("set x to 5 and set y to 6", Session())
    assert calls == ["REJECT_AND_CONTINUATION"]


@pytest.mark.parametrize("behaviour", [
    lambda text, code: None,
    lambda text, code: 42,
    lambda text, code: "   ",
])
def test_suggest_without_a_usable_answer_gives_none(monkeypatch, behaviour):
    monkeypatch.setattr(suggest_module, "suggest", behaviour, raising=False)
    assert run("store 50 in bonus", Session()).suggestion is None


@pytest.mark.parametrize("error", [NotImplementedError(), ValueError("boom"), SystemExit(2)])
def test_suggest_errors_never_break_the_pipeline(monkeypatch, error):
    def fake(text, code):
        raise error
    monkeypatch.setattr(suggest_module, "suggest", fake, raising=False)
    result = run("store 50 in bonus", Session())
    assert result.status == "unsupported" and result.suggestion is None


@pytest.mark.parametrize("text", ['print "hi"', "print x times 2", "increase score"])
def test_suggest_is_only_asked_for_unsupported_input(monkeypatch, text):
    calls = []
    monkeypatch.setattr(suggest_module, "suggest", lambda t, c: calls.append(t), raising=False)
    result = run(text, Session())
    assert calls == [] and result.suggestion is None


# N4 / V3 review fixes

from parsley import pipeline as pipeline_module  # noqa: E402
from parsley.nlp.candidates import NLPResult  # noqa: E402


def _unsupported_with(monkeypatch, notes):
    monkeypatch.setattr(pipeline_module, "generate", lambda text: NLPResult("unsupported", [], notes=list(notes)))


@pytest.mark.parametrize("notes,primary", [
    (["NO_MATCH"], "NO_MATCH"),
    (["NO_MATCH", "REJECT_AND_CONTINUATION"], "REJECT_AND_CONTINUATION"),
    (["TOO_MANY_ALTERNATIVES", "TOO_MANY_READINGS"], "TOO_MANY_ALTERNATIVES"),
])
def test_message_and_suggest_use_the_same_primary_reason(monkeypatch, notes, primary):
    _unsupported_with(monkeypatch, notes)
    calls = []
    monkeypatch.setattr(suggest_module, "suggest", lambda text, code: calls.append(code), raising=False)
    result = run("anything", Session())
    assert calls == [primary]
    assert pipeline_module._UNSUPPORTED_MESSAGES[primary] in result.diagnostics[0].message
    assert result.notes == tuple(notes)


def test_internal_error_gets_no_suggestion(monkeypatch):
    _unsupported_with(monkeypatch, ["INTERNAL_ERROR"])
    calls = []
    monkeypatch.setattr(suggest_module, "suggest", lambda text, code: calls.append(code) or "x", raising=False)
    assert run("anything", Session()).suggestion is None and calls == []


class _BadEq:
    def __eq__(self, other):
        raise RuntimeError("cannot compare")

    __hash__ = None


def test_v3_part_whose_equality_raises_is_a_reported_failure(monkeypatch):
    _fake_evaluators(monkeypatch, (_BadEq(), [], []), ({}, [], []), [])
    result = run("let x be 1", Session())
    assert result.status == "ok" and result.verification.v3_match is False


# V3 work budget, negative zero, and N4 phrasing vs E101 guidance (real modules unless faked)

from parsley import verify as verify_package  # noqa: E402

_BUDGET = verify_package.STEP_LIMIT_ERROR


def test_v3_is_skipped_not_failed_when_a_long_session_exceeds_the_budget():
    session = Session()
    assert run("let x be 0", session).verification.v3_match is True
    results = [run("repeat 1000 times add 1 to x", session) for _ in range(20)]
    assert [r.status for r in results] == ["ok"] * 20
    assert [r.verification.v3_match for r in results[:19]] == [True] * 19
    last = results[-1].verification
    assert last.v3_match is None
    assert last.details[-1] == "V3 skipped: execution budget exceeded"


@pytest.mark.parametrize("ast_result,interp_result", [
    (({"x": 1}, [], [_BUDGET]), ({"x": 9}, [], [])),   # only the AST evaluator ran out
    (({"x": 9}, [], []), ({"x": 1}, [], [_BUDGET])),   # only the interpreter ran out
    (({"x": 1}, [], [_BUDGET]), ({"x": 1}, [], [_BUDGET])),
])
def test_v3_is_skipped_when_either_evaluator_hits_its_budget(monkeypatch, ast_result, interp_result):
    _fake_evaluators(monkeypatch, ast_result, interp_result, [])
    v = run("let x be 1", Session()).verification
    assert v.v3_match is None
    assert v.details[-1] == "V3 skipped: execution budget exceeded"


def test_print_negative_zero_passes_v3():
    v = run("print negative 0.0", Session()).verification
    assert (v.v2_match, v.v3_match) == (True, True)


def test_and_rejection_puts_guidance_in_e101_and_a_phrasing_in_the_suggestion():
    result = run("repeat 3 times print 1 and print 2", Session())
    assert result.status == "unsupported"
    assert result.suggestion == "repeat 3 times print 1"
    message = result.diagnostics[0].message
    assert message.endswith(
        '(REJECT_AND_CONTINUATION). Blocks hold one statement. Try: "repeat 3 times print 1" '
        'and then "print 2" as separate sentences.'
    )


@pytest.mark.parametrize("behaviour", [
    lambda text: None, lambda text: 42, lambda text: "  ",
    lambda text: (_ for _ in ()).throw(ValueError("boom")),
])
def test_e101_without_usable_guidance_keeps_the_plain_message(monkeypatch, behaviour):
    monkeypatch.setattr(suggest_module, "split_guidance", behaviour, raising=False)
    message = run("repeat 3 times print 1 and print 2", Session()).diagnostics[0].message
    assert message.endswith("(REJECT_AND_CONTINUATION)")


def test_guidance_is_only_asked_for_and_rejections(monkeypatch):
    calls = []
    monkeypatch.setattr(suggest_module, "split_guidance", lambda text: calls.append(text), raising=False)
    run("store 50 in bonus", Session())
    assert calls == []
