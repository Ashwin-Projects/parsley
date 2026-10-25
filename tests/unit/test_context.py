"""[N1] Context resolver: LANGUAGE_SPEC.md sections 4 and 5, against a read-only session."""

import pytest

from parsley.compiler.symbols import SymbolTable
from parsley.nlp.candidates import Candidate, generate
from parsley.nlp.context import edit_distance, near_miss, resolve
from parsley.session import Session


def session_with(ref_stack=None, **types):
    table = SymbolTable()
    for i, (name, kind) in enumerate(types.items()):
        table.declare(name, kind, i)
    return Session(symbol_table=table, ref_stack=list(ref_stack if ref_stack is not None else types))


def top(text, session):
    return resolve(generate(text).candidates, session)[0]


def word(text):
    return {"kind": "word", "text": text}


def name(text):
    return {"kind": "name", "text": text}


def string(text, quoted=False):
    return {"kind": "string", "text": text, "quoted": quoted}


def number(text):
    return {"kind": "number", "text": text}


# Edit distance: optimal string alignment (LANGUAGE_SPEC.md 4 rule 3)


@pytest.mark.parametrize("a,b,d", [
    ("score", "score", 0), ("scroe", "score", 1), ("totl", "total", 1), ("contr", "counter", 2),
    ("store", "score", 1), ("", "abc", 3), ("ca", "abc", 3), ("abc", "", 3), ("Score", "score", 1),
])
def test_edit_distance(a, b, d):
    assert edit_distance(a, b) == d


# Near-miss rule: length-scaled thresholds and the common-word list


@pytest.mark.parametrize("word_,names,expected", [
    ("scroe", ["score"], "score"),          # 5 letters, distance 1
    ("scoer", ["score"], "score"),
    ("sxore", ["score"], "score"),
    ("scr", ["score"], None),               # distance 2 > 1 for a 5-letter name
    ("contr", ["counter"], "counter"),      # 7 letters, distance 2
    ("cntr", ["counter"], None),            # distance 3
    ("y", ["x"], None),                     # 1-2 letter names never ask
    ("ag", ["ab"], None),
    ("store", ["score"], None),             # common English word
    ("Store", ["score"], None),             # common-word check ignores case
    ("score", ["score"], None),             # exact match is not a near miss
    ("totl", ["total", "tote"], "total"),   # both distance 1: the first declared wins
])
def test_near_miss(word_, names, expected):
    assert near_miss(word_, names) == expected


def test_near_miss_prefers_smallest_distance_then_declaration_order():
    assert near_miss("countr", ["counted", "counter"]) == "counter"   # 1 vs 2
    assert near_miss("cab", ["car", "cat"]) == "car"                  # tie: first declared


# Variable vs. text (rules 1, 2, 4, 5)


def test_declared_word_becomes_a_name():
    r = top("print age", session_with(age="number"))
    assert r.candidate.slots == {"value": name("age")}
    assert r.question is None


def test_undeclared_word_becomes_text():
    r = top("display hello world", Session())
    assert r.candidate.slots == {"value": string("hello world")}


def test_quoted_text_stays_text_even_if_declared():
    r = top('print "age"', session_with(age="number"))
    assert r.candidate.slots == {"value": string("age", quoted=True)}


def test_operand_of_operator_word_becomes_a_name_even_if_undeclared():
    r = top("set age to x plus 1", session_with(age="number"))
    assert r.candidate.slots["value"] == {"kind": "binop", "op": "+", "left": name("x"), "right": number("1")}


def test_negated_word_is_an_operand():
    r = top("print negative x", Session())
    assert r.candidate.slots["value"] == {"kind": "neg", "operand": name("x")}


def test_condition_operands_and_block_bodies_are_resolved():
    r = top("if age is greater than 17 then print adult else print age", session_with(age="number"))
    slots = r.candidate.slots
    assert slots["condition"]["left"] == name("age")
    assert slots["then"]["slots"] == {"value": string("adult")}
    assert slots["else"]["slots"] == {"value": name("age")}


# Pronouns (section 5)


def test_pronoun_resolves_to_top_of_reference_stack():
    r = top("add 5 to it", session_with(ref_stack=["a", "score"], a="number", score="number"))
    assert r.candidate.slots["name"] == name("score")


def test_pronoun_in_a_value_position():
    r = top("print it", session_with(score="number"))
    assert r.candidate.slots == {"value": name("score")}


def test_pronoun_with_empty_reference_stack_asks():
    r = top("add 5 to it", Session())
    assert r.question == 'Which variable does "it" refer to?'
    assert r.options == ()


def test_the_variable_pronoun_keeps_its_wording_in_the_question():
    r = top("print the variable", Session())
    assert r.question == 'Which variable does "the variable" refer to?'


# Implicit declaration (section 5)


