"""[N2] Ambiguity gate (LANGUAGE_SPEC.md 7): accept or clarify, and merging the user's answer."""

import pytest

from parsley.compiler.symbols import SymbolTable
from parsley.nlp.ambiguity import CLARIFY_MARGIN, apply_answer, gate, missing_slot_question
from parsley.nlp.candidates import Candidate, generate
from parsley.nlp.context import Resolution, resolve
from parsley.session import Session


def session_with(**types):
    table = SymbolTable()
    for i, (name, kind) in enumerate(types.items()):
        table.declare(name, kind, i)
    return Session(symbol_table=table, ref_stack=list(types))


def decide(text, session=None):
    session = session or Session()
    return gate(resolve(generate(text).candidates, session))


def clarification(text, session=None):
    decision = decide(text, session)
    assert decision.decision == "CLARIFY", decision
    return decision.clarification


def number(text):
    return {"kind": "number", "text": text}


def name(text):
    return {"kind": "name", "text": text}


# Missing-slot question templates (LANGUAGE_SPEC.md 7.1)


def question(text):
    return missing_slot_question(generate(text).candidates[0])


@pytest.mark.parametrize("text,expected", [
    ("increase score", "By how much should score increase?"),
    ("decrease lives", "By how much should lives decrease?"),
    ("multiply total", "By how much should total be multiplied?"),
    ("divide total", "By how much should total be divided?"),
    ("set y to", "What value should y be set to?"),
    ("change y to", "What value should y be set to?"),
    ("update y to", "What value should y be set to?"),
    ("print", "What should be printed?"),
    ("repeat print hello", "How many times should it repeat?"),
])
def test_missing_slot_question_templates(text, expected):
    assert question(text) == expected


def test_missing_slot_inside_a_block_body():
    assert question("repeat 3 times print") == "What should be printed?"


def test_complete_candidate_has_no_question():
    assert question("increase score by 2") is None
    assert question("repeat 3 times print hello") is None


# Accept


@pytest.mark.parametrize("text", ["set age to 21", "print hello", "multiply x by 2 times 3"])
def test_single_clear_reading_is_accepted(text):
    decision = decide(text, session_with(age="number", x="number"))
    assert decision.decision == "ACCEPT" and decision.clarification is None
    assert decision.candidate is not None


# Alternatives: two or more readings within the score margin


def test_margin_constant():
    assert CLARIFY_MARGIN == 0.05


def test_two_alternatives():
    c = clarification("set x to 10 or 20", session_with(x="number"))
    assert (c.kind, c.question, c.options) == ("alternatives", "10 or 20?", ("10", "20"))
    assert [r.slots["value"] for r in c.readings] == [number("10"), number("20")]


def test_three_alternatives_use_commas():
    c = clarification("print 1 or 2 or 3")
    assert (c.question, c.options) == ("1, 2 or 3?", ("1", "2", "3"))


def test_quoted_alternatives_keep_quotes():
    c = clarification('print "yes" or "no"')
    assert (c.question, c.options) == ('"yes" or "no"?', ('"yes"', '"no"'))


def test_readings_are_the_unresolved_sources():
    c = clarification("print hello or bye")
    assert [r.slots["value"]["kind"] for r in c.readings] == ["word", "word"]


def _resolution(slots, score):
    candidate = Candidate("print", slots, score, "P1", [])
    return Resolution(candidate, source=candidate)


def test_margin_is_exclusive():
    close = gate([_resolution({"value": number("1")}, 0.8), _resolution({"value": number("2")}, 0.76)])
    apart = gate([_resolution({"value": number("1")}, 0.8), _resolution({"value": number("2")}, 0.75)])
    assert close.decision == "CLARIFY" and apart.decision == "ACCEPT"
    assert apart.candidate.slots["value"] == number("1")


def test_identical_readings_within_margin_are_not_ambiguous():
    same = gate([_resolution({"value": number("1")}, 0.8), _resolution({"value": number("1")}, 0.8)])
    assert same.decision == "ACCEPT"


def test_readings_with_different_intents_are_described_whole():
    a = Candidate("print", {"value": number("1")}, 0.8, "P1", [])
    b = Candidate("increment", {"name": name("x"), "amount": number("1")}, 0.8, "INC2", [])
    c = gate([Resolution(a, source=a), Resolution(b, source=b)]).clarification
    assert c.kind == "alternatives"
    assert c.options == ("print 1", "increase x by 1")
    assert c.question == "print 1 or increase x by 1?"


# Operator scope (MUL1/DIV1 with plus or minus in the amount)


