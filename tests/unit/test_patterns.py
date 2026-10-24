"""Pattern table is data that mirrors LANGUAGE_SPEC.md 4.1 and 6 and ARCHITECTURE.md 2.3."""

import re
from pathlib import Path

import pytest

from parsley.nlp import patterns
from parsley.nlp.normalizer import normalize

SPEC = (Path(__file__).resolve().parents[2] / "LANGUAGE_SPEC.md").read_text(encoding="utf-8")

CONTRACT_SLOT_KEYS = {
    "declare": {"name", "value"},
    "assign": {"name", "value"},
    "increment": {"name", "amount"},
    "decrement": {"name", "amount"},
    "multiply": {"name", "amount"},
    "divide": {"name", "amount"},
    "print": {"value"},
    "repeat": {"count", "body"},
}


def test_rule_ids_are_unique_and_match_the_spec():
    ids = [p.rule_id for p in patterns.PATTERNS]
    spec_ids = set(re.findall(r"^\| \w+ \| ([A-Z]+\d) \|", SPEC, re.MULTILINE))
    assert len(ids) == len(set(ids))
    assert set(ids) == spec_ids


@pytest.mark.parametrize("pattern", patterns.PATTERNS, ids=lambda p: p.rule_id)
def test_slot_keys_follow_the_candidate_contract(pattern):
    keys = set(pattern.slot_names)
    if pattern.intent == "if":
        assert keys == ({"condition", "then", "else"} if pattern.rule_id == "IF2" else {"condition", "then"})
    else:
        assert keys == CONTRACT_SLOT_KEYS[pattern.intent]


@pytest.mark.parametrize("pattern", patterns.PATTERNS, ids=lambda p: p.rule_id)
def test_each_rule_matches_its_own_spec_example(pattern):
    assert pattern.regex.fullmatch(normalize(pattern.example).match_text)


def test_common_word_starting_set_matches_the_spec():
    block = re.search(r"plus this starting set:\n\n```\n(.*?)```", SPEC, re.DOTALL).group(1)
    assert patterns.COMMON_WORDS_START == frozenset(block.split())


def test_common_words_include_every_vocabulary_word():
    vocabulary = set()
    for group in patterns.SYNONYMS.values():
        vocabulary.update(word for phrase in group for word in phrase.split())
    for phrase, _ in patterns.COMPARISONS + patterns.BINARY_OPERATORS:
        vocabulary.update(word for word in phrase.split() if word.isalpha())
    for phrase in patterns.PRONOUNS:
        vocabulary.update(phrase.split())
    vocabulary.add(patterns.UNARY_MINUS_WORD)
    assert vocabulary <= patterns.COMMON_WORDS
    assert patterns.COMMON_WORDS_START <= patterns.COMMON_WORDS


def test_comparisons_are_ordered_longest_first():
    lengths = [len(phrase.split()) for phrase, _ in patterns.COMPARISONS]
    assert lengths == sorted(lengths, reverse=True)


def test_block_bodies_are_simple_statements_only():
    assert patterns.BLOCK_BODY_INTENTS == {"print", "assign", "increment", "decrement", "multiply", "divide"}