@pytest.mark.parametrize("text", ["set x to 5", "change x to 5", "update x to 5", "assign 5 to x"])
def test_assignment_to_undeclared_name_becomes_declaration_with_warning(text):
    r = top(text, Session())
    assert r.candidate.intent == "declare"
    [d] = r.diagnostics
    assert (d.level, d.stage, d.code) == ("warning", "context", "W301")
    assert "x" in d.message
    assert any("implicit" in note for note in r.candidate.notes)


def test_assignment_to_declared_name_stays_assignment():
    r = top("set x to 5", session_with(x="number"))
    assert r.candidate.intent == "assign"
    assert r.diagnostics == ()


def test_update_of_undeclared_name_is_not_implicitly_declared():
    r = top("increase x by 1", Session())
    assert r.candidate.intent == "increment"
    assert r.diagnostics == ()


# Typo confirmation (rule 3)


def test_near_miss_asks_and_never_corrects():
    r = top("print scroe", session_with(score="number"))
    assert r.question == "Did you mean the variable score?"
    assert r.options == ("yes", "no")
    assert r.candidate.slots == {"value": word("scroe")}


def test_typo_rule_comes_before_the_operand_rule():
    r = top("set score to scroe plus 1", session_with(score="number"))
    assert r.question == "Did you mean the variable score?"


@pytest.mark.parametrize("text", [
    "set scroe to 7", "change scroe to 7", "assign 7 to scroe",
    "increase scroe by 1", "subtract 1 from scroe",
])
def test_near_miss_target_of_assignment_or_update_asks(text):
    r = top(text, session_with(score="number"))
    assert r.question == "Did you mean the variable score?"
    assert r.candidate.intent != "declare" and r.diagnostics == ()


def test_explicit_declaration_of_a_near_miss_name_does_not_ask():
    r = top("let scroe be 7", session_with(score="number"))
    assert r.question is None and r.candidate.intent == "declare"


def test_missing_value_is_not_implicitly_declared():
    r = top("set x to", Session())
    assert r.candidate.intent == "assign" and r.diagnostics == ()


def test_typo_inside_a_block_body_asks():
    r = top("if scroe is at least 10 then print hi", session_with(score="number"))
    assert r.question == "Did you mean the variable score?"


def test_case_difference_is_a_near_miss():
    assert top("print Score", session_with(score="number")).question == "Did you mean the variable score?"


def test_common_word_is_never_a_typo():
    r = top("print store", session_with(score="number"))
    assert r.question is None
    assert r.candidate.slots == {"value": string("store")}


# Read-only contract


def test_resolve_never_changes_the_session_or_the_input():
    session = session_with(score="number")
    candidates = generate("set x to scroe").candidates
    before = [Candidate(c.intent, dict(c.slots), c.score, c.rule_id, list(c.notes)) for c in candidates]
    snapshot = (dict(session.symbols), list(session.ref_stack), list(session.history))
    resolve(candidates, session)
    resolve(generate("set y to 5").candidates, session)
    assert (dict(session.symbols), session.ref_stack, session.history) == snapshot
    assert candidates == before


def test_missing_slots_are_left_for_the_caller():
    r = top("increase score", session_with(score="number"))
    assert r.candidate.slots["amount"] is None
    assert r.question is None


# Type hints re-score candidates (plan Phase 6 step 2)


def _cand(intent, slots, score=0.8):
    return Candidate(intent, slots, score, "T", [])


def test_update_of_text_variable_loses_score():
    session = session_with(n="number", s="string")
    good, bad = resolve([_cand("increment", {"name": name("n"), "amount": number("1")}),
                         _cand("increment", {"name": name("s"), "amount": number("1")})], session)
    assert good.candidate.score > 0.8 > bad.candidate.score


def test_candidate_using_undeclared_variable_loses_score():
    session = session_with(a="number")
    [r] = resolve([_cand("print", {"value": {"kind": "binop", "op": "+",
                                               "left": word("ghost"), "right": number("1")}})], session)
    assert r.candidate.score < 0.8


def test_rescoring_reorders_and_stays_in_range():
    session = session_with(s="string", n="number")
    low = _cand("increment", {"name": name("n"), "amount": number("1")}, score=0.79)
    high = _cand("increment", {"name": name("s"), "amount": number("1")}, score=0.8)
    ranked = resolve([high, low], session)
    assert [r.candidate.slots["name"]["text"] for r in ranked] == ["n", "s"]
    assert all(0.0 <= r.candidate.score <= 1.0 for r in ranked)
    [capped] = resolve([_cand("increment", {"name": name("n"), "amount": number("1")}, score=1.0)], session)
    assert capped.candidate.score == 1.0


def test_plain_candidates_keep_their_score():
    [r] = resolve([_cand("print", {"value": number("1")})], Session())
    assert r.candidate.score == 0.8
