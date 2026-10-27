"""N4 ranks guidance, preserves slots, and never accepts rejected input."""

import json
from pathlib import Path

import pytest

from parsley.nlp.suggest import suggest
from parsley.pipeline import run
from parsley.session import Session


@pytest.mark.parametrize(('text', 'expected'), [
    ('store 50 in bonus', 'set bonus to 50'),
    ('store -2.50 in totalAmount', 'set totalAmount to -2.50'),
    ('store "Hello World" in greeting', 'set greeting to "Hello World"'),
    ('Store 0 In totalAmount.', 'set totalAmount to 0'),
    ('prnit totalAmount', 'print totalAmount'),
    ('increse score by 2', 'increase score by 2'),
])
def test_useful_rewrites_preserve_slot_values(text, expected):
    assert suggest(text, 'NO_MATCH') == expected


def test_fixed_split_guidance_from_spec():
    fixtures = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/invalid.json').read_text())
    fixture = next(f for f in fixtures['fixtures'] if f['id'] == 'X11')
    assert suggest(fixture['input'], 'REJECT_AND_CONTINUATION') == fixture['expected_suggestion']


def test_split_does_not_treat_quoted_and_as_a_boundary():
    assert suggest('print "a and set x to 1" and print "done"', 'REJECT_AND_CONTINUATION') == (
        'Blocks hold one statement. Try: "print \\"a and set x to 1\\"" and then '
        '"print \\"done\\"" as separate sentences.'
    )


@pytest.mark.parametrize('reason', [
    'EMPTY_INPUT', 'UNTERMINATED_QUOTE', 'INPUT_TOO_LONG', 'INTERNAL_ERROR',
    'NOT_TEXT', 'TOO_MANY_ALTERNATIVES', 'TOO_MANY_READINGS',
])
def test_malformed_or_internal_failures_get_no_rewrite(reason):
    assert suggest('store 50 in bonus', reason) is None


@pytest.mark.parametrize('text', [
    'sort the list descending', 'create a list of numbers', 'define a function called greet',
    'ask the user for their age', 'while x is less than 10 print x',
    'calculate the square root of 16', 'open the file data.txt', 'go to line 10',
    '', 'z' * 501, 'store 1 in LET', 'store 10 or 20 in x',
])
def test_no_confident_supported_rewrite(text):
    assert suggest(text, 'NO_MATCH') is None


def test_pipeline_shows_rewrite_without_executing_it():
    session = Session()
    result = run('store 50 in bonus', session)
    assert result.status == 'unsupported' and result.minilang is None
    assert result.suggestion == 'set bonus to 50'
    assert session.history == [] and dict(session.symbols) == {}


def test_placeholder_like_identifier_is_preserved():
    assert suggest('store 50 in VALUE', 'NO_MATCH') == 'set VALUE to 50'
