"""The AST evaluator has the same work budget as the interpreter, from one shared constant."""

import inspect

from parsley import verify
from parsley.compiler.parser import parse
from parsley.verify import ast_eval, interpreter


def test_nested_repeats_obey_a_total_work_budget():
    program = parse('REPEAT 1000 TIMES { REPEAT 1000 TIMES {} }')
    state, output, errors = ast_eval.run(program, max_steps=30)
    assert state == {} and output == []
    assert errors == [verify.STEP_LIMIT_ERROR]


def test_budget_stops_the_whole_run_and_keeps_earlier_effects():
    program = parse('LET x = 1; REPEAT 1000 TIMES { x = x + 1; } PRINT x;')
    state, output, errors = ast_eval.run(program, max_steps=50)
    assert errors == [verify.STEP_LIMIT_ERROR]
    assert output == [] and 1 < state['x'] < 1000


def test_both_evaluators_default_to_the_one_shared_step_limit():
    assert verify.STEP_LIMIT == 100_000
    assert verify.STEP_LIMIT_ERROR == 'execution step limit exceeded'
    assert inspect.signature(ast_eval.run).parameters['max_steps'].default == verify.STEP_LIMIT
    assert inspect.signature(interpreter.run).parameters['max_steps'].default == verify.STEP_LIMIT
    for module in (ast_eval, interpreter):
        assert '100_000' not in inspect.getsource(module)
        assert 'step limit exceeded' not in inspect.getsource(module)


def test_negative_zero_prints_with_its_sign():
    assert ast_eval.run(parse('PRINT -0.0;')) == ({}, ['-0.0'], [])
