"""Asserted, repeatable presentation of the actual English-to-MiniLang pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parsley.compiler.ast_nodes import Program
from parsley.compiler.codegen import generate
from parsley.pipeline import PipelineResult, answer, run
from parsley.session import Session
from parsley.verify.interpreter import run as interpret
from parsley.verify.summary import summarize


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def show(result: PipelineResult) -> None:
    print(f'  decision: {result.trace.decision}; status: {result.status}')
    if result.question:
        print(f'  question: {result.question}')
    for diagnostic in result.diagnostics:
        print(f'  {diagnostic.stage} {diagnostic.code}: {diagnostic.message}')
    if result.suggestion:
        print(f'  Try: {result.suggestion}')
    if result.minilang:
        print(f'  I understood: {result.back_translation}')
        print(f'  MiniLang: {result.minilang}')
    if result.verification:
        print(f'  {summarize(result.verification)}')
        require(result.verification.v2_match is True, 'V2 must pass in the demonstration')
        require(result.verification.v3_match is True, 'V3 must pass in the demonstration')


def demonstrate() -> None:
    session = Session()
    cases = [
        ('make a variable called score and set it to 10', None, 'LET score = 10;'),
        ('add 5 to it', None, 'score = score + 5;'),
        ('print total', None, 'PRINT "total";'),
        ('print scroe', 'yes', 'PRINT score;'),
        ('increase score', '2', 'score = score + 2;'),
        ('set score to 10 or 20', '20', 'score = 20;'),
        ('if score is at least 17 then print "adult" else print "minor"', None,
         'IF score >= 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }'),
        ('repeat 2 times print "hello"', None, 'REPEAT 2 TIMES { PRINT "hello"; }'),
    ]
    print('PARSLEY: real pipeline demonstration (scripted clarification replies)')
    for text, reply, expected in cases:
        print(f'\n> {text}')
        before = list(session.history)
        result = run(text, session)
        show(result)
        if reply is not None:
            require(result.status == 'needs_clarification', 'expected a clarification question')
            require(session.history == before, 'clarification changed session history')
            print(f'  scripted reply: {reply}')
            result = answer(result, reply, session)
            show(result)
        require(result.status == 'ok', f'failed to compile {text!r}')
        require(result.minilang == expected, f'unexpected code for {text!r}')

    print('\n> store 50 in bonus')
    before = list(session.history)
    rejected = run('store 50 in bonus', session)
    show(rejected)
    require(rejected.status == 'unsupported' and rejected.minilang is None, 'unsupported input ran')
    require(rejected.suggestion == 'set bonus to 50', 'N4 did not suggest the required rewrite')
    require(session.history == before, 'rejected input changed history')
    print('  checked: did not execute rejected input')

    print('\n> set score to missingValue plus 1')
    failed = run('set score to missingValue plus 1', session)
    show(failed)
    require(failed.status == 'error' and any(d.code == 'E201' for d in failed.diagnostics),
            'undefined arithmetic operand was not diagnosed')
    require(session.history == before, 'semantic error changed history')

    print('\nStrict confirmation: reject an interpretation')
    strict = Session()
    result = run('let approved be 1', strict, confirm=lambda text: False)
    show(result)
    require(result.status == 'error' and any(d.code == 'E103' for d in result.diagnostics),
            'strict confirmation was not enforced')
    require(not strict.history, 'strict rejection recorded code')

    print('\nSmall context ablation (demo case, not the held-out evaluation):')
    outcomes = []
    for enabled in (True, False):
        isolated = Session()
        require(run('let score be 10', isolated).status == 'ok', 'ablation setup failed')
        outcomes.append(run('add 5 to it', isolated, use_context=enabled).status)
    print(f'  context ON={outcomes[0]}; OFF={outcomes[1]}')
    require(outcomes == ['ok', 'error'], 'context ablation did not isolate pronoun resolution')

    state, output, errors = interpret(generate(Program(tuple(session.history))))
    require(state == {'score': 20} and output == ['total', '15', 'adult', 'hello', 'hello'] and not errors,
            'final execution did not match the presentation')
    print(f'\nFinal variables: {state}; printed output: {output}; errors: {errors}')
    print('DEMO PASS: real N1, N2, N4, V1/V2/V3, semantic rejection, confirmation and context ablation.')
    print('Full held-out metrics and clarification ablation belong to the Evaluation owner; no results invented.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-mutations', action='store_true', help='also run test-only V2/V3 mutations')
    args = parser.parse_args()
    try:
        demonstrate()
    except RuntimeError as error:
        print(f'DEMO FAILED: {error}', file=sys.stderr)
        return 1
    if args.with_mutations:
        sys.stdout.flush()
        return subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', '-s',
             'tests/integration/test_verifier_mutations.py', '-k', 'test_mutation_detection'],
            cwd=ROOT, check=False,
        ).returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
