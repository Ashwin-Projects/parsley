# Testing

Framework: `pytest` (the only dependency). Run everything from the repo root:

```
python -m pytest -q
```

## Layout

```
tests/
|-- unit/           one test file per module: test_<module>.py (e.g. test_normalizer.py)
|-- integration/    multi-stage tests: pipeline, CLI, REPL clarification, sessions
|-- fixtures/       development fixtures (JSON), shared by all phases
|   |-- valid.json      English + given session -> expected MiniLang
|   |-- invalid.json    English -> expected "unsupported"
|   |-- ambiguous.json  English + given session -> expected clarification question
|   `-- semantic.json   English + given session -> expected semantic diagnostic codes (Phase 4)
`-- eval_data/      held-out evaluation set (Phase 8); written after Phase 7 by a teammate, frozen before running
```

Mutation / corruption hooks for the Phase 7 mutation suite live **only** under `tests/`,
never in `src/` (CLAUDE.md rule 6).

## Ownership

**Each owner tests their own module.** Whoever writes `parsley/x/y.py` writes
`tests/unit/test_y.py` in the same PR, using test-driven development (CLAUDE.md). Owners are
listed in DEVELOPMENT.md. Integration tests for the pipeline and CLI belong to Core (the
integration owner). The mutation suite and evaluation tests belong to Evaluation.

Every new behaviour and every bug fix gets a test (CLAUDE.md rule 8). PR descriptions state
the exact test command and paste its output (rules 8 and 9).

## Fixture format

All fixture files share this envelope:

```json
{
  "version": 1,
  "category": "valid | invalid | ambiguous | semantic",
  "spec": "LANGUAGE_SPEC.md",
  "fixtures": [ ... ]
}
```

Every fixture has:

| Key | Type | Meaning |
|---|---|---|
| `id` | `str` | Unique: `Vnn` valid, `Xnn` invalid, `Ann` ambiguous, `Mnn` semantic. Never reuse an id (retired: `A07`). |
| `input` | `str` | One English sentence, exactly as the user types it. |
| `given` | `object` | Session state before the input: `{"symbols": {name: "number"\|"string"}, "ref_stack": [name, ...]}`. `ref_stack` lists the most recent name last. Tests load this into a `Session`, with `declared_at` assigned in key order. |
| `note` | `str` (optional) | Why the case exists; which spec rule it exercises. |

Per category:

| Category | Extra keys |
|---|---|
| valid | `intent`, `rule` (LANGUAGE_SPEC.md rule id), `expected_slots` (the top candidate's slots after Phase 2, in the ARCHITECTURE.md 2.3 slot shapes; bare words stay unresolved `word`s), `expected_minilang` (canonical format, LANGUAGE_SPEC.md 2.1), `expected_diagnostic_levels` (list of `"warning"`/`"info"`; empty when the statement is clean) |
| invalid | `expected_status` (`"unsupported"`), `expected_reason_code` (the `NLPResult.notes` reason code, ARCHITECTURE.md 2.4), `reason` (`unsupported_phrasing` \| `out_of_scope` \| `block_continuation` \| `malformed`), optional `expected_suggestion` (exact text, where the spec fixes it) |
| ambiguous | `rule`, `expected_status` (`"ambiguous"`), `ambiguity` (`missing_slot` \| `alternatives` \| `typo` \| `operator_scope`), `expected_question` (exact text from the LANGUAGE_SPEC.md 7.1 templates), `options` (list; empty for free answers) |
| semantic | `rule`, `expected_status` (`"ok"`: the NLP accepts it), `expected_diagnostic_codes` (e.g. `["E201"]`) |

Rules for adding fixtures:

- Every fixture must follow LANGUAGE_SPEC.md exactly. A fixture that needs a new pattern means
  the spec changes first, in the same PR (CLAUDE.md rule 4).
- `tests/fixtures/` is the single source of truth for fixtures (decision D-5). `examples/`
  holds runnable sessions built from them, from Phase 5.
- Fixtures are for development and tuning. The Phase 8 evaluation set is separate and must
  not be copied from them.

`tests/unit/test_fixtures.py` checks the envelope, counts, unique ids and required keys.

## Phase exit tests

Each phase's exit test is listed in DEVELOPMENT.md. A phase is done only when its exit test
has been **run** and its output recorded.

## Parser/Verifier contribution checks (2026-10-27)

```
python -m pytest -q
python scripts/validate_paraphrases.py
python scripts/demo.py --with-mutations
```

`test_lexer.py`, `test_parser.py`, `test_roundtrip.py`, `test_interpreter.py` and
`test_suggest.py` cover the assigned runtime modules. Existing CLI/pipeline tests now
exercise available verifiers; missing-layer tests explicitly remove their functions with
`monkeypatch`, so they remain meaningful after implementation.

`tests/integration/test_verifier_mutations.py` compares both real evaluators and V2 on all
valid development fixtures. Its corruptions live only in tests: operator swaps, dropped
statements, changed literals, lost grouping, runtime and syntax errors. Equivalent-result
and unexecuted-branch mutations are expected to pass V3 while failing V2; whitespace passes
both. `test_demo.py` also injects a test-only V2 failure to ensure the presentation fails.

`test_paraphrase_data.py` checks held-out integrity and gold validity without compiling the
held-out English. Paraphrase consistency and NLP coverage belong in the Evaluation owner's
runner, never as tuning assertions in the unit suite.

The interpreter uses a per-loop 1000-iteration cap and an independent total work budget
(default 100,000 statement/expression/iteration steps). `run(source, max_steps=...)` can
reduce it for a bounded test. Exceeding it reports `execution step limit exceeded` and
stops the run. The AST evaluator retains its inherited per-loop cap; it has no total work
budget yet. This is a known limitation for arbitrary deeply nested MiniLang, which the
current English front end does not generate.
