"""Phase 3 lexical contract, independent of the English pattern table."""

import pytest

from parsley import keywords
from parsley.compiler import lexer
from parsley.compiler.lexer import LexError, tokenize


def test_keyword_set_has_one_owner():
    assert lexer.KEYWORDS is keywords.KEYWORDS


def test_tokens_preserve_case_number_spelling_and_positions():
    tokens = tokenize('LET totalAmount = 02.50;\nPRINT totalAmount;')
    assert [(t.kind, t.text) for t in tokens] == [
        ('LET', 'LET'), ('IDENT', 'totalAmount'), ('=', '='), ('NUMBER', '02.50'),
        (';', ';'), ('PRINT', 'PRINT'), ('IDENT', 'totalAmount'), (';', ';'), ('EOF', ''),
    ]
    assert (tokens[5].line, tokens[5].column, tokens[5].start) == (2, 1, 25)
    assert all(t.end >= t.start for t in tokens)


@pytest.mark.parametrize('op', ['>', '<', '==', '>=', '<=', '!=', '+', '-', '*', '/'])
def test_operator_tokens(op):
    assert tokenize(op)[0].kind == op


def test_strings_decode_only_the_two_allowed_escapes():
    assert tokenize(r'"Hello \"World\""')[0].text == 'Hello "World"'
    assert tokenize(r'"C:\\demo"')[0].text == 'C:\\demo'


@pytest.mark.parametrize('source', [
    'let x = 1;', 'LET Print = 1;', '_name', 'café', '.5', '2.', '1.2.3',
    '!', '@', r'"bad\n"', r'"bad\t"', '"not closed',
])
def test_bad_tokens_have_coordinates(source):
    with pytest.raises(LexError) as caught:
        tokenize(source)
    assert caught.value.line >= 1 and caught.value.column >= 1


def test_error_coordinates_after_newline():
    with pytest.raises(LexError) as caught:
        tokenize('LET x = 1;\n  @')
    assert (caught.value.line, caught.value.column) == (2, 3)


def test_multiline_string_tracks_following_token():
    assert [(t.kind, t.line, t.column) for t in tokenize('"a\nb"\nPRINT')][-2:] == [
        ('PRINT', 3, 1), ('EOF', 3, 6),
    ]
