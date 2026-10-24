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
|   `-- ambiguous.json  English + given session -> expected clarification question
`-- eval_data/      held-out evaluation set (Phase 8); written after Phase 7 by a teammate, frozen before running
```

Mutation / corruption hooks for the Phase 7 mutation suite live **only** under `tests/`,
never in `src/` (CLAUDE.md rule 6).

## Ownership

**Each owner tests their own module.** Whoever writes `parsley/x/y.py` writes
`tests/unit/test_y.py` in the same PR, using test-driven development (CLAUDE.md). Owners are
listed in DEVELOPMENT.md. Integration tests for the pipeline and CLI belong to ASUS (the
integration owner). The mutation suite and evaluation tests belong to Gaming.

Every new behaviour and every bug fix gets a test (CLAUDE.md rule 8). PR descriptions state
the exact test command and paste its output (rules 8 and 9).

## Fixture format

All fixture files share this envelope:

```json
{
  "version": 1,
  "category": "valid | invalid | ambiguous",
  "spec": "LANGUAGE_SPEC.md",
  "fixtures": [ ... ]
}
```

Every fixture has:

| Key | Type | Meaning |
|---|---|---|
| `id` | `str` | Unique: `Vnn` valid, `Xnn` invalid, `Ann` ambiguous. Never reuse an id. |
| `input` | `str` | One English sentence, exactly as the user types it. |
| `given` | `object` | Session state before the input: `{"symbols": {name: "number"\|"string"}, "ref_stack": [name, ...]}`. `ref_stack` lists the most recent name last. Tests load this into a `Session`, with `declared_at` assigned in key order. |
| `note` | `str` (optional) | Why the case exists; which spec rule it exercises. |

Per category:

| Category | Extra keys |
|---|---|
| valid | `intent`, `rule` (LANGUAGE_SPEC.md rule id), `expected_minilang` (canonical format, LANGUAGE_SPEC.md 2.1), `expected_diagnostic_levels` (list of `"warning"`/`"info"`; empty when the statement is clean) |
| invalid | `expected_status` (`"unsupported"`), `reason` (`unsupported_phrasing` \| `out_of_scope` \| `malformed`) |
| ambiguous | `rule`, `expected_status` (`"ambiguous"`), `ambiguity` (`missing_slot` \| `alternatives` \| `typo` \| `operator_scope` \| `block_boundary`), `expected_question` (exact text from the LANGUAGE_SPEC.md 7.1 templates), `options` (list; empty for free answers) |

Rules for adding fixtures:

- Every fixture must follow LANGUAGE_SPEC.md exactly. A fixture that needs a new pattern means
  the spec changes first, in the same PR (CLAUDE.md rule 4).
- Do not write fixtures that depend on the LANGUAGE_SPEC.md Section 9 open questions until
  they are decided.
- Fixtures are for development and tuning. The Phase 8 evaluation set is separate and must
  not be copied from them.

`tests/unit/test_fixtures.py` checks the envelope, counts, unique ids and required keys.

## Phase exit tests

Each phase's exit test is listed in DEVELOPMENT.md. A phase is done only when its exit test
has been **run** and its output recorded.
