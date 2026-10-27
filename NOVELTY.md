# Novelty and Original Contribution

Source of truth: plan v2.1, Sections 1, 2, 8 and 9.

## Statement

Translating natural language into code, and into domain-specific languages, is an
established area. Parsley does not claim to be the first such system. Its contribution is
a **context-aware, self-verifying translation pipeline for a formally specified
mini-language**, built on three ideas:

1. **Compiler-informed interpretation.** Information flows back from the compiler to the
   language-understanding stage. The symbol table and statement history are used to
   resolve references such as "it", to decide whether a word denotes a declared variable or
   literal text, to detect likely misspelled identifiers, and to apply type constraints when
   ranking interpretations.
2. **Explicit ambiguity handling.** The front end produces ranked candidate
   interpretations rather than a single guess. A decision rule accepts, asks a targeted
   clarification question, or rejects with a suggested supported phrasing.
3. **Layered verification.** Each accepted statement is checked three ways. It is
   back-translated into canonical English so the user can confirm the interpretation. It is
   re-parsed to check structural consistency with the intended syntax tree. And it is
   executed by two independent evaluators to check behavioural equivalence.

The contribution is evaluated on a held-out set of valid, paraphrased, multi-sentence,
ambiguous and unsupported inputs. This includes an ablation that measures the effect of
compiler-informed interpretation and clarification, and mutation tests that measure which
verification layer detects which class of generation error.

## The novelty package (N1-N5)

N1-N3 are core (must ship), N4 is core-light, and N5 is the evidence. All are
deterministic, use no paid API, and are built with the standard library only.

| Id | Feature | Phase | Module(s) |
|---|---|---|---|
| **N1** | Compiler-informed interpretation (headline): variable vs. text (operands of operator words are identifiers, so undeclared ones report E201), pronouns, implicit declaration, typo confirmation (length-scaled edit distance, never on common English words), type-aware wording | 6 (inputs from 4) | `nlp/context.py` |
| **N2** | Ambiguity detection and clarification dialogue: accept / clarify / reject; REPL loop; diagnostics in file mode. Sources: missing values, alternatives, likely typos, operator scope. (`and ...` block continuations are rejected, not clarified: MVP blocks hold one statement.) | 2 (multi-candidate output), 6 | `nlp/candidates.py`, `nlp/ambiguity.py` |
| **N3** | Two-way, three-layer verification: V1 back-translation (core), V2 structural round-trip (supporting), V3 execution equivalence (core-light) | 5 (V1), 7 (V2, V3) | `verify/` |
| **N4** | "Did you mean" recovery: nearest supported pattern for rejected input | 6 | `nlp/suggest.py` |
| **N5** | Measured evaluation: held-out set, metrics, ablation, failure analysis | 8 | `eval/` |

### Why the layering matters

V2 alone only checks the compiler against itself: with AST-based codegen it fails only on
printer or parser bugs. V1 checks the compiler against the user's intent, and V3 checks
meaning, not just shape. We describe this as **verification against defined checks, never
as proof** that every English interpretation is correct.

| Layer | Catches | Cannot catch |
|---|---|---|
| V1 Back-translation | NLP misinterpretation (invisible to round-trip) | Errors the user does not notice |
| V2 Structural round-trip | Code generator / printer bugs, grammar drift | Interpretation errors |
| V3 Execution equivalence | Code that parses but means something else (e.g. wrong precedence) | The same bug in both evaluators (so they are kept independent) |

## What we do NOT claim

- That NL-to-code or NL-to-DSL translation is new.
- That clarification questions, back-translation or round-trip testing are new
  individually. Each exists in research and tools.
- That structural round-trip (V2) is a strong check on its own. It is a supporting layer.
- That verification **proves** an interpretation correct. It checks against defined
  checks and lets the user confirm.
- Coverage of unconstrained English. Input is constrained English; pattern coverage
  limits paraphrase handling.
- Any language features beyond the spec: no functions, lists or user input in MiniLang.
- Any percentage in advance. We report the measured numbers, including failures.
- Anything from the optional learned scorer (`parsley_ml/`). It is off by default, outside the
  core, and not part of the contribution; all headline numbers are reported with it off.

