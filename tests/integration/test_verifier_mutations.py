"""Test-only corruptions: report which V2/V3 layers detect each mutation."""

import json
from pathlib import Path

import pytest

from parsley.compiler.ast_nodes import Program
from parsley.compiler.codegen import generate
from parsley.compiler.parser import parse
from parsley.pipeline import run
from parsley.session import Session
from parsley.verify import ast_eval, interpreter, roundtrip


@pytest.mark.parametrize(('name', 'original', 'corrupted', 'v2_detects', 'v3_detects'), [
    ('operator', 'PRINT 8 + 2;', 'PRINT 8 - 2;', True, True),
    ('dropped_statement', 'PRINT 1; PRINT 2;', 'PRINT 1;', True, True),
    ('literal', 'LET x = 4; PRINT x;', 'LET x = 5; PRINT x;', True, True),
    ('precedence', 'PRINT (2 + 3) * 4;', 'PRINT 2 + 3 * 4;', True, True),
    ('runtime_error', 'LET x = 2; PRINT 4 / x;', 'LET x = 0; PRINT 4 / x;', True, True),
    ('syntax_error', 'PRINT 1;', 'PRINT ;', True, True),
    ('equivalent_mutant', 'PRINT 2 + 2;', 'PRINT 2 * 2;', True, False),
    ('unexecuted_branch', 'IF 1 > 2 THEN { PRINT 3; }', 'IF 1 > 2 THEN { PRINT 9; }', True, False),
    ('harmless_whitespace', 'PRINT 1;', ' PRINT  1 ;\n', False, False),
])
def test_mutation_detection(name, original, corrupted, v2_detects, v3_detects):
    expected = parse(original)
    assert (roundtrip.check(corrupted, expected) is not None) is v2_detects
    assert (ast_eval.run(expected) != interpreter.run(corrupted)) is v3_detects
    print(f'{name}: V2={"detected" if v2_detects else "same"}; '
          f'V3={"detected" if v3_detects else "same behavior"}')


@pytest.mark.parametrize('fixture', json.loads(
    (Path(__file__).resolve().parents[1] / 'fixtures/valid.json').read_text(),
)['fixtures'], ids=lambda f: f['id'])
def test_all_valid_fixtures_pass_both_real_verifiers(fixture):
    session = Session()
    for name, kind in fixture['given']['symbols'].items():
        value = '0' if kind == 'number' else '"text"'
        assert run(f'let {name} be {value}', session).status == 'ok'
    result = run(fixture['input'], session)
    assert result.status == 'ok'
    assert result.verification.v2_match is True
    assert result.verification.v3_match is True
    program = Program(tuple(session.history))
    assert ast_eval.run(program) == interpreter.run(generate(program))


def test_evaluators_are_independent_modules():
    import ast
    for module, forbidden in [(interpreter, 'ast_eval'), (ast_eval, 'interpreter')]:
        tree = ast.parse(Path(module.__file__).read_text())
        imports = [
            node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        ]
        assert not any(forbidden in name for name in imports)
