# Architecture

Source of truth: plan v2.1, Section 3. Novel stages are marked `[N]`. Arrows going up are
the feedback paths that make N1 work.

## 1. Pipeline

```
 English sentence
       |
 [A] Normalizer ............ keywords matched in lowercase; identifier case kept
       |
 [B] Candidate generator ... pattern rules -> 0..k candidate intents, each with slots + score
       |            ^
       |            |  [N1] Context resolver: symbol table + reference stack
       |            |       (variable vs string, 'it', typos, implicit declare)
       v            |
 [C] Ambiguity gate [N2] -- accept --> continue
       |         \-- clarify --> ask user / emit diagnostic --> re-enter at [B]
       |          \-- reject  --> [N4] nearest-pattern suggestion
       v
 [D] IR / AST builder (typed nodes)
       |
 [E] Semantic analyzer + symbol table  ----------------------------^ (feeds N1)
       |
 [F] Code generator (AST -> MiniLang text)
       |
 [G] Verifier [N3]:  V1 back-translation | V2 re-parse + AST compare | V3 execution equivalence
       |
 [H] Trace / output:  input, normalized text, candidates + scores, decision,
                      AST, checks, back-translation, MiniLang, verification result
```

### Stage -> module map

| Stage | Module(s) | Phase |
|---|---|---|
| [A] Normalizer | `parsley/nlp/normalizer.py` | 2 |
| [B] Candidate generator | `parsley/nlp/patterns.py`, `parsley/nlp/candidates.py` | 2 |
| [N1] Context resolver | `parsley/nlp/context.py` | 6 |
| [C] Ambiguity gate [N2] | `parsley/nlp/ambiguity.py` | 6 |
| [N4] Suggestions | `parsley/nlp/suggest.py` | 6 |
| [D] IR / AST builder | `parsley/compiler/ast_nodes.py`, `parsley/compiler/ir_builder.py` | 3 |
| Parser for V2/V3 | `parsley/compiler/lexer.py`, `parsley/compiler/parser.py` | 3 |
| [E] Semantic analyzer | `parsley/compiler/semantic.py`, `parsley/compiler/symbols.py`, `parsley/session.py` | 4 |
| [F] Code generator | `parsley/compiler/codegen.py` | 5 |
| [G] Verifier V1 | `parsley/verify/backtranslate.py` | 5 |
| [G] Verifier V2 | `parsley/verify/roundtrip.py` | 7 |
| [G] Verifier V3 | `parsley/verify/ast_eval.py`, `parsley/verify/interpreter.py` | 7 |
| [H] Trace / output | `parsley/pipeline.py`, `parsley/cli.py`, `parsley/diagnostics.py` | 5 |
| [N5] Evaluation | `parsley/eval/` | 8 |

## 2. Data contracts (frozen in Phase 1)

### 2.1 Authority and change protocol

- **This section is the single authoritative definition** of every cross-stage payload.
  Code mirrors it; it never redefines it. If code and this file disagree, the code is wrong.
- The plan's notation is reproduced verbatim first (2.2). Sections 2.3-2.8 pin down the
  details the plan leaves implicit (value ranges, nullability, enums, slot shapes).
  They do not add or remove fields.
- **Change protocol** (no exceptions): (1) open a PR that edits this file first, saying
  which consumers are affected; (2) the owners of every affected module approve it;
  (3) update the code and tests in the same or a following PR. Never change an
  implementation first and update the contract afterward.
- Python representation: frozen `@dataclass`es (standard library only). The defining module
  for each contract is listed in its section; other modules import it from there.

### 2.2 Plan notation (verbatim)

```
Candidate   = { intent: str, slots: dict, score: float, rule_id: str, notes: [str] }
NLPResult   = { status: "ok" | "ambiguous" | "unsupported",
                candidates: [Candidate], question: str | None, suggestion: str | None }
Diagnostic  = { level: "error" | "warning" | "info", stage: str, code: str, message: str }
Verification= { back_translation: str, v2_match: bool, v3_match: bool | None, details: [str] }
Session     = { symbol_table: {name: {type, declared_at}}, ref_stack: [name], history: [Stmt] }
```

### 2.3 Candidate

Defined in `parsley/nlp/candidates.py`. Producer: candidate generator [B]; re-scored by
the context resolver [N1]. Consumers: ambiguity gate [C], IR builder [D], trace [H],
evaluation [N5].