The defensible claim is the **specific combination**: a compiler symbol table feeding back
into English interpretation, explicit ambiguity handling, and layered verification inside a
formally specified mini-language, with measured results.

## Metrics (Section 8)

Held-out set of about 150 inputs, kept separate from development fixtures, written after
Phase 7 by a teammate and frozen before running.

| Subset | Size | Content |
|---|---|---|
| Valid single statements | ~50 | All intents, canonical phrasing |
| Paraphrase groups | ~15 groups x 3-4 | Same meaning, different wording, written blind |
| Multi-sentence sessions | ~10 sessions | Pronouns, variable vs. string, implicit declaration |
| Ambiguous | ~25 | Missing slots, alternatives, operator scope, name overlap |
| Invalid / unsupported | ~25 | Out-of-scope requests, malformed input, semantic errors |

| Metric | Definition | Supports |
|---|---|---|
| Exact-match accuracy | Generated MiniLang equals expected, on valid + session subsets | Core translation |
| Paraphrase consistency | Share of paraphrase groups where all members produce the same AST | NLP robustness |
| Ambiguity precision / recall | Of clarifications asked, how many were truly ambiguous / of truly ambiguous inputs, how many were caught | N2 |
| Unnecessary-question rate | Clarifications asked on clearly unambiguous input | N2 usability |
| Context resolution accuracy | Correct pronoun / variable-vs-string / typo handling in sessions | N1 |
| Safe rejection rate | Unsupported inputs rejected without crash or wrong code | Reliability |
| Suggestion usefulness | Share of rejected inputs where the top suggestion matches the intended meaning (manually judged) | N4 |
| Mutation detection by layer | Fraction of injected generation bugs caught by V2, V3, and combined | N3 |
| Ablation deltas | Accuracy with N1 off vs. on; wrong-code rate with N2 off (forced guess) vs. on | Proof that N1/N2 matter |

Honesty rule: the report shows failures too.

## Results (2026-10-27)

From `python -m parsley.eval.run_eval` on the frozen held-out set: 168 inputs (60
paraphrases in 15 groups, 25 ambiguous, 25 unsupported, 58 sentences in 10 sessions). The run is
deterministic; `results/summary.md` has every table and the SHA-256 of each data file.
Baseline: exact match 104/118 (88.1%), wrong code 0/168, crashes 0/168, unnecessary questions
0/118, safe rejection 25/25, ambiguity precision 25/25 and recall 25/25.

**N1 ablation (context resolution off for the evaluated sentence; setup unchanged).**

| Measure | N1 on | N1 off |
|---|---|---|
| Exact-match accuracy | 104/118 (88.1%) | 38/118 (32.2%) |
| Context-resolution accuracy | 92/102 (90.2%) | 26/102 (25.5%) |

**N2 ablation (no questions: each one answered with its top-ranked option).** Wrong code rises
from 0/168 to 11/168 (6.5%): every guess on 5 alternatives, 3 typos and 3 operator-scope
inputs (e.g. `set queueLimit to 14 or 28` silently becomes `queueLimit = 14;`). Questions
with nothing to guess from (a missing value) still stop, so recall falls to 14/25 rather
than 0.

**N3 mutation detection by layer.** 188 test-only code-generation mutants of the held-out
gold programs (last statement), checked with the real layers:

| Layer | Caught |
|---|---|
| V2 (re-parse + AST compare) | 188/188 (100.0%) |
| V3 (AST evaluator vs. interpreter) | 173/188 (92.0%) |
| V2 or V3 | 188/188 (100.0%) |

V3 misses mutants that do not change final state or output: 9 of 17 operand swaps
(`visits + 3` vs. `3 + visits`), 3 literal, 1 comparison, 1 string and 1 variable change.

**Synthetic blind set.** 25 cases scored 19/19 exact match, ambiguity recall 3/3 and safe
rejection 3/3, with no wrong code (`results/summary.md`). Provenance: synthetic, written by the
AI coding agent that helped build this system and not independently human-authored, so it is
weak evidence; no human-authored blind set was obtained.

## Limitations

- **Paraphrase consistency is 1/15 groups** (all members giving the same AST, and the gold
  AST). In 13 groups the deliberately out-of-coverage phrasing (e.g. `quadruple subtotal`,
  `bump visits up by 3`) is rejected, and `set flag to 1 provided pressure does not exceed 8`
  ends in a semantic error. Per input, 46/60 (76.7%) paraphrases match.
