"""v1.1 vocabulary (LANGUAGE_SPEC.md 6, changelog v1.1): each new phrasing gives the same
MiniLang as the existing canonical phrasing, through the real pipeline."""

import pytest

from parsley.pipeline import run
from parsley.session import Session

X = ("let x be 1",)

# (new phrasing, canonical phrasing, setup sentences)
SAME_AS_CANONICAL = [
    # declare: "define"/"initialize" as verbs; "as", "=", "equal to", "set to" as value connectors
    ("define x as 5", "let x be 5", ()),
    ("initialize x to 5", "let x be 5", ()),
    ("declare x = 5", "let x be 5", ()),
    ("define x equal to 5", "let x be 5", ()),
    ("initialize x set to 5", "let x be 5", ()),
    ("create a variable x as 5", "let x be 5", ()),
    ("make a new variable x = 5", "let x be 5", ()),
    ("create a variable x equal to 5", "let x be 5", ()),
    ("create a variable x set to 5", "let x be 5", ()),
    ("create a variable called x as 5", "let x be 5", ()),
    ("create a variable named x = 5", "let x be 5", ()),
    ("make a variable called x set to 5", "let x be 5", ()),
    ("define a variable called x and set it to 5", "let x be 5", ()),
    ("initialize a variable named x with value 5", "let x be 5", ()),
    # assign
    ("set x as 5", "set x to 5", X),
    ("set x equal to 5", "set x to 5", X),
    ("make x equal to 5", "set x to 5", X),
    ("change x as 5", "change x to 5", X),
    ("update x as 5", "update x to 5", X),
    ("x becomes 5", "set x to 5", X),
    ("x becomes x plus 1", "set x to x plus 1", X),
    # increment
    ("increment x by 2", "increase x by 2", X),
    ("raise x by 2", "increase x by 2", X),
    ("grow x by 2", "increase x by 2", X),
    ("increase the x by 2", "increase x by 2", X),
    # decrement
    ("decrement x by 2", "decrease x by 2", X),
    ("lower x by 2", "decrease x by 2", X),
    ("drop x by 2", "decrease x by 2", X),
    ("take 2 from x", "subtract 2 from x", X),
    ("remove 2 from x", "subtract 2 from x", X),
    # print
    ("output x", "print x", X),
    ("print out x", "print x", X),
    ("show me x", "print x", X),
    # conditions
    ("if x is bigger than 0 then print big", "if x is greater than 0 then print big", X),
    ("if x is larger than 0 then print big", "if x is greater than 0 then print big", X),
    ("if x is smaller than 9 then print small", "if x is less than 9 then print small", X),
    ("if x is under 9 then print small", "if x is less than 9 then print small", X),
    ("if x is no less than 1 then print ok", "if x is at least 1 then print ok", X),
    ("if x is no more than 1 then print ok", "if x is at most 1 then print ok", X),
    ("if x equals 1 then print one", "if x is equal to 1 then print one", X),
    ("if x is not equal to 2 then print ok", "if x does not equal 2 then print ok", X),
    ("if x isn't 2 then print ok", "if x does not equal 2 then print ok", X),
    ("if x isn't equal to 2 then print ok", "if x does not equal 2 then print ok", X),
    ("if x is greater than 0 then print big otherwise print small",
     "if x is greater than 0 then print big else print small", X),
    ("when x is greater than 0 then print big", "if x is greater than 0 then print big", X),
    ("when x is greater than 0 then print big otherwise print small",
     "if x is greater than 0 then print big else print small", X),
    # repeat
    ("loop 3 times print hello", "repeat 3 times print hello", ()),
    ("print hello 3 times", "repeat print hello 3 times", ()),
    ("add 2 to x 3 times", "repeat add 2 to x 3 times", X),
    # leading "please" and "the" before a variable name
    ("please print x", "print x", X),
    ("please set x to 5", "set x to 5", X),
    ("please let y be 2", "let y be 2", ()),
    ("print the x", "print x", X),
    ("add 2 to the x", "add 2 to x", X),
    ("set the x to 5", "set x to 5", X),
    ("set y to the x", "set y to x", X),
]


def compile_in_fresh_session(text, setup):
    session = Session()
    for sentence in setup:
        assert run(sentence, session).status == "ok", sentence
    return run(text, session)


@pytest.mark.parametrize(("phrasing", "canonical", "setup"), SAME_AS_CANONICAL, ids=[c[0] for c in SAME_AS_CANONICAL])
def test_new_phrasing_gives_the_canonical_minilang(phrasing, canonical, setup):
    expected = compile_in_fresh_session(canonical, setup)
    assert expected.status == "ok" and expected.minilang, canonical
    got = compile_in_fresh_session(phrasing, setup)
    assert (got.status, got.minilang) == ("ok", expected.minilang)


def test_store_in_stays_rejected_with_its_suggestion():
    result = compile_in_fresh_session("store 50 in bonus", ())
    assert result.status == "unsupported"
    assert result.suggestion == "set bonus to 50"


@pytest.mark.parametrize("text", [
    "double x", "triple x", "quadruple x", "bump x by 2",
    "if x exceeds 3 then print big", "if x exceed 3 then print big",
    "provided x is greater than 3 then print big",
])
def test_excluded_phrasings_stay_unsupported(text):
    assert compile_in_fresh_session(text, X).status == "unsupported"


def test_the_before_an_undeclared_word_stays_text():
    assert compile_in_fresh_session("print the end", ()).minilang == 'PRINT "the end";'


def test_the_variable_is_still_a_pronoun():
    assert compile_in_fresh_session("increase the variable by 2", X).minilang == "x = x + 2;"


def test_please_alone_is_not_a_statement():
    assert compile_in_fresh_session("please", ()).status == "unsupported"
