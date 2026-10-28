# Development Plan

Source of truth: plan v2.1, Section 6. Eight weeks, ten phases. Novelty work is spread
through the plan, not left to the end. If the deadline is shorter, compress Phases 3-5,
**never** Phases 6-8: those carry the novelty marks.

**Phase gate rule:** do not start a phase until the previous phase's exit test passes.

## Team

Final split. Current progress is in [Status](#status-2026-10-27).

| Member | Responsibility |
|---|---|
| **Core** | Merge `phase-2`; `ir_builder.py`, `keywords.py`; `symbols.py`, `semantic.py`, `session.py`; `codegen.py`, `backtranslate.py`, `pipeline.py`, `cli.py`; `context.py`, `ambiguity.py`, N1/N2 integration; verification integration; final integration and release |
| **Evaluation** | `ast_eval.py` (starts now); optional `parsley_ml`* (starts now, off the critical path); `metrics.py`, `run_eval.py`; mutation tests; ablation and results tables; results section of the report |
| **Parser/Verifier** | `lexer.py`, `parser.py`; `suggest.py`; `roundtrip.py`, `interpreter.py`; held-out paraphrase set (written blind, without looking at the pattern table); demo script |

\* **Optional learned scorer** (not part of plan v2.1, and not part of the novelty claim):
- It lives in a separate package, `parsley_ml/`, with its own `requirements-ml.txt`.
  Third-party libraries are allowed there, and only there (CLAUDE.md rule 7).
- Core code (`src/parsley/`) never imports it.
- It is off by default and plugs in only through the Candidate scoring interface
  (ARCHITECTURE.md 2.3); it may change `Candidate.score` and nothing else.
- It may start once the Candidate contract is frozen (ARCHITECTURE.md 2.3, frozen in Phase 1).

### Module ownership

| Module(s) | Owner | Status on this branch (2026-10-27) |
|---|---|---|
| `nlp/normalizer.py`, `patterns.py`, `candidates.py`, `context.py`, `ambiguity.py` | Core | Existing implementation, unchanged |
| `nlp/suggest.py` | Parser/Verifier | Implemented and tested; existing pipeline hook now active |
| `compiler/ast_nodes.py`, `ir_builder.py`, `keywords.py`, semantic analysis, symbols | Core | Existing implementation, unchanged |
| `compiler/lexer.py`, `parser.py` | Parser/Verifier | Inherited Phase 3 implementation validated; lexer uses the shared keyword owner |
| `compiler/codegen.py`, `verify/backtranslate.py`, `pipeline.py`, CLI, session | Core | Existing implementation, unchanged |
| `verify/roundtrip.py`, `verify/interpreter.py` | Parser/Verifier | Implemented, tested and hardened; V2/V3 active |
| `verify/ast_eval.py` | Evaluation | Existing implementation inherited from `phase-7-verifier`, unchanged |
| `eval/dataset.py`, `eval/metrics.py`, `eval/run_eval.py`, ablation, results | Evaluation | Done; results in NOVELTY.md (Results, Limitations) |
| `tests/eval_data/paraphrases.json` | Parser/Verifier | 15 groups / 60 inputs, frozen; gold validation passes |
| `scripts/demo.py`, `docs/DEMO.md` | Parser/Verifier | Runnable presentation, failure checks and actual transcript |
| Optional `parsley_ml/` | Evaluation | Not started; outside this contribution |

`ast_eval.py` (Evaluation) and `interpreter.py` (Parser/Verifier) have different authors on purpose,
so V3 does not share bugs between them.

### Workflow rule

**Each person works on a feature branch and merges into `main` via a pull request.** No
direct commits to `main`. Branch names: `phase-<n>[-<topic>]`, e.g. `phase-2`,
`phase-3-parser`.
A PR touching another owner's module, or any contract in ARCHITECTURE.md, needs that
owner's review.

## Phase overview

| Phase | Timing | Focus | Novelty | Owner(s) |
|---|---|---|---|---|
| 0 | Days 1-2 | Setup, repo, docs skeleton | - | Core |
| 1 | Week 1 | Language spec, data contracts, fixtures, related work | Ambiguous fixtures; NOVELTY.md | Core |
| 2 | Week 2 | NLP front end with scored candidates | Multi-candidate output (enables N2) | Core |
| 3 | Week 3 | AST, IR builder, lexer, parser | Parser reused by V2/V3 | Parser/Verifier (lexer, parser); Core (AST, IR builder, keywords) |
| 4 | Week 4 | Semantic analysis, symbol table, session | Symbol table exposed for N1 | Core |
| 5 | Week 5 | Code generation + back-translation + end-to-end CLI | N3-V1 | Core |
| 6 | Week 6 (first half) | Context resolver + ambiguity gate + suggestions | N1, N2, N4 | Core (context, ambiguity, N1/N2 integration); Parser/Verifier (suggest.py) |
| 7 | Week 6 (second half) - Week 7 | Verifier: round-trip + interpreter + execution equivalence | N3-V2, V3 | Parser/Verifier (roundtrip, interpreter); Evaluation (ast_eval, starts now; mutation tests); Core (verification integration) |
| 8 | Week 7 | Evaluation dataset, metrics, ablation | N5 | Evaluation (metrics, run_eval, ablation, results tables); Parser/Verifier (blind paraphrase set) |
| 9 | Week 8 | Hardening, docs, report, demo | Novelty demo script | Core (final integration, release); Evaluation (results section); Parser/Verifier (demo script) |

## Status (2026-10-28)

**The project is complete.** The evaluation runs with `python -m parsley.eval.run_eval`;
its results and limitations are in NOVELTY.md and the final report is `docs/REPORT.md`.
The evaluation includes a synthetic blind set (`tests/eval_data/synthetic_blind.json`,
written by the AI coding agent, not human-authored); no human-authored blind set was obtained.

| Phase | State |
|---|---|
| 0-2, 4-5 | Done. |
| 3 | Done. Lexer/parser checked against every valid fixture, precedence, all comparisons, nested blocks and malformed input. |
| 6 | Done. N1, N2 and N4 suggestions (ranked supported rewrites, block-splitting guidance). |
| 7 | Done. Real V2/V3 active in the pipeline; `ast_eval.py` and `interpreter.py` stay independent; test-only mutation tests. |
| 8 | Done. Frozen held-out set (168 inputs), every Section 8 metric, N1 and N2 ablations, failures by category, mutation detection by layer; synthetic blind set (25 cases). No human-authored blind set was obtained. |
| 9 | Done: demo script and transcript, documentation, final report (`docs/REPORT.md`, `docs/Parsley_Report.docx`). |

Details of the parser/verifier hand-off are in `docs/ASSIGNED_PHASES.md`.

### v1.1 (after vocabulary expansion; not used in the submitted paper/report)

After the submission, the English vocabulary was expanded (LANGUAGE_SPEC.md, "Changelog:
v1.1 vocabulary"): new phrasings mapped onto existing intents, with no grammar, AST or
MiniLang change. `write` was dropped because N4 would then suggest a rewrite of a `while`
loop. The report and NOVELTY.md keep the v1.0 numbers. Held-out set (168 inputs),
`python -m parsley.eval.run_eval`, 2026-10-28:

| Metric | v1.0 | v1.1 |
|---|---|---|
| exact-match accuracy, paraphrase | 46/60 (76.7%) | 47/60 (78.3%) |
| exact-match accuracy, session | 58/58 (100.0%) | 58/58 (100.0%) |
| exact-match accuracy, all with gold code | 104/118 (88.1%) | 105/118 (89.0%) |
| whole-session exact match | 10/10 (100.0%) | 10/10 (100.0%) |
| paraphrase consistency (same AST) | 1/15 (6.7%) | 2/15 (13.3%) |
| paraphrase consistency (gold AST) | 1/15 (6.7%) | 2/15 (13.3%) |
| ambiguity precision | 25/25 (100.0%) | 25/25 (100.0%) |
| ambiguity recall | 25/25 (100.0%) | 25/25 (100.0%) |
| unnecessary-question rate | 0/118 (0.0%) | 0/118 (0.0%) |
| context-resolution accuracy | 92/102 (90.2%) | 93/102 (91.2%) |
| safe-rejection rate | 25/25 (100.0%) | 25/25 (100.0%) |
| suggestion usefulness | 0/13 (0.0%) | 0/11 (0.0%) |
| wrong-code rate | 0/168 (0.0%) | 0/168 (0.0%) |
| crashes | 0/168 (0.0%) | 0/168 (0.0%) |

Ablations in v1.1: context_off 38/118 exact match (unchanged; -56.8 pp from the v1.1
baseline); forced_top1 wrong code 11/168 (6.5%) and ambiguity recall 14/25, both unchanged.
Paraphrase failures: 13 rejected and 1 error in v1.0; 11 rejected and 2 errors in v1.1 (one
input moved from rejected to a semantic error, still not wrong code). The synthetic blind
set and the development fixtures score the same as in v1.0.

---

## Phase 0 - Setup (Days 1-2)

**Goal:** A clean repository that installs and runs an empty test suite from the README
alone.

Steps: create the repo and the Section 5 folder structure (empty modules with docstrings);
create a virtual environment, `requirements.txt` (only `pytest>=8,<9`) and `pyproject.toml`
(package metadata and pytest config); write a placeholder `cli.py` that echoes input and
exits 0; add one trivial passing test and commit; create the doc files with headings.

| Deliverable | Exit test |
|---|---|
| Runnable skeleton, doc headings, first commit | Fresh clone -> install -> `python -m pytest -q` passes; CLI starts |

## Phase 1 - Lock the language and contracts (Week 1)

**Goal:** Every later component has a fixed target: grammar, types, English patterns, data
contracts and fixtures.

Steps: write LANGUAGE_SPEC.md (grammar, types, identifier rules, error behaviour); list
supported English patterns per intent (3-5 phrasings each) and the rejected patterns; write
the ambiguity rules; freeze the data contracts in ARCHITECTURE.md; create fixtures (at least
20 valid, 10 invalid, 10 ambiguous); write NOVELTY.md with 3-5 related-work citations and a
"what we do not claim" list.

| Deliverable | Exit test |
|---|---|
| Frozen spec, contracts, 40+ fixtures, NOVELTY.md draft | Team agrees the spec is frozen (done 2026-10-25; LANGUAGE_SPEC.md Section 9 decision log); fixtures saved in `tests/fixtures` (the source of truth; `examples/` gets runnable sessions in Phase 5) |

## Phase 2 - NLP front end (scored candidates) (Week 2)

**Goal:** Turn normalized English into zero or more scored candidate intents.

Steps: normalizer (lowercased copy for matching only; identifiers and quoted text keep
their case; collapse spaces; strip trailing punctuation; map synonyms); data-driven pattern
table in `patterns.py`; slot extraction (identifiers, numbers, optionally number words 0-20,
quoted strings, operators, condition and body clauses); a candidate generator that returns
every match with a score and does not pick one yet; status `unsupported` when nothing
matches, with no exceptions escaping; unit tests.

| Deliverable | Exit test |
|---|---|
| `normalizer.py`, `patterns.py`, `candidates.py` with tests | All valid fixtures map to the right intent + slots; invalid ones fail cleanly |

## Phase 3 - AST, IR builder, lexer, parser (Week 3)

**Goal:** A typed program representation, and an independent MiniLang parser for
verification.

Steps: frozen, comparable AST dataclasses (`Program, Let, Assign, Print, If, Repeat, BinOp,
Compare, Num, Str, Var`, plus `Neg` for unary minus; **already implemented** in
`ast_nodes.py` so the parser can build against it); IR builder (Candidate -> AST, one function per intent); lexer with
line/column errors; recursive-descent parser with correct precedence; tests (every
expected-MiniLang fixture parses; malformed MiniLang returns errors and never crashes).

| Deliverable | Exit test |
|---|---|
| `ast_nodes.py`, `ir_builder.py`, `lexer.py`, `parser.py` with tests | Every valid fixture: English -> AST matches `parse(expected MiniLang)` |

## Phase 4 - Semantic analysis, symbol table, session (Week 4)

**Goal:** Catch meaning errors and keep program state across sentences.

Steps: `symbols.py` (name, inferred type, declaring statement); `semantic.py` (undefined
variable `E201`, `LET` inside a block `E202`, redeclaration warning, type mismatch including
string operations other than `+`/`==`/`!=`, division by literal zero, REPEAT count outside
1-1000); plain-English diagnostics with stage and code; `session.py` (symbol
table, reference stack, history); a read-only symbol-table view for the context resolver;
positive and negative tests.

| Deliverable | Exit test |
|---|---|
| `semantic.py`, `symbols.py`, `session.py` with tests | All semantic fixtures produce the expected diagnostics; valid programs produce none |

## Phase 5 - Code generation, back-translation, end-to-end CLI (Week 5)

**Goal:** A working English -> MiniLang pipeline with the first verification layer.

Steps: `codegen.py` (one template per AST node, canonical format from LANGUAGE_SPEC.md 2.1);
`backtranslate.py` (V1, one English template per node); `pipeline.py` (normalize ->
candidates (top for now) -> AST -> semantic -> codegen -> back-translate); CLI (single
sentence, file mode, `--trace`, `--output`, REPL, `--confirm`); golden tests.

| Deliverable | Exit test |
|---|---|
| Working CLI with trace and back-translation | All golden tests pass; errors exit non-zero without printing fake success |

## Phase 6 - Context resolver, ambiguity gate, suggestions (Week 6, first half)

**Goal:** Implement the headline novelty N1, plus N2 and N4. Prioritize this over any extra
language features.

Steps: `context.py` (bare words vs. symbol table, operator operands as identifiers, pronouns
via the reference stack, implicit LET with warning, near-miss names -> confirmation using the
length-scaled distance and common-word list in LANGUAGE_SPEC.md §4, type hints); context
re-scoring; `ambiguity.py` (score-margin threshold, missing-slot checks, template questions;
`and ...` block continuations are rejected, not clarified);
REPL clarification loop (diagnostic in file mode); `suggest.py` (token overlap + edit
distance over the pattern templates); tests, including the `--no-context` ablation switch.

| Deliverable | Exit test |
|---|---|
| `context.py`, `ambiguity.py`, `suggest.py`; REPL clarification loop | All ambiguous and context fixtures pass; `--no-context` switch works |

## Phase 7 - Layered verifier (Week 6 second half - Week 7)

**Goal:** Implement V2 and V3 so every accepted statement is checked three ways.

Steps: `roundtrip.py` (V2: re-parse, dataclass equality, report the first differing node);
`ast_eval.py` (evaluate the AST directly); `interpreter.py` (parse MiniLang and walk the
parsed tree; separate file and author); V3 on the whole session program (compare final
variables and printed output, REPEAT capped); verification summary in the trace; mutation
tests (test-only hooks: swap operators, drop statements, change literals, alter precedence).

| Deliverable | Exit test |
|---|---|
| `verify/` package; verification shown in trace; mutation tests | All valid fixtures pass V2 and V3; the mutation suite reports which mutations each layer catches |

## Phase 8 - Evaluation and ablation (Week 7)

**Goal:** Turn features into measured evidence (N5).

Steps: build the held-out evaluation set (NOVELTY.md metrics section), with paraphrases
written blind to the pattern table; `run_eval.py` computes all metrics and writes a CSV and a
summary table; ablations (context ON vs. OFF; clarification ON vs. OFF, forced top-1); record
and categorize failures honestly; fix only clear bugs and never tune on the evaluation set.

| Deliverable | Exit test |
|---|---|
| Results table, ablation table, failure analysis | `run_eval.py` reproduces the same numbers from a clean clone |

## Phase 9 - Hardening, documentation, report, demo (Week 8)

**Goal:** A reproducible, well-explained submission.

Steps: a regression test for every bug found, and no crash on any fixture or random
sentence; make README, LANGUAGE_SPEC, ARCHITECTURE, TESTING and NOVELTY match the
implementation; write the report; prepare and rehearse the demo script, with a recorded
backup; optional only if everything else is done: a minimal GUI or Python backend.

| Deliverable | Exit test |
|---|---|
| Final repo, report, demo script, recording | Another person reproduces install, tests, eval and demo from the README alone |

## Risks

| Risk | Mitigation |
|---|---|
| Novelty slips because core takes longer | Phase 6 has priority over extra grammar. If behind, drop REPEAT and ELSE before dropping N1/N2. |
| Too many clarification questions annoy users | Measure the unnecessary-question rate; tune the score margin; auto-resolve when the symbol table decides it. |
| ast_eval and interpreter share a bug (V3 blind spot) | Separate files and authors; the interpreter works on parsed MiniLang, not the original AST. |
| Evaluation set leaks into tuning | Write it after Phase 7, by a teammate, and freeze it before running. |
| Infinite loop in REPEAT during V3 | REPEAT count must be a literal; cap at e.g. 1000; timeout guard. |
| Coding agent changes the spec silently | CLAUDE.md rules; review diffs to LANGUAGE_SPEC.md manually. |
| Deadline shorter than 8 weeks (not stated) | Confirm the date now. Compress Phases 3-5; keep 6-8. |
