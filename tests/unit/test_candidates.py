"""Candidate generator [B] (Phase 2): every match, scored, as an NLPResult (ARCHITECTURE.md 2.3-2.4)."""

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from parsley.nlp import candidates
from parsley.nlp.candidates import Candidate, NLPResult, generate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixtures(category):
    return json.loads((FIXTURES / f"{category}.json").read_text(encoding="utf-8"))["fixtures"]


def word(text):
    return {"kind": "word", "text": text}


def num(text):
    return {"kind": "number", "text": text}


# Phase 2 exit test


@pytest.mark.parametrize("fx", fixtures("valid"), ids=lambda f: f["id"])
def test_valid_fixture_top_candidate_has_expected_intent_and_slots(fx):
    result = generate(fx["input"])
    assert result.status == "ok"
    top = result.candidates[0]
    assert (top.intent, top.rule_id) == (fx["intent"], fx["rule"])
    assert top.slots == fx["expected_slots"]


@pytest.mark.parametrize("fx", fixtures("invalid"), ids=lambda f: f["id"])
def test_invalid_fixture_is_unsupported(fx):
    result = generate(fx["input"])
    assert result.status == "unsupported"
    assert result.candidates == []


# The other fixture sets: Phase 2 must already produce the right rule for Phase 4/6


@pytest.mark.parametrize("fx", fixtures("ambiguous") + fixtures("semantic"), ids=lambda f: f["id"])
def test_ambiguous_and_semantic_fixtures_match_their_rule(fx):
    result = generate(fx["input"])
    assert result.candidates, "Phase 6 needs a candidate to clarify or check"
    assert result.candidates[0].rule_id == fx["rule"]


# Frozen contract (parsley_ml and every later stage depend on it)


def test_candidate_fields_match_the_frozen_contract():
    assert [f.name for f in dataclasses.fields(Candidate)] == ["intent", "slots", "score", "rule_id", "notes"]


def test_nlp_result_fields_match_the_frozen_contract():
    assert [f.name for f in dataclasses.fields(NLPResult)] == ["status", "candidates", "question", "suggestion"]


@pytest.mark.parametrize("text", [f["input"] for f in fixtures("valid") + fixtures("ambiguous")])
def test_scores_are_in_range_and_sorted(text):
    result = generate(text)
    scores = [c.score for c in result.candidates]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert result.question is None and result.suggestion is None


def test_generator_takes_no_session_or_symbol_table():
    assert list(inspect.signature(generate).parameters) == ["text"]


# Slots stay raw and unresolved (requirement 4)


def test_bare_words_are_unresolved_regardless_of_meaning():
    assert generate("print age").candidates[0].slots == {"value": word("age")}


def test_pronoun_in_value_position_is_marked_unresolved():
    assert generate("print it").candidates[0].slots == {"value": {"kind": "pronoun", "text": "it"}}


def test_multi_word_pronoun_in_name_position():
    slots = generate("increase the variable by 2").candidates[0].slots
    assert slots["name"] == {"kind": "pronoun", "text": "the variable"}


def test_quoted_text_is_not_split_by_operator_words():
    slots = generate('print "a plus b"').candidates[0].slots
    assert slots == {"value": {"kind": "string", "text": "a plus b", "quoted": True}}


# Missing required slots are None, with a note


@pytest.mark.parametrize(
    "text, slot",
    [("increase score", "amount"), ("set y to", "value"), ("print", "value"), ("repeat print hello", "count")],
)
def test_missing_required_slot_is_none(text, slot):
    top = generate(text).candidates[0]
    assert top.slots[slot] is None
    assert any(slot in note for note in top.notes)


# Alternatives produce one candidate per reading, with equal scores


def test_alternatives_give_one_candidate_each():
    result = generate("set x to 10 or 20")
    assert [c.slots["value"] for c in result.candidates] == [num("10"), num("20")]
    assert result.candidates[0].score == result.candidates[1].score


# Values


