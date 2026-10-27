"""Phase 3 syntax, exact ASTs, and controlled errors."""

import json
import random
from pathlib import Path

import pytest

from parsley.compiler.ast_nodes import (
    BinOp, Compare, If, Let, Neg, Num, Print, Program, Repeat, Str, Var,
)
from parsley.compiler.lexer import LexError
from parsley.compiler.parser import MAX_DEPTH, ParseError, parse
from parsley.pipeline import run
from parsley.session import Session


def test_precedence_and_left_associativity():
    assert parse('PRINT 10 - 6 / 2 * 3 + 1;') == Program((Print(BinOp(
        '+', BinOp('-', Num('10'), BinOp('*', BinOp('/', Num('6'), Num('2')), Num('3'))), Num('1'),
    )),))


def test_unary_minus_and_parentheses():
    assert parse('LET x = -(2 + 3) * --4;') == Program((Let('x', BinOp(
        '*', Neg(BinOp('+', Num('2'), Num('3'))), Neg(Neg(Num('4'))),
    )),))


@pytest.mark.parametrize('op', ['>', '<', '==', '>=', '<=', '!='])
def test_every_comparison(op):
    assert parse(f'IF x {op} 3 THEN {{}}') == Program((If(Compare(op, Var('x'), Num('3')), ()),))


def test_nested_blocks_multiple_statements_and_empty_else():
    tree = parse('IF 1 == 1 THEN { REPEAT 2 TIMES { PRINT "a"; PRINT "b"; } } ELSE {}')
    assert tree.statements[0].then_body == (Repeat(Num('2'), (Print(Str('a')), Print(Str('b')))),)
    assert tree.statements[0].else_body == ()
    assert parse('') == Program(())


def test_repeat_count_range_is_semantic_not_syntax():
    assert parse('REPEAT 0.5 TIMES {}').statements[0].count == Num('0.5')


@pytest.mark.parametrize('source', [
    'LET = 1;', 'LET x 1;', 'PRINT ;', 'PRINT 1', 'IF x THEN {}',
    'IF x > 1 { PRINT x; }', 'REPEAT x TIMES {}', 'REPEAT -1 TIMES {}',
    'REPEAT 1 TIMES {', 'ELSE {}', 'PRINT 1; }', 'IF 1 < 2 < 3 THEN {}',
    'PRINT (1 + 2;', 'LET x = 1 2;', 'PRINT 1 == 1;',
])
def test_malformed_syntax_reports_parse_error(source):
    with pytest.raises(ParseError) as caught:
        parse(source)
    assert caught.value.line >= 1 and caught.value.column >= 1


def test_nested_input_fails_with_a_located_diagnostic():
    with pytest.raises(ParseError, match='deeply nested'):
        parse('PRINT ' + '(' * (MAX_DEPTH + 1) + '1' + ')' * (MAX_DEPTH + 1) + ';')


def test_all_development_golden_fixtures_match_ir_builder():
    fixtures = Path(__file__).resolve().parents[1] / 'fixtures' / 'valid.json'
    for fixture in json.loads(fixtures.read_text())['fixtures']:
        session = Session()
        for name, kind in fixture['given']['symbols'].items():
            value = '0' if kind == 'number' else '"text"'
            assert run(f'let {name} be {value}', session).status == 'ok'
        result = run(fixture['input'], session)
        assert result.status == 'ok', fixture['id']
        assert parse(fixture['expected_minilang']) == Program((result.trace.ast,)), fixture['id']


def test_seeded_malformed_input_never_leaks_an_unexpected_exception():
    rng = random.Random(2703)
    alphabet = 'LET PRINT IF THEN ELSE REPEAT TIMES xyz0123;{}()+-*/!=<>"\\\n'
    for _ in range(400):
        source = ''.join(rng.choices(alphabet, k=rng.randrange(100)))
        try:
            parse(source)
        except (LexError, ParseError):
            pass
