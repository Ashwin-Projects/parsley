# Parsley

**A context-aware, self-verifying compiler from constrained English to MiniLang.**

Parsley turns plain English instructions into MiniLang, a small, formally specified
programming language, and checks its own output instead of asking you to trust it.

```
> make a variable called score and set it to 10
  I understood: create variable score with value 10.
  MiniLang:     LET score = 10;

> add 5 to it
  I understood: increase score by 5.
  MiniLang:     score = score + 5;

> print scroe
  Did you mean the variable score?
```

It is deterministic and runs offline. It uses only the Python standard library, with no
LLMs and no external APIs.

> **Status (2026-10-27):** the English pipeline, standalone MiniLang lexer/parser,
> N4 rewrite suggestions, V2 structural comparison and V3 execution checks are working.
> Run `python scripts/demo.py --with-mutations` for the checked presentation and
> `python scripts/validate_paraphrases.py` to validate 60 frozen paraphrase inputs.
> The evaluation runner, metrics and ablation (`eval/`) are not written yet.

---

## Why Parsley is different

Translating English into code is an established area, so Parsley doesn't claim to be the
first such system. What it adds is a specific combination of three ideas inside a formally
specified language, measured with an evaluation and an ablation.

### 1. Compiler-informed interpretation

In a normal pipeline, information only flows one way: English, then the compiler. In
Parsley, the compiler's **symbol table and statement history flow back** into the English
stage to settle what the sentence leaves open.

| English problem | How Parsley resolves it | Example |
|---|---|---|
| Variable or text? | A declared name is a variable; quoted text is always a string; anything else is text | after `LET age = 20;`, `print age` → `PRINT age;`, `print total` → `PRINT "total";` |
| Pronouns | `it`, `that` and `the variable` refer to the most recently used variable | `set score to 10. add 5 to it.` → `score = score + 5;` |
| Implicit declaration | Assigning to an undeclared name declares it, with a warning | `set x to 5` → `LET x = 5;` |
| Typos | A near miss of a declared name triggers a question. Parsley never corrects silently | `print scroe` → "Did you mean the variable score?" |
| Types | Inferred types are tracked and mismatches are explained in plain English | `add 5 to name` (a string) → type error |

### 2. Explicit ambiguity handling

The front end returns **ranked candidate interpretations**, each with a score, instead of
a single guess. A decision rule then picks one of three outcomes:

- **Accept**: one clear winner, with no missing information. Example: `set age to 21`.
- **Clarify**: two plausible readings, or something is missing, so Parsley asks a
  targeted question. Examples: `increase x` → "By how much?", and `set x to 10 or 20` →
  "10 or 20?"
- **Reject**: nothing supported matches, so Parsley explains why and suggests a supported rewrite when one is close.
  Example: `store 50 in bonus` → "Try: set bonus to 50".

In file mode a clarification becomes a diagnostic, so batch runs never hang.

### 3. Layered verification

Every accepted statement is checked in three ways. Each check catches a different kind of
error.

| Layer | What it does | Catches |
|---|---|---|
| **Back-translation** | Turns the AST back into canonical English ("I understood: …") | The NLP misunderstanding the sentence |
| **Structural round-trip** | Re-parses the generated MiniLang and compares the ASTs | Code-generator and grammar bugs |
| **Execution equivalence** | Runs the program through two independent evaluators and compares state and output | Code that parses but means something else |

These layers verify output against defined checks. They do not prove that every English
interpretation is correct.

---

## How it works

```
English sentence
   │
   ▼
Normalizer ─────────────── lowercases command words; keeps identifier case
   │
   ▼
Candidate generator ◄───── context resolver (symbol table + reference stack)
   │
   ▼
Ambiguity gate ─────────── accept │ clarify (ask) │ reject (suggest)
   │
   ▼
IR / AST builder
   │
   ▼
Semantic analyzer + symbol table ──► feeds the context resolver
   │
   ▼
Code generator ─────────── AST → MiniLang text
   │
   ▼
Verifier ───────────────── back-translation │ round-trip │ execution equivalence
   │
   ▼
Trace / output
```

The design follows a few strict rules:

- No stage silently guesses. Each one returns a testable result or a diagnostic.
- The NLP never writes MiniLang. It produces candidates, and only the code generator
  writes code.
- The symbol table has one owner, the semantic analyzer. The context resolver only
  reads it.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full data contracts.

---

## MiniLang

A deliberately small language with numbers, strings, variables, `PRINT`, `IF` / `ELSE`
and `REPEAT`.

```
LET age = 20;
age = age + 1;
IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }
REPEAT 3 TIMES { PRINT "hello"; }
```