| Field | Type | Required | Semantics |
|---|---|---|---|
| `intent` | `str` | yes | One of `declare`, `assign`, `increment`, `decrement`, `multiply`, `divide`, `print`, `if`, `repeat` (LANGUAGE_SPEC.md Section 6). |
| `slots` | `dict[str, Slot \| None]` | yes | Keys fixed per intent (table below). `None` = required slot missing from the English, which triggers CLARIFY. |
| `score` | `float` | yes | In `[0.0, 1.0]`; higher is better. Computed in Phase 2, re-scored in Phase 6. |
| `rule_id` | `str` | yes | Stable pattern id from LANGUAGE_SPEC.md (`D1`, `INC2`, ...). |
| `notes` | `list[str]` | yes (may be empty) | Human-readable notes for the trace, e.g. implicit declaration. Never MiniLang text. |

Slot keys per intent:

| Intent | Slot keys |
|---|---|
| `declare`, `assign` | `name`, `value` |
| `increment`, `decrement`, `multiply`, `divide` | `name`, `amount` |
| `print` | `value` |
| `if` | `condition`, `then`, `else` (`else` absent for IF1) |
| `repeat` | `count`, `body` |

`Slot` shapes (plain dicts, tagged by `kind`). The NLP never emits MiniLang text; these
describe meaning, not code:

| `kind` | Other keys | Meaning |
|---|---|---|
| `number` | `text: str` | Number literal exactly as written (`"2.5"`). |
| `string` | `text: str`, `quoted: bool` | Literal text, from quotes or from variable-vs-text rule 3. |
| `word` | `text: str` | Unresolved bare word(s); the context resolver turns it into `name` or `string`. |
| `name` | `text: str` | Resolved identifier (declared variable, or assignment target). |
| `pronoun` | `text: str` | Unresolved `it` / `that` / `the variable`. |
| `binop` | `op: "+"\|"-"\|"*"\|"/"`, `left: Slot`, `right: Slot` | Arithmetic value. |
| `neg` | `operand: Slot` | Unary minus (`negative 5`, `-5`). |
| `condition` | `op: ">"\|"<"\|"=="\|">="\|"<="\|"!="`, `left: Slot`, `right: Slot` | `if` condition. |
| `statement` | `intent: str`, `slots: dict` | Nested block body (`then`, `else`, `body`). |
| `count` | `text: str` | `repeat` count as written. |

After the context resolver runs on an accepted candidate, no `word` or `pronoun` slot
remains.

**Scoring interface.** `score` is the only field an external scorer may change. The
optional learned scorer (`parsley_ml/`, DEVELOPMENT.md) plugs in through the scorer hook
defined in `candidates.py` in Phase 2: it takes candidates and returns new scores, and
never adds, removes or edits candidates. Core code never imports `parsley_ml`. The scorer
is off by default; with it off, the rule-based score is used.

### 2.4 NLPResult

Defined in `parsley/nlp/candidates.py`. Producers: candidate generator (sets
`unsupported` when nothing matches) and ambiguity gate (final status). Consumers:
pipeline, REPL/CLI, evaluation.

| Field | Type | Semantics |
|---|---|---|
| `status` | `"ok" \| "ambiguous" \| "unsupported"` | Maps to gate decision ACCEPT / CLARIFY / REJECT. |
| `candidates` | `list[Candidate]` | Sorted by `score`, descending. Empty iff `unsupported`. |
| `question` | `str \| None` | Non-null iff `status == "ambiguous"`; text from LANGUAGE_SPEC.md Section 7.1. |
| `suggestion` | `str \| None` | Only for `unsupported`; an N4 example phrasing, or `None` when nothing is close. |

### 2.5 Diagnostic

Defined in `parsley/diagnostics.py`. Every stage may produce it; no exception escapes a
stage (design rule 1).

| Field | Type | Semantics |
|---|---|---|
| `level` | `"error" \| "warning" \| "info"` | Any `error` makes the CLI exit non-zero. |
| `stage` | `str` | One of `normalizer`, `candidates`, `context`, `ambiguity`, `ir`, `lexer`, `parser`, `semantic`, `codegen`, `verify`, `cli`. |
| `code` | `str` | Letter (`E`/`W`/`I`, matching `level`) + 3 digits. `E201` = used before it is created; `E202` = `LET` inside a block (LANGUAGE_SPEC.md 2.2). Other codes are assigned in Phase 4. |
| `message` | `str` | Plain English, user-facing. |

