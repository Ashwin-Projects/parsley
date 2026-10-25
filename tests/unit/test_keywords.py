"""keywords.py is the single source of MiniLang keywords (LANGUAGE_SPEC.md 2)."""

import re
from pathlib import Path

import pytest

from parsley import keywords
from parsley.nlp import patterns

SPEC = (Path(__file__).resolve().parents[2] / "LANGUAGE_SPEC.md").read_text(encoding="utf-8")


def test_keywords_match_the_spec():
    row = re.search(r"^\| Keywords \|(.*)$", SPEC, re.MULTILINE).group(1)
    assert set(re.findall(r"`([A-Z]+)`", row)) == keywords.KEYWORDS


def test_patterns_use_the_same_keyword_set():
    assert patterns.MINILANG_KEYWORDS is keywords.KEYWORDS


@pytest.mark.parametrize("word", ["LET", "let", "Let", "tImEs", "else"])
def test_keywords_are_reserved_in_any_case(word):
    assert keywords.is_reserved(word)


@pytest.mark.parametrize("word", ["letter", "age", "printer", "x", "ıf"])  # dotless-i "ıf" is not IF
def test_other_words_are_not_reserved(word):
    assert not keywords.is_reserved(word)
