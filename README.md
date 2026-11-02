# Parsley

**A context-aware, self-verifying compiler from constrained English to MiniLang.**

License: [MIT](LICENSE).

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

By default it is deterministic and runs offline, using only the Python standard library,
with no LLMs and no external APIs. An [optional LLM mode](#optional-llm-modes) can propose
readings for sentences the rules miss; every proposal goes through the same checks.

> **Status (2026-10-27):** the English pipeline, standalone MiniLang lexer/parser,
> N4 rewrite suggestions, V2 structural comparison and V3 execution checks are working.
> Run `python scripts/demo.py --with-mutations` for the checked presentation and
> `python scripts/validate_paraphrases.py` to validate 60 frozen paraphrase inputs.
> `python -m parsley.eval.run_eval` runs the held-out evaluation and ablations (see
> [Evaluation](#evaluation)).

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
| Declare | `make a variable called age and set it to 20` / `define age as 20` | `LET age = 20;` |
| Assign | `set age to age plus 1` / `change age to 30` | `age = age + 1;` |
| Increment / decrement | `increase count by 2` / `increase the count by 2` / `decrease count by 1` | `count = count + 2;` |
| Arithmetic assign | `multiply total by 3` / `divide total by 2` | `total = total * 3;` |
| Print | `print age` / `show me age` / `show "Hello"` / `display hello world` | `PRINT age;` / `PRINT "hello world";` |
| If | `if age is greater than 17 then print adult else print minor` | `IF age > 17 THEN { ... } ELSE { ... }` |
| Repeat | `repeat 3 times print hello` / `loop 3 times print hello` | `REPEAT 3 TIMES { PRINT "hello"; }` |
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

The demo and paraphrase validation scripts run from the repo root with no install needed.

Run the tests:

```
python -m pytest -q
```

Run the CLI:

```
parsley "set age to 21"
python -m parsley "set age to 21"
parsley --file examples/valid/age.txt --output program.mini
parsley --file examples/valid/vocabulary.txt --run
parsley --confirm
parsley --version
```

`--run` runs the accepted program after the last sentence and prints its output under
`Output:`. Runtime errors (such as division by zero) go to stderr as `runtime error: ...`
and make the exit code 1. Code generation is the same with or without `--run`.
`--version` prints the version from `pyproject.toml`.

With no sentence or file, the CLI starts a REPL. Lines that start with `:` are
commands, never English:

| Command | Effect |
|---|---|
| `:run` | Run the program so far and show what it prints, plus any runtime errors |
| `:program` | Show all accepted MiniLang so far |
| `:undo` | Remove the last accepted statement; variables and `it` go back to how they were |
| `:reset` | Start a new, empty session |
| `:help` | List the commands and example phrasings |
| `:quit` | Leave the REPL (end of input also works) |

Answer clarification questions
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

## Optional LLM modes

The default, `--mode rules`, never uses a model, never reads `.env` and never touches the
network. Two other modes let a language model propose readings:

| Mode | When the model is asked | What is compared |
|---|---|---|
| `rules` (default) | Never | Pattern rules only |
| `hybrid` | When no rule matches, or the best rule match is weak (score below 0.55) | Rule readings and model readings |
| `llm` | For every sentence | Model readings; the rule result if the model fails, and rule readings too if the rules would ask a question |

```
parsley --mode hybrid "store 50 in bonus"
parsley --mode hybrid --file examples/valid/age.txt --trace
parsley --mode hybrid
```

The model only proposes. Each reading must fit the same data structure as a rule's, may use
only words and numbers from your sentence, and then goes through context resolution, the
ambiguity gate, semantic checks and all three verification layers. If two readings are close,
Parsley asks. If the model fails or times out, you get the rule result and a warning. An
accepted model reading always carries `W513`, so read the `I understood:` line.

### Configure a provider

Copy [.env.example](.env.example) to `.env` (it is git-ignored) and set a provider. Real
environment variables win over `.env`.

| Variable | Meaning |
|---|---|
| `PARSLEY_LLM_PROVIDER` | `anthropic`, `openai` (any OpenAI-compatible server) or `fake` |
| `PARSLEY_LLM_MODEL` | The model; optional for `anthropic` (default `claude-opus-5-5`), required for `openai` |
| `PARSLEY_LLM_BASE_URL` | Server URL, for `openai` servers other than OpenAI |
| `PARSLEY_LLM_TIMEOUT` | Seconds per attempt (default 20); a failed call is retried once |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PARSLEY_LLM_API_KEY` | The key; the last one wins over the vendor names |
| `PARSLEY_LLM_FIXTURES` | For `fake`: a file of recorded responses |

```
# Anthropic
PARSLEY_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...

# Groq
PARSLEY_LLM_PROVIDER=openai
PARSLEY_LLM_BASE_URL=https://api.groq.com/openai/v1
PARSLEY_LLM_MODEL=your-model
PARSLEY_LLM_API_KEY=...

# Ollama (local, no key)
PARSLEY_LLM_PROVIDER=openai
PARSLEY_LLM_BASE_URL=http://localhost:11434/v1
PARSLEY_LLM_MODEL=your-model
```

To try the modes without a key or a network, replay the recorded responses:

```
PARSLEY_LLM_PROVIDER=fake
PARSLEY_LLM_FIXTURES=tests/fixtures_llm/recorded.json
```

With `--trace`, candidates from the model show as `LLM`, and the trace says why the model was
asked and why any reading was discarded.

| Warning | Meaning |
|---|---|
| `W510` | The model call failed; the rule result stands |
| `W511` | The model timed out; the rule result stands |
| `W512` | No proposed reading passed validation; the rule result stands |
| `W513` | The accepted reading came from the model, so check the back-translation |
| `W514` | No provider is configured; the rule result stands |

Good to know:

- Your sentence, your variable names and their types are sent to the provider you configure.
- These modes are not deterministic, and each model call adds time and may cost money.
- A reading can only use what the sentence says, with one exception: an implied amount, as in
  `double x`. Parsley always asks first (`Did you mean: multiply x by 2?`), and in file mode
  that is `E102`, so it never compiles unconfirmed.
- A model can still misread a sentence in a way that passes every check, such as swapping two
  variables. No accuracy has been measured for these modes, and the evaluation below is
  `rules` mode only.

---

## Web API

An optional HTTP API backs the web frontend. It needs the `web` extra:

```
pip install -e ".[web]"
parsley-web                       # or: python -m parsley.web --port 8000
```

It listens on `127.0.0.1:8000` and allows browser requests from `localhost:5173`.

| Endpoint | Request | Response |
|---|---|---|
| `POST /api/session` | `{}` | `{session_id}` |
| `POST /api/compile` | `{session_id, sentence, mode}` | `{status, minilang?, understood?, checks?, question?, diagnostics, suggestion?, source?, trace?}` |
| `POST /api/answer` | `{session_id, answer}` | Same as compile |
| `GET /api/program?session_id=` | | `{minilang, statements: [{english, minilang}]}` |
| `POST /api/run` | `{session_id}` | `{output, variables, error?}` |
| `POST /api/undo`, `POST /api/reset` | `{session_id}` | `{ok}` |
| `GET /api/health` | | `{version, llm_configured, provider?, model?}` |

`status` is `accepted`, `clarify`, `rejected` or `error`, and `source` says whether the reading
came from `rules` or the `llm`. Each sentence goes through the same pipeline as the CLI. Sessions
live in memory only: one expires after an hour unused, and at 1000 sessions the least recently
used one is dropped. A sentence can be 500 characters long and a session can hold 500 statements.
`llm` and `hybrid` use the provider configured above, loaded the first time it is needed, with at
most 14 seconds per attempt. `/api/health` reads that configuration too, but never calls the model
and never returns a key or a base URL.
Unknown or expired sessions return 404, and errors never include a stack trace or a key.

---

## Evaluation

Run from the repository root (after `pip install -e .`):

```
python -m parsley.eval.run_eval
```

It runs every frozen held-out input in `tests/eval_data/` (168 inputs: 15 paraphrase groups
of 4, 25 ambiguous, 25 unsupported, 10 multi-sentence sessions) through the real pipeline,
with context resolution on and off and with clarification replaced by a forced top-1 guess.
It writes `results/results.csv` (one row per input and condition) and `results/summary.md`
(metrics, ablations, failures by category, mutation detection by layer). The output is
deterministic. A file whose SHA-256 freeze does not match is refused. An optional
`human_blind.json` is reported in its own section (format in [TESTING.md](TESTING.md)).

Results on the held-out set (2026-10-27):

- Exact match 104/118 (88.1%), with no wrong code, no crashes and 25/25 unsupported inputs safely rejected.
- With context resolution off, exact match falls to 38/118 (32.2%).
- Without clarification (forced top-1 guess), wrong code rises from 0 to 11/168.
- Injected code-generation bugs: V2 caught 188/188 and V3 173/188; V3 caught none that V2 missed.
- Weak spots: paraphrase consistency 1/15 groups and N4 suggestion usefulness 0/13.

To evaluate a model on the same inputs, add `--mode hybrid` or `--mode llm`:

```
python -m parsley.eval.run_eval --mode hybrid --delay 2 --record results/recorded_hybrid.json
```

Those runs write `results_<mode>_<model>.csv` and `summary_<mode>_<model>.md`, so the rules
results are never overwritten, and report wrong code first. Responses are cached on disk by
model, prompt hash and input in `results/llm_cache/` (`--cache DIR`), so a re-run is free and
gives the same output. `--delay` paces real calls and a 429 backs off automatically. `--record`
saves the responses as a fixture for the `fake` provider. `--sets development --limit 5` is a
small smoke test, which never touches held-out inputs.

[NOVELTY.md](NOVELTY.md) has the results and their limitations, including data provenance.
Do not tune on the held-out inputs. `python scripts/validate_paraphrases.py` checks the
paraphrase file's freeze and gold programs; `python scripts/demo.py --with-mutations` runs
the checked demo ([guide](docs/DEMO.md)).

---

## Project layout

```
src/parsley/
├── cli.py  pipeline.py  session.py  diagnostics.py  keywords.py
├── nlp/        normalizer, pattern table, candidates, context, ambiguity, suggestions
├── compiler/   AST nodes, IR builder, lexer, parser, semantic analysis, symbols, codegen
├── verify/     back-translation, round-trip, AST evaluator, interpreter
├── eval/       dataset, metrics, evaluation runner
├── llm/        optional model providers, prompt, validation, hybrid mode, response cache
└── web/        optional HTTP API for the frontend
tests/          unit/  integration/  fixtures/  fixtures_llm/  golden/  eval_data/
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
