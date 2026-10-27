# Parser/Verifier handoff

Branch: `phase-3-6-7-8-9-completion`.
Base: `phase-7-verifier` at `1c2de76eb9b7d407c73eb69a4d7680dd3685f9db`.
That base already includes `main` at `c47d4dd05a6eb3ff9f3326e387f839655b60695d`.
The two existing branches were not edited, merged, rebased or reset.

## Assigned deliverables

| Assignment | Completed work |
|---|---|
| Phase 3: lexer and parser | Reused the existing implementation on the verifier branch. Added direct lexical/syntax tests, exact AST and all-golden-fixture checks, precedence, unary minus, comparison, block, location, nesting and seeded-malformed-input checks. Removed the duplicate lexer keyword definition. |
| Phase 6: N4 | Implemented `suggest(text, reason_code)`. Uses supported pattern metadata, token overlap and Levenshtein ranking. Safely rewrites simple `store VALUE in NAME` inputs and misspelled command words, and explains rejected block continuations. Preserves identifier case and values. Never accepts rejected input or emits MiniLang. |
| Phase 7: roundtrip and interpreter | Validated inherited modules; V2 now uses a stack to avoid recursive-equality crashes on long expressions and reports a differing field. Interpreter remains independent of `ast_eval.py`, with a whole-run work budget and controlled excessive-expression-depth errors. Both real verifiers pass every valid development fixture. |
| Phase 8: held-out paraphrases | Prepared 15 groups x 4 inputs, setup sessions, canonical gold statements, author/method limitations and a SHA-256 freeze. Gold/data validator does not run held-out English through NLP. |
| Phase 9: demonstration | Added an asserted real-pipeline script, failure-path tests, presenter guide, test-only mutation demonstration and a captured rehearsal transcript. |

Existing `ast_eval.py`, AST, code generator, semantics, context, ambiguity, pipeline and CLI
runtime files were preserved. Existing Core CLI/pipeline **tests** were adjusted because
modules are now implemented: missing-module cases explicitly monkeypatch missing functions
instead of relying on permanent stubs. No frozen cross-stage contract or language grammar
was changed. The optional interpreter budget parameter preserves `run(source)` callers.

## Exact checks run

Environment: Python 3.12.5; pytest 8.4.2. Commands from the repository root after activating
the virtual environment (the execution used `.venv/bin/python` explicitly):

```
python -m pip install -r requirements.txt -e .
python -m pytest -q
# 1588 passed in 2.32s

python scripts/validate_paraphrases.py
# PASS: 15 groups / 60 inputs; digest, schema, separation and gold programs valid.
# No NLP accuracy or paraphrase-consistency result is claimed by this validation.

python scripts/demo.py --with-mutations
# DEMO PASS ...
# 9 passed, 24 deselected in 0.02s (the test-only mutation selection)

python -m compileall -q src scripts
# exit 0

git diff --check
# exit 0
```

The inherited branch's baseline had 6 failing tests / 1437 passing tests: the failures
assumed the implemented V2/V3 functions were absent. New regression tests were first run
against the old implementation to expose the shared-keyword, deep-equality, work-budget,
expression-depth and placeholder-substitution issues before fixing them.
A manual Python review checked types, error paths, independent evaluator imports, mutation
locations, interface compatibility and changed docs. The inherited GitHub Actions matrix
covers Python 3.11 and 3.13; those remote runs are not claimed as locally executed.

## Known limits and team follow-up

- The user assigned **paraphrase preparation**, not the whole Phase 8 evaluation. `eval/`
  remains unfinished; no held-out accuracy, consistency score or full ablation table is
  fabricated. The demo's context comparison is one labeled presentation case.
- The paraphrases are AI-assisted and blind to the implementation table, not independent
  human annotations. Their author read the specification and fixtures. Human review of
  intended equivalence remains appropriate before publishing final study results.
- N4 is conservative: it does not promise a useful suggestion for arbitrary unsupported
  English. It declines malformed input, out-of-scope requests and alternatives it cannot
  safely rewrite. Suggestions are advice; they do not execute.
- The interpreter's default 100,000-step guard can stop large valid nested MiniLang. The
  inherited AST evaluator has only the per-REPEAT cap. Very large or deeply nested programs
  can therefore fail V3 or exhaust the AST evaluator's resources. The English front end
  currently excludes nested blocks; coordinating an independently implemented AST-evaluator
  total budget is an Evaluation-owner follow-up.
- Runtime behavior retained from the existing verifier branch: each loop is clamped to
  1000 iterations; zero/decimal counts are runtime errors. The semantic analyzer rejects
  out-of-range counts before the normal pipeline records them. Types and forbidden block
  declarations are checked by semantic analysis before verification, rather than duplicated
  wholesale in the interpreter.
- V3 compares final state, output and errors; equal-behavior or unexecuted changes can evade
  it. Tests demonstrate this. V2 catches those structural differences.
- Pipeline contract: a verification failure is reported; it does not roll back or change an
  accepted compilation status. The demonstration script requires every layer to pass.
- `docs/demo-transcript.txt` is a captured text rehearsal, not a video recording. Full report,
  release, Evaluation-owned metrics and a screen recording remain separate team tasks.
- Adding mutation/integration tests and adjusting Core tests should receive the appropriate
  owners' normal PR review; no shared runtime contracts were modified.

## Complete changed-file list relative to the base

- `README.md`
- `DEVELOPMENT.md`
- `TESTING.md`
- `src/parsley/compiler/lexer.py`
- `src/parsley/nlp/suggest.py`
- `src/parsley/verify/roundtrip.py`
- `src/parsley/verify/interpreter.py`
- `scripts/demo.py`
- `scripts/validate_paraphrases.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_pipeline.py`
- `tests/unit/test_lexer.py`
- `tests/unit/test_parser.py`
- `tests/unit/test_roundtrip.py`
- `tests/unit/test_interpreter.py`
- `tests/unit/test_suggest.py`
- `tests/unit/test_paraphrase_data.py`
- `tests/integration/test_verifier_mutations.py`
- `tests/integration/test_demo.py`
- `tests/eval_data/paraphrases.json`
- `tests/eval_data/paraphrases.sha256`
- `tests/eval_data/README.md`
- `docs/DEMO.md`
- `docs/demo-transcript.txt`
- `docs/ASSIGNED_PHASES.md`

Compared to `main`, the branch additionally contains the base branch's existing
`compiler/lexer.py`, `compiler/parser.py`, `verify/ast_eval.py`, `verify/interpreter.py`,
`verify/roundtrip.py`, and `verify/summary.py` work. It was preserved, not reauthored.