### Supported English

| Intent | English | MiniLang |
|---|---|---|
| Declare | `make a variable called age and set it to 20` | `LET age = 20;` |
| Assign | `set age to age plus 1` / `change age to 30` | `age = age + 1;` |
| Increment / decrement | `increase count by 2` / `decrease count by 1` | `count = count + 2;` |
| Arithmetic assign | `multiply total by 3` / `divide total by 2` | `total = total * 3;` |
| Print | `print age` / `show "Hello"` / `display hello world` | `PRINT age;` / `PRINT "hello world";` |
| If | `if age is greater than 17 then print adult else print minor` | `IF age > 17 THEN { ... } ELSE { ... }` |
| Repeat | `repeat 3 times print hello` | `REPEAT 3 TIMES { PRINT "hello"; }` |
| Reference | `add 5 to it` | `score = score + 5;` |

The full grammar, type rules, accepted phrasings and rejected patterns are in
[LANGUAGE_SPEC.md](LANGUAGE_SPEC.md).

---

## Getting started

Requires Python 3.11 or newer.

```
git clone https://github.com/Ashwin-Projects/parsley.git
cd parsley
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Run the tests:

```
python -m pytest -q
```

Run the CLI:

```
parsley "set age to 21"
python -m parsley "set age to 21"
parsley --file examples/valid/age.txt --output program.mini
parsley --confirm
```

With no sentence or file, the CLI starts a REPL. Answer clarification questions
with a value/name, an option's text or number, or `yes`/`no` for a typo. Invalid
answers repeat the question; an empty answer cancels the sentence. `--confirm`
asks before recording each error-free statement: `yes` accepts, `no` (or empty)
rejects with `E103`. File mode shares one session, never prompts, and reports
clarifications as `ambiguity E102`; `--confirm` outside the REPL reports `E103`.

`--trace` shows candidates, the decision, the AST and the verification details;
`--output PATH` writes the accepted program; `--no-context` disables context
resolution. Pipeline statuses are `ok`, `needs_clarification`, `unsupported` and
`error`. The CLI exits 0 on success and 1 on a processing error (2 for invalid
arguments, 130 on interruption).

Each accepted statement ends with a verification summary such as
`V1 ok | V2 ok | V3 ok`. A missing layer reports `skipped`; a disagreement reports
`failed`. As defined by the pipeline contract, verification reports findings and does
not change the compilation status. An unsupported sentence reports its reason
(e.g. `candidates E101: ... (NO_MATCH)`), followed by `Try: ...` when a supported
phrasing is close.

---

## Evaluation

The held-out set has **15 frozen paraphrase groups / 60 English
inputs**, with setup sessions and expected MiniLang. They were written before looking at
the implementation pattern table and include plausible out-of-coverage wording. Their
AI-assisted provenance and limits are recorded in `tests/eval_data/README.md`.

```
python scripts/validate_paraphrases.py
python scripts/demo.py
python scripts/demo.py --with-mutations
```

The validator checks the digest, schema, separation from development fixtures and the
syntax/semantics/execution of gold programs. It does **not** assert NLP accuracy on held-out
inputs. Do not tune on these inputs. Full metrics, the remaining evaluation subsets and
N1/N2 ablation tables are not written yet (`eval/` is unfinished).
See [the demo guide](docs/DEMO.md) and [the phase handoff](docs/ASSIGNED_PHASES.md).

---

## Project layout

```
src/parsley/
├── cli.py  pipeline.py  session.py  diagnostics.py  keywords.py
├── nlp/        normalizer, pattern table, candidates, context, ambiguity, suggestions
├── compiler/   AST nodes, IR builder, lexer, parser, semantic analysis, symbols, codegen
├── verify/     back-translation, round-trip, AST evaluator, interpreter
└── eval/       dataset, metrics, evaluation runner
tests/          unit/  integration/  fixtures/  eval_data/
examples/       valid/  invalid/  ambiguous/
```

---

## Limitations

- Only constrained English is supported; paraphrase coverage is limited by the pattern
  table.
- MiniLang has no functions, lists or user input.
- Verification checks the output against defined checks; it is not a proof of
  correctness.

---

## Documentation

| File | Contents |
|---|---|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Problem, goals, non-goals, success criteria |
| [LANGUAGE_SPEC.md](LANGUAGE_SPEC.md) | Grammar, types, English patterns, ambiguity rules |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline and data contracts |
| [NOVELTY.md](NOVELTY.md) | Contributions, what is not claimed, metrics, related work |
| [TESTING.md](TESTING.md) | Test layout and fixture format |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Contributor workflow and current progress |
