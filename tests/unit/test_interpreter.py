"""MiniLang execution has its own oracle; no imports from ast_eval."""

import pytest

from parsley.verify.interpreter import run


@pytest.mark.parametrize(('source', 'expected'), [
    ('PRINT 10 - 2 * 3; PRINT (10 - 2) * 3;', ({}, ['4', '24'], [])),
    ('LET X = -5; X = X + 7; PRINT X;', ({'X': 2}, ['2'], [])),
    ('PRINT 8 / 2; PRINT 7 / 2; PRINT 2.0;', ({}, ['4', '3.5', '2.0'], [])),
    ('PRINT "Hi" + " there";', ({}, ['Hi there'], [])),
    ('LET x = 0; REPEAT 3 TIMES { x = x + 2; } PRINT x;', ({'x': 6}, ['6'], [])),
    ('IF 3 != 4 THEN { PRINT "yes"; } ELSE { PRINT "no"; }', ({}, ['yes'], [])),
    ('IF "a" == "b" THEN { PRINT 1; } ELSE { PRINT 2; }', ({}, ['2'], [])),
    ('IF 1 > 2 THEN { PRINT missing; } PRINT 5;', ({}, ['5'], [])),
    ('PRINT missing; PRINT 7;', ({}, ['7'], ['undefined variable: missing'])),
    ('LET x = 0; PRINT 5 / x; PRINT 9;', ({'x': 0}, ['9'], ['division by zero'])),
    ('x = 1; PRINT 2;', ({}, ['2'], ['undefined variable: x'])),
    ('PRINT -"a";', ({}, [], ['type error: cannot negate text'])),
    ('PRINT "a" + 2;', ({}, [], ["type error: cannot apply '+' to text and number"])),
    ('IF "a" < "b" THEN {}', ({}, [], ["type error: cannot compare text and text with '<'"])),
    ('REPEAT 0 TIMES {}', ({}, [], ['invalid REPEAT count: 0'])),
    ('REPEAT 2.0 TIMES {}', ({}, [], ['invalid REPEAT count: 2.0'])),
])
def test_execution_contract(source, expected):
    assert run(source) == expected


def test_parse_failure_runs_nothing():
    state, output, errors = run('PRINT 1; LET = ;')
    assert state == {} and output == []
    assert errors[0].startswith('syntax error: ')


def test_loop_cap_and_run_isolation():
    assert len(run('REPEAT 1001 TIMES { PRINT 1; }')[1]) == 1000
    assert run('LET x = 4;')[0] == {'x': 4}
    assert run('PRINT x;') == ({}, [], ['undefined variable: x'])


def test_nested_repeats_obey_a_total_work_budget():
    state, output, errors = run('REPEAT 1000 TIMES { REPEAT 1000 TIMES {} }', max_steps=30)
    assert state == {} and output == []
    assert errors == ['execution step limit exceeded']


def test_long_expression_returns_an_error_instead_of_crashing():
    result = run('PRINT ' + ' + '.join(['1'] * 1600) + '; PRINT 9;')
    assert result[1] == ['9']
    assert result[2] == ['expression is too deeply nested']