def test_operator_scope_question_and_readings():
    c = clarification("multiply x by 2 plus 3", session_with(x="number"))
    assert c.kind == "operator_scope"
    assert c.question == "Do you mean (x times 2) plus 3, or x times (2 plus 3)?"
    assert c.options == ("(x times 2) plus 3", "x times (2 plus 3)")
    left, right = c.readings
    assert left.intent == "assign"
    assert left.slots["value"] == {"kind": "binop", "op": "+", "right": number("3"),
                                   "left": {"kind": "binop", "op": "*", "left": name("x"), "right": number("2")}}
    assert right.intent == "assign"  # explicit, so choosing it cannot ask again
    assert right.slots["value"] == {"kind": "binop", "op": "*", "left": name("x"),
                                    "right": {"kind": "binop", "op": "+", "left": number("2"), "right": number("3")}}


def test_operator_scope_with_divide_and_minus():
    c = clarification("divide total by 4 minus 1", session_with(total="number"))
    assert c.question == "Do you mean (total divided by 4) minus 1, or total divided by (4 minus 1)?"


def test_operator_scope_inside_a_block():
    c = clarification("repeat 2 times multiply x by 2 plus 3", session_with(x="number"))
    assert c.kind == "operator_scope"
    left, _ = c.readings
    assert left.intent == "repeat" and left.slots["body"]["intent"] == "assign"


# Order: readings first, then which variable, then what is missing


def test_alternatives_come_before_a_typo_inside_them():
    c = clarification("set x to scroe or 20", session_with(x="number", score="number"))
    assert c.kind == "alternatives"


def test_typo_and_pronoun_and_missing_slot_kinds():
    s = session_with(score="number")
    assert clarification("print scroe", s).kind == "typo"
    assert clarification("increase it").kind == "pronoun"
    assert clarification("increase score", s).kind == "missing_slot"


# Merging answers into the source candidate


def merged(text, answer, session=None):
    result = apply_answer(clarification(text, session), answer)
    return None if result is None else result.candidate


@pytest.mark.parametrize("answer", ["20", " 20 ", "2"])
def test_alternative_by_text_or_number(answer):
    assert merged("set x to 10 or 20", answer, session_with(x="number")).slots["value"] == number("20")


def test_quoted_alternative_answer_without_quotes():
    assert merged('print "yes" or "no"', "no").slots["value"]["text"] == "no"


@pytest.mark.parametrize("answer", ["30", "0", "4", "", "ten or twenty"])
def test_unknown_alternative_answer_is_not_understood(answer):
    assert merged("set x to 10 or 20", answer, session_with(x="number")) is None


def test_operator_scope_answer():
    s = session_with(x="number")
    assert merged("multiply x by 2 plus 3", "1", s).intent == "assign"
    assert merged("multiply x by 2 plus 3", "x times (2 plus 3)", s).slots["value"]["op"] == "*"


def test_missing_amount_answer_is_parsed_as_a_value():
    c = merged("increase score", "2", session_with(score="number"))
    assert c.slots["amount"] == number("2")


def test_missing_value_answer_may_be_words():
    c = merged("print", "hello world")
    assert c.slots["value"] == {"kind": "word", "text": "hello world"}


def test_missing_count_answer():
    assert merged("repeat print hello", "3").slots["count"] == {"kind": "count", "text": "3"}


def test_missing_slot_inside_block_is_filled_at_its_path():
    c = merged("repeat 3 times print", "hi")
    assert c.slots["body"]["slots"]["value"] == {"kind": "word", "text": "hi"}


@pytest.mark.parametrize("text,answer", [
    ("increase score", "1 or 2"), ("increase score", '"oops'), ("repeat print hello", "x"),
    ("repeat print hello", "2.5 times"),
])
def test_unparsable_missing_slot_answer_is_not_understood(text, answer):
    assert merged(text, answer, session_with(score="number")) is None


@pytest.mark.parametrize("answer", ["yes", "Y", "yes."])
def test_typo_yes_uses_the_declared_name(answer):
    assert merged("print scroe", answer, session_with(score="number")).slots["value"] == name("score")


def test_typo_no_in_a_value_makes_text():
    c = merged("print scroe", "no", session_with(score="number"))
    assert c.slots["value"] == {"kind": "string", "text": "scroe", "quoted": False}


def test_typo_no_in_a_target_accepts_the_new_name():
    result = apply_answer(clarification("set scroe to 7", session_with(score="number")), "n")
    assert result.candidate.slots["name"] == name("scroe")
    assert result.accepted == frozenset({"scroe"})


def test_typo_other_answer_is_not_understood():
    assert merged("print scroe", "maybe", session_with(score="number")) is None


def test_pronoun_answer_names_the_variable():
    assert merged("increase it", "score").slots["name"] == name("score")


@pytest.mark.parametrize("answer", ["2", "two words", "PRINT"])
def test_pronoun_answer_must_be_an_identifier(answer):
    assert merged("increase it", answer) is None


@pytest.mark.parametrize("text", ["x" * 501, "\x00"])
def test_overlong_or_control_answers_are_not_understood(text):
    assert merged("print", text) is None
    assert merged("repeat print hello", text) is None
