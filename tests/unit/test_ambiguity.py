"""Missing-slot questions (LANGUAGE_SPEC.md 7.1). The rest of the ambiguity gate is a later step."""

import pytest

from parsley.nlp.ambiguity import missing_slot_question
from parsley.nlp.candidates import generate


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
