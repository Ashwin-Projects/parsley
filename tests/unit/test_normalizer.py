"""Normalizer [A]: original kept, lowercase copy for matching only, case preserved (LANGUAGE_SPEC.md 3)."""

import pytest

from parsley.nlp.normalizer import normalize


def test_original_text_is_kept_exactly():
    raw = "  Set   totalAmount to 5.  "
    assert normalize(raw).original == raw


def test_spaces_collapse_and_trailing_punctuation_is_stripped():
    assert normalize("  print   hello   world!?. ").text == "print hello world"


def test_match_text_lowercases_command_words_only_for_matching():
    norm = normalize("SET totalAmount TO 5")
    assert norm.match_text == "set totalamount to 5"
    assert norm.text == "SET totalAmount TO 5"


def test_match_text_has_same_length_as_text():
    norm = normalize('Show "Hello World" Now')
    assert len(norm.match_text) == len(norm.text)


def test_quoted_content_is_masked_in_match_text():
    norm = normalize('print "Set X"')
    assert "set" not in norm.match_text[6:]
    assert norm.match_text.startswith('print "')
    assert norm.match_text.endswith('"')


def test_whitespace_inside_quotes_is_preserved():
    norm = normalize('show  "a   b"')
    assert norm.text == 'show "a   b"'
    assert norm.tokens[1].text == "a   b"


def test_identifier_tokens_keep_original_case():
    tokens = normalize("make a variable called totalAmount").tokens
    assert tokens[-1].text == "totalAmount"
    assert tokens[-1].lower == "totalamount"
    assert tokens[-1].kind == "word"


@pytest.mark.parametrize(
    "raw, kinds",
    [
        ("print 2.5", ["word", "number"]),
        ('show "Hello"', ["word", "string"]),
        ("set x to x+1", ["word", "word", "word", "word", "symbol", "number"]),
        ("set x to -5", ["word", "word", "word", "symbol", "number"]),
        ("print 2nd", ["word", "word"]),
        ("print ٣", ["word", "word"]),  # non-ASCII digits are not MiniLang numbers
    ],
)
def test_token_kinds(raw, kinds):
    assert [t.kind for t in normalize(raw).tokens] == kinds


def test_quoted_token_text_excludes_quotes_but_span_includes_them():
    norm = normalize('show "Hi"')
    token = norm.tokens[1]
    assert token.text == "Hi"
    assert norm.text[token.start:token.end] == '"Hi"'


def test_token_spans_index_into_text():
    norm = normalize("set Age to 20")
    assert [norm.text[t.start:t.end] for t in norm.tokens] == ["set", "Age", "to", "20"]


def test_unterminated_quote_is_malformed():
    assert normalize('print "hello').malformed


def test_empty_after_normalization_has_no_tokens():
    norm = normalize("!!!")
    assert norm.text == ""
    assert norm.tokens == ()
    assert not norm.malformed