- **N4 suggestion usefulness is 0/13.** For none of the 13 rejected paraphrases with a known
  meaning did N4 offer a suggestion. Usefulness is judged automatically (the suggestion must
  compile to the gold code), not manually as planned.
- **V3 added no detections beyond V2 on this mutation set.** Every mutant V3 caught, V2 also
  caught (173 both, 15 V2 only, 0 V3 only). The set has no mutant that V2 misses, so it does
  not show what V3 adds; V3's purpose is bugs that a shared parser and code generator would
  hide from V2, and none are modelled here.
- **Data provenance.** The ambiguous, unsupported and session subsets were AI-written in this
  repository by an author with compiler-integration and development-fixture context, so they
  may share the system's phrasing; read their perfect scores with that in mind. The paraphrase
  set was written before its author saw the pattern table and is the stronger evidence, but it
  is also AI-assisted and not independently human-reviewed. An optional
  `tests/eval_data/human_blind.json` (format in TESTING.md) is reported in its own section.
- **Gaps against the plan.** There is no held-out subset of ~50 valid single statements (the
  paraphrases stand in), and held-out unsupported inputs include no semantic errors.
- The sets are small (168 inputs, one deterministic run), so the numbers have wide
  uncertainty; no confidence intervals are reported.

## Related work

All five entries were found with the paper-search tool (OpenAlex) and their DOIs were
checked to resolve, on 2026-10-25. Each line says how Parsley differs.

1. **Desai, A., Gulwani, S., Hingorani, V., et al. (2016). Program synthesis using natural
   language.** *Proceedings of the 38th International Conference on Software Engineering
   (ICSE).* <https://doi.org/10.1145/2884781.2884786>
   *NL-to-DSL.* A general framework that maps English into DSL programs using a ranked set of
   candidate programs. Parsley shares the "ranked candidates into a small DSL" idea, but adds
   symbol-table feedback, explicit clarification, and layered verification of the chosen
   candidate.
2. **Austin, J., Odena, A., Nye, M., et al. (2021). Program Synthesis with Large Language
   Models.** *arXiv.* <https://doi.org/10.48550/arxiv.2108.07732>
   *NL-to-code (general-purpose).* Benchmarks large language models on short Python tasks,
   checked by executing test cases. It is the neural, open-ended end of the field. Parsley is
   deterministic and constrained, and uses execution (V3) as a self-check rather than as a
   benchmark oracle.
3. **Yao, Z., Su, Y., Sun, H., Yih, W. (2019). Model-based Interactive Semantic Parsing: A Unified
   Framework and A Text-to-SQL Case Study.** *EMNLP-IJCNLP 2019.*
   <https://doi.org/10.18653/v1/d19-1547>
   *Clarification in semantic parsing.* The parser asks the user questions when it is
   uncertain. Parsley's N2 follows the same principle. The difference is that our
   uncertainty signals include compiler facts (declared names, types, edit distance to
   declared names), not only model confidence.
4. **Li, H.-S., Mesgar, M., Martins, A. F. T., Gurevych, I. (2023). Python Code Generation by
   Asking Clarification Questions.** *ACL 2023 (Long Papers).*
   <https://doi.org/10.18653/v1/2023.acl-long.799>
   *Clarification for NL-to-code.* Shows that under-specified NL descriptions can be resolved
   by asking clarification questions before generating code. Parsley applies this to a formal
   mini-language with templated, slot-targeted questions and a measured
   unnecessary-question rate.
5. **Suhr, A., Iyer, S., Artzi, Y. (2018). Learning to Map Context-Dependent Sentences to
   Executable Formal Queries.** *NAACL-HLT 2018.* <https://doi.org/10.18653/v1/n18-1203>
   *Context across utterances.* Interprets each sentence using the interaction history.
   Parsley's N1 uses history too, but through an explicit compiler data structure (the
   symbol table and reference stack) with deterministic rules that an ablation can switch
   off (`--no-context`).

Author lists were checked against OpenAlex records. Entries 1 and 2 have 8 and 11 authors
respectively, shortened here to "et al.".
