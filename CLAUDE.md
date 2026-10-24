# CLAUDE.md - permanent rules for the coding agent

Project: Parsley, an English-to-MiniLang compiler. The plan PDF
(`Clarix_NL_MiniLang_Compiler_Plan_Final.pdf`, "Clarix" = Parsley) is the source of truth.

```
1. Read README, DEVELOPMENT, LANGUAGE_SPEC, ARCHITECTURE and NOVELTY
   before any change.
2. Implement only the requested phase/step; list every changed file.
3. Keep module boundaries: NLP never emits MiniLang text;
   only semantic.py writes the symbol table.
4. Never expand grammar or English patterns without updating
   LANGUAGE_SPEC.md and tests together.
5. Keep ast_eval.py and interpreter.py independent; do not share evaluation code.
6. Mutation/corruption hooks exist only under tests/; never in the runtime pipeline.
7. Standard library only, plus pytest. No APIs, secrets or heavy
   dependencies without approval.
8. Add a test for every new behaviour and bug fix. Run tests;
   report the exact command and output.
9. Never claim tests passed unless they were run.
```

Use /superpowers:test-driven-development for every code phase and /ecc:python-review before finishing a phase.
