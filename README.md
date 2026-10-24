# Parsley

A context-aware, self-verifying compiler from constrained English to **MiniLang**, a small,
formally specified language. Python 3.11+, standard library only (pytest for tests).

## Goal

Translate English such as `make a variable called score and set it to 10` into MiniLang
(`LET score = 10;`) in a way that is checked rather than trusted. Three ideas carry this:

- **Compiler-informed interpretation (N1).** The compiler's symbol table feeds back into
  the English stage: `print age` prints the variable `age` only if it was declared;
  `add 5 to it` resolves `it`; `print scroe` asks `Did you mean the variable score?`.
- **Explicit ambiguity handling (N2).** Ranked candidates, then accept / clarify / reject.
  Rejected input gets a supported phrasing as a suggestion (N4).
- **Layered verification (N3).** Back-translation to English, AST round-trip, and execution
  equivalence with two independent evaluators. Evaluated with metrics and an ablation (N5).

See [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) and [NOVELTY.md](NOVELTY.md).

## Setup

```
git clone https://github.com/Ashwin-Projects/parsley.git
cd parsley
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run

```
python -m pytest -q                       # run the test suite
python -m parsley.cli "set age to 21"     # CLI (Phase 0 placeholder: echoes its input)
parsley "set age to 21"                   # same, via the installed entry point
```

The full CLI (file mode, `--trace`, `--output`, REPL, `--confirm`, `--no-context`) arrives
in Phases 5-6.

## Status

| Phase | State |
|---|---|
| 0 - Setup | Done: skeleton, packaging, placeholder CLI, smoke test |
| 1 - Spec, contracts, fixtures, related work | Draft done; **awaiting team freeze** (see LANGUAGE_SPEC.md Section 9) |
| 2-9 | Not started |

No compiler logic exists yet. Every module under `src/parsley/` is a docstring-only stub.

## Documentation

| File | Contents |
|---|---|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Problem, goals, non-goals, success criteria |
| [LANGUAGE_SPEC.md](LANGUAGE_SPEC.md) | Grammar, types, English patterns, ambiguity rules |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline and frozen data contracts |
| [NOVELTY.md](NOVELTY.md) | N1-N5, non-claims, metrics, related work |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Phases 0-9, exit tests, team, branch/PR workflow |
| [TESTING.md](TESTING.md) | Test layout, ownership, fixture format |
| [CLAUDE.md](CLAUDE.md) | Rules for the coding agent |

## Team

| Member | Responsibility |
|---|---|
| ASUS | Core + integration (Phases 0, 1, 2, 4, 5, 6) |
| Gaming | Evaluation, ablation, AST evaluator, mutation tests, optional learned scorer |
| MacBook | Lexer, parser, interpreter, round-trip compare, suggestions, demo |

Each person works on a feature branch and merges via pull request (see DEVELOPMENT.md).