### 2.6 Verification

Defined in `parsley/verify/__init__.py`. Producer: verifier [G]. Consumers: trace,
evaluation.

| Field | Type | Semantics |
|---|---|---|
| `back_translation` | `str` | V1 canonical English, e.g. `create variable age with value 20.` Always present for accepted statements. |
| `v2_match` | `bool` | V2: re-parsed AST equals the original AST (dataclass equality). |
| `v3_match` | `bool \| None` | V3: final variable state and printed output agree. `None` = V3 not run. |
| `details` | `list[str]` | Human-readable notes, e.g. the first differing node on a V2 mismatch. |

### 2.7 Session

Defined in `parsley/session.py`; the symbol table type lives in
`parsley/compiler/symbols.py`.

| Field | Type | Semantics |
|---|---|---|
| `symbol_table` | `dict[str, {type: "number"\|"string", declared_at: int}]` | `declared_at` = index into `history` of the declaring statement. **Written only by `semantic.py`.** |
| `ref_stack` | `list[str]` | Most recently assigned or referenced variable **last**. Read by the context resolver. |
| `history` | `list[Stmt]` | Accepted statements in order. |

`Stmt` = any statement AST node: `Let | Assign | Print | If | Repeat`.

### 2.8 AST nodes

Defined in `parsley/compiler/ast_nodes.py` (implemented; owner ASUS). Frozen, comparable
dataclasses, so V2 is a plain equality check. Child sequences are tuples, so every tree is
hashable.

| Node | Fields |
|---|---|
| `Program` | `statements: tuple[Stmt, ...]` |
| `Let`, `Assign` | `name: str`, `value: Expr` |
| `Print` | `value: Expr` |
| `If` | `condition: Compare`, `then_body: tuple[Stmt, ...]`, `else_body: tuple[Stmt, ...] \| None` (None = no ELSE) |
| `Repeat` | `count: Num`, `body: tuple[Stmt, ...]` |
| `Compare` | `op: ">"\|"<"\|"=="\|">="\|"<="\|"!="`, `left: Expr`, `right: Expr` |
| `BinOp` | `op: "+"\|"-"\|"*"\|"/"`, `left: Expr`, `right: Expr` |
| `Neg` | `operand: Expr` (unary minus) |
| `Num` | `text: str` (exactly as written) |
| `Str` | `value: str` (unescaped content) |
| `Var` | `name: str` |

`Expr = Num | Str | Var | Neg | BinOp`; `Stmt = Let | Assign | Print | If | Repeat`.
Nodes hold no logic: type and range checks (e.g. the REPEAT count) belong to `semantic.py`.

## 3. Design rules

- No stage silently guesses. It returns a testable result or a diagnostic.
- The NLP never emits MiniLang text. It emits candidates; only the code generator writes code.
- The symbol table has one owner (semantic analyzer). The context resolver reads it but
  never writes to it.
- Back-translation templates live next to codegen templates, one per AST node type, so
  adding a node forces both.
- `ast_eval.py` and `interpreter.py` share no evaluation code. The interpreter runs on
  parsed MiniLang, not on the original AST.
- Mutation / corruption hooks exist only under `tests/`, never in the runtime pipeline.

## 4. Ownership of boundaries

| Boundary | Producer (owner) | Consumers (owners) |
|---|---|---|
| `Candidate`, `NLPResult` | NLP front end (ASUS) | IR builder (ASUS), suggest.py (MacBook), evaluation (Gaming), optional `parsley_ml` scorer (Gaming; may change `score` only) |
| `Diagnostic` | all stages | CLI (ASUS), evaluation (Gaming) |
| `Session` / symbol table | semantic.py (ASUS) | context.py (ASUS), ast_eval (Gaming), interpreter (MacBook) |
| AST nodes | ast_nodes.py (ASUS) | parser (MacBook), codegen (ASUS), verifiers (MacBook, Gaming) |
| `Verification` | verify/ (MacBook V2, Gaming/MacBook V3) | trace (ASUS), evaluation (Gaming) |

Contract changes need approval from every owner in the row (Section 2.1).
