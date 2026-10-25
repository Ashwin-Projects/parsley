# Examples

Each UTF-8 `.txt` file is a self-contained session: one English sentence per line,
with a fresh session at the start and shared state between its sentences. There
are no comments, hidden variable declarations or scripted clarification answers.
The matching `.expected` file uses the same basename and ends with a newline.

- `valid/`: canonical MiniLang, including two implicit-declaration and `it`
  sessions (`implicit-pronoun-x` and `implicit-pronoun-score`).
- `invalid/`: semantic errors or unsupported input.
- `ambiguous/`: exact clarification questions, with any preceding setup code.

The `.expected` files contain the semantic output for each sentence in order:
canonical MiniLang for accepted statements; `stage CODE: message` for semantic
errors; the question verbatim for clarification; or `unsupported: REASON_CODE`
for unsupported input. Multiple unsupported reason codes are sorted and joined
with `, `. For rejections and clarifications, the reason/question is compared
even if batch mode also wraps it in an error diagnostic. Semantic errors take
precedence over any generated code. Trace output,
back-translation, warning diagnostics and suggestions are excluded from this
comparison. Implicit declaration is accepted with a warning, so it still
contributes a `LET` line. These are compiler outputs, not program execution
output (a print statement contributes `PRINT ...;`, not its evaluated value).

The source of truth remains [`tests/fixtures/`](../tests/fixtures/). The integration
test records every source fixture and any name/value replacements, and checks
the input and expected files against them:

| Session | Source fixtures |
|---|---|
| `valid/age` | V01, V04, V12 |
| `valid/greeting` | V03, V13 |
| `valid/conditional` | V01, V16 |
| `valid/repeat` | V18 |
| `valid/implicit-pronoun-x` | V06, V20 (`score` becomes `x`), V23 |
| `valid/implicit-pronoun-score` | V06 (`x = 5` becomes `score = 10`), V20, V19 |
| `invalid/undefined-variable` | M02 |
| `invalid/division-by-zero` | V06 (`x = 5` becomes `total = 10`), M08 |
| `invalid/repeat-zero` | M09 |
| `invalid/unsupported-list` | X02 |
| `ambiguous/missing-increase` | V06 (`x = 5` becomes `score = 10`), A01 |
| `ambiguous/empty-reference` | A02 |
| `ambiguous/typo` | V06 (`x = 5` becomes `score = 10`), A04 |
| `ambiguous/a12-three-alternatives` | A12 |
| `ambiguous/a13-assignment-alternatives` | V06, A13 |
| `ambiguous/a14-quoted-alternatives` | A14 |
| `ambiguous/a15-division-scope` | V06 (`x = 5` becomes `total = 10`), A15 |
| `ambiguous/a16-block-scope` | V06, A16 |
| `ambiguous/a17-assignment-typo` | V06 (`x = 5` becomes `score = 10`), A17 |
| `ambiguous/a18-pronoun-before-amount` | A18 |

Run the integration checks from the repository root:

```text
python -m pytest -q tests/integration/test_examples.py
```

File-pair and fixture checks always run. End-to-end comparisons run each sentence
through `parsley.pipeline` with one `Session` per file. They skip with an explicit
reason while the pipeline is unimplemented. The test's small adapter is marked
TODO for the pipeline owner's final entry point and result shape. Only an empty
or docstring-only pipeline module skips; an incompatible API or runtime failure
fails visibly instead of silently skipping.

Run a session with:

```text
python -m parsley.cli --file examples/valid/age.txt
```

Ambiguous sessions stop at a question for a user in interactive mode. In batch
mode, the question is reported as diagnostic `E102` without waiting for input.
The `.expected` file keeps only the exact question, excluding that CLI wrapper
and any listed options. To answer questions interactively, start the CLI without
`--file` and enter the example sentences in order.
