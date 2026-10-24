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
