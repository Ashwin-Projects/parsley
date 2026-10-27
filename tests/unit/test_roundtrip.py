"""V2 diagnostics and resilience; all corruption is confined to tests."""

from parsley.compiler.ast_nodes import BinOp, Num, Print, Program
from parsley.compiler.parser import parse
from parsley.verify.roundtrip import check


def test_roundtrip_success_and_parse_failure():
    assert check('PRINT 1;', parse('PRINT 1;')) is None
    assert 're-parse failed' in check('PRINT ;', parse('PRINT 1;'))


def test_first_different_operator_and_literal():
    assert "Program.statements[0].value.op: expected '+', got '-'" == check(
        'PRINT 1 - 2;', parse('PRINT 1 + 2;'),
    )
    assert '.value.text' in check('PRINT 9;', parse('PRINT 1;'))


def test_dropped_statement_and_absent_else_are_different():
    assert 'expected 2 items, got 1' in check('PRINT 1;', parse('PRINT 1; PRINT 2;'))
    assert '.else_body' in check('IF 1 == 1 THEN {} ELSE {}', parse('IF 1 == 1 THEN {}'))


def test_long_flat_expression_roundtrips_without_python_recursion_error():
    expr = Num('1')
    for _ in range(1200):
        expr = BinOp('+', expr, Num('1'))
    assert check('PRINT ' + ' + '.join(['1'] * 1201) + ';', Program((Print(expr),))) is None
