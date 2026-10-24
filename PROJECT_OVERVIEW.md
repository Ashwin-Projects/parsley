# Project Overview

## Problem

English-to-code systems usually pass information one way, from the language model to the
code, and output a single guess. That causes three problems:

1. **Hidden ambiguity.** `print hello world` should print text, but `print age` should
   print a variable. Only the compiler knows whether `age` was declared. That is a
   symbol-table fact, not a language fact, and one-way pipelines never ask the compiler.
2. **Silent guessing.** `increase x` (by how much?) and `set x to 10 or 20` (which?) get
   guessed instead of asked.
3. **Unverified output.** Checking generated code against its own parser (round-trip)
   only catches printer bugs. It cannot see the most likely error: the English was
   misunderstood.

## Goals

- Translate a constrained, documented subset of English into MiniLang, a small formally
  specified language (LANGUAGE_SPEC.md).
- Use the compiler's symbol table and statement history to resolve English ambiguity (N1).
- Return ranked candidates and accept, clarify or reject, never guess silently (N2). Suggest a
  supported phrasing for rejected input (N4).
- Verify every accepted statement three ways: back-translation, structural round-trip,
  execution equivalence (N3).
- Measure all of this on a held-out set, with an ablation (N5).
- Stay deterministic, offline and reproducible: Python standard library plus pytest.

## Non-goals

- Unconstrained English, or a general-purpose language model front end. An LLM could plug
  into the candidate interface later, but it is out of scope.
- MiniLang features beyond the spec: no functions, lists, user input, `while` loops, or
  booleans as values.
- Claiming that NL-to-code, clarification, back-translation or round-trip are new on their
  own (NOVELTY.md, "What we do NOT claim").
- Proving that an interpretation is correct. Verification checks against defined checks.
- Paid APIs, network access, or heavy dependencies.
- A GUI or web backend (optional, Phase 9, only if everything else is done).

## Success criteria (definition of done)

| Requirement | Acceptance target |
|---|---|
| Core translation | At least 6 intents (declare, assign, inc/dec, print, if, repeat) with documented English patterns |
| Compiler concepts | Lexer, recursive-descent parser, typed AST, symbol table, semantic diagnostics, AST-based codegen |
| N1 context | Pronouns, variable vs. string, implicit declaration, typo confirmation, with a `--no-context` ablation switch |
| N2 ambiguity | Ranked candidates, accept/clarify/reject, REPL clarification loop |
| N3 verification | Back-translation, re-parse comparison, execution equivalence, mutation test results |
| N4 suggestions | Nearest supported phrasing for rejected input |
| N5 evaluation | Held-out set, all metrics, ablation table, failure analysis |
| Reproducibility | Clean clone -> install -> tests -> eval -> demo, from the README only |