def test_standard_precedence():
    value = generate("set x to 1 plus 2 times 3").candidates[0].slots["value"]
    assert value == {"kind": "binop", "op": "+", "left": num("1"),
                     "right": {"kind": "binop", "op": "*", "left": num("2"), "right": num("3")}}


def test_symbol_minus_directly_before_number_is_unary():
    value = generate("set x to -5").candidates[0].slots["value"]
    assert value == {"kind": "neg", "operand": num("5")}


def test_spaced_symbol_minus_between_operands_is_binary():
    value = generate("set x to y - 5").candidates[0].slots["value"]
    assert value == {"kind": "binop", "op": "-", "left": word("y"), "right": num("5")}


def test_multi_word_operator():
    value = generate("set x to y divided by 2").candidates[0].slots["value"]
    assert value == {"kind": "binop", "op": "/", "left": word("y"), "right": num("2")}


@pytest.mark.parametrize(
    "text",
    [
        "set x to minus 5",  # minus is binary only
        "set x to 5 plus",  # dangling operator
        "set print to 5",  # keyword (any case) is not a name
        "set Let to 5",
        "set 5 to 6",  # not an identifier
        "repeat 3 times print a and print b",  # block continuation (D-4)
        "if x is 1 then print a",  # bare "is" is not a comparison
        "if x is above 1 then make a variable called y and set it to 2",  # declaration in a block
        "repeat many times print x",  # count must be a number
    ],
)
def test_unsupported_shapes(text):
    assert generate(text).status == "unsupported"


# Review fixes: bounded cost, one statement per sentence, isolated slots


def test_overlong_input_is_unsupported():
    assert generate("print " + "a " * candidates.MAX_INPUT_CHARS).status == "unsupported"


def test_more_alternatives_than_the_cap_is_unsupported():
    many = " or ".join(str(n) for n in range(candidates.MAX_ALTERNATIVES + 1))
    assert generate(f"set x to {many}").status == "unsupported"


def test_alternatives_up_to_the_cap_are_kept():
    many = " or ".join(str(n) for n in range(candidates.MAX_ALTERNATIVES))
    assert len(generate(f"set x to {many}").candidates) == candidates.MAX_ALTERNATIVES


def test_reading_explosion_is_capped():
    alts = " or ".join("abcd"[: candidates.MAX_ALTERNATIVES])
    text = f"if {alts} equals {alts} then print {alts} else print {alts}"
    assert generate(text).status == "unsupported"


@pytest.mark.parametrize(
    "text",
    ["set x to 5 and set y to 6", "increase x by 1 and print x", "print big and print done"],
)
def test_and_followed_by_a_statement_is_rejected_anywhere(text):
    assert generate(text).status == "unsupported"


def test_and_inside_plain_text_is_kept():
    assert generate("print salt and pepper").candidates[0].slots == {"value": word("salt and pepper")}


def test_many_and_clauses_stay_polynomial(monkeypatch):
    calls = 0
    real_match = candidates._match

    def counting_match(*args):
        nonlocal calls
        calls += 1
        return real_match(*args)

    monkeypatch.setattr(candidates, "_match", counting_match)
    generate(("set x to a or a or a or a and " * 20)[: candidates.MAX_INPUT_CHARS])
    assert calls < 5000


def test_long_unary_chain_does_not_recurse():
    norm = candidates.normalize("negative " * 3000 + "5")
    value = candidates._expression(norm, norm.tokens)
    depth = 0
    while value["kind"] == "neg":
        value, depth = value["operand"], depth + 1
    assert (depth, value) == (3000, num("5"))


def test_candidates_do_not_share_slot_objects():
    first, second = generate("set x to 10 or 20").candidates
    first.slots["name"]["text"] = "changed"
    assert second.slots["name"]["text"] == "x"


# No exceptions escape


@pytest.mark.parametrize("bad", [None, 123, "", "   ", 'print "unterminated', "\x00\x01"])
def test_bad_input_is_unsupported_not_an_exception(bad):
    assert generate(bad).status == "unsupported"


def test_internal_errors_are_contained(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(candidates, "_match", boom)
    assert generate("print age") == NLPResult("unsupported", [], None, None)
