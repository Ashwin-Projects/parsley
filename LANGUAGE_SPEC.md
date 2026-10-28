# MiniLang and Constrained-English Specification

Status: **frozen for Phase 2 (2026-10-25); v1.1 vocabulary added 2026-10-28 (see the [changelog](#changelog-v11-vocabulary)).** Source of truth: plan v2.1, Section 4
([`docs/Clarix_NL_MiniLang_Compiler_Plan_Final.pdf`](docs/Clarix_NL_MiniLang_Compiler_Plan_Final.pdf);
"Clarix" in the PDF = Parsley), plus the team decisions recorded in
[Section 9](#9-decision-log).

Changes to this file require updating tests in the same commit (CLAUDE.md rule 4).

---

## 1. MiniLang grammar

```
program      := statement*
statement    := declaration | assignment | print_stmt | if_stmt | repeat_stmt
declaration  := "LET" IDENT "=" expression ";"
assignment   := IDENT "=" expression ";"
print_stmt   := "PRINT" expression ";"
if_stmt      := "IF" condition "THEN" block ("ELSE" block)?
repeat_stmt  := "REPEAT" NUMBER "TIMES" block
block        := "{" statement* "}"
condition    := expression ( ">" | "<" | "==" | ">=" | "<=" | "!=" ) expression
expression   := term   (("+" | "-") term)*
term         := factor (("*" | "/") factor)*
factor       := "-" factor | NUMBER | STRING | IDENT | "(" expression ")"
```

Precedence, from tightest: unary `-`, then `*` `/`, then `+` `-`. The binary operators are
left-associative. Parentheses override precedence.

## 2. Types and lexical rules

| Rule | Decision |
|---|---|
| Types | `number` (integer or decimal) and `string`. No booleans as values in MVP; conditions appear only inside `IF`. |
| Number operations | `+ - * /`, unary `-`, and all six comparisons. |
| String operations | `+` between two strings (concatenation), and `==` / `!=` between two strings. Nothing else. |
| Mixed types | No implicit conversion. String + number, string vs. number comparison, and unary `-` on a string are semantic errors. |
| Identifiers | Letters, digits, underscore; must start with a letter; case-sensitive. |
| Keywords | `LET`, `PRINT`, `IF`, `THEN`, `ELSE`, `REPEAT`, `TIMES`, reserved **in any case**: `let`, `Let` and `LET` are all unusable as identifiers. MiniLang source writes keywords in upper case; any other casing of a keyword is a lexical error. |
| NUMBER | Digits with an optional single decimal part (`20`, `2.5`). No sign in the token; negatives use unary `-`. |
| STRING | Double-quoted. The only escapes are `\"` (quote) and `\\` (backslash). Any other backslash sequence is a lexical error. |
| REPEAT count | An integer literal from 1 to 1000 (1000 is also the V3 safety cap). |
| Block scope | One global scope. `LET` inside a block (`IF` or `REPEAT` body) is a semantic error, `E202`. |

### 2.1 Canonical MiniLang formatting

The code generator (Phase 5) prints exactly one canonical form, so golden fixtures can
compare text. The form follows the examples in plan Section 4:

- One statement per line; every simple statement ends with `;`.
- Single spaces around `=`, binary operators and comparison operators: `LET x = a + 1;`
- Unary minus is attached with no space: `-5`, `-x`, `-(a + b)`; after a binary operator
  it reads `a - -5`.
- Keywords upper-case; identifiers and string contents keep their original spelling.
- Number literals are printed as written in the input (`2.5` stays `2.5`, `20` stays `20`).
- String literals are printed with `"` and `\` escaped as `\"` and `\\`.
- Blocks print on one line: `{ ` + the statement + ` }`.
  Example: `IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }`
- Parentheses appear only where precedence requires them: `x * (2 + 3)`, but `x * 2 + 3`.

### 2.2 Semantic errors (detected in Phase 4)

| Code | Condition | Example message |
|---|---|---|
| `E201` | Variable used (or assigned) before it is created | `score is used before it is created` |
| `E202` | `LET` inside an `IF` or `REPEAT` block | `variables must be created outside IF and REPEAT blocks` |
| `E203` | `-`, `*`, `/` or unary `-` on text | `name is text, and text cannot be multiplied` |
| `E204` | Text mixed with a number in `+` or a comparison | `cannot add text and a number: name is text and 5 is a number` |
| `E205` | Text compared with anything other than `==` / `!=` | `text can only be compared with 'is equal to' or 'is not equal to', not 'is greater than'` |
| `E206` | Division by a literal zero (`0`, `0.0`, `-0`) | `cannot divide by zero` |
| `E207` | REPEAT count that is not a whole number from 1 to 1000 | `REPEAT needs a whole number of times from 1 to 1000, not 0` |
| `W208` | Redeclaration (warning; the new `LET` replaces the old type) | `age already exists, so creating it again replaces it` |
| `E209` | Assignment that would change a variable's type | `x is a number, so it cannot be set to text` |

All of these have stage `semantic`. Diagnostics are plain English with a stage and a code
(see ARCHITECTURE.md, `Diagnostic`). Errors exit non-zero and never print fake success.

Type rules used by these checks:

- An expression with an unknown type (an undefined name, or a sub-expression that already
  failed) is not type-checked against its neighbours, so a failure does not cascade into
  further type errors.
- A variable keeps the type it was created with. Only a new top-level `LET` (W208) can
  change it; an assignment of the other type is `E209`. Because `LET` is not allowed in
  blocks, a type never changes on a branch that might not run.
- A statement with any error is not recorded: the symbol table, reference stack and
  history are unchanged. Warnings do not block recording.

## 3. Normalization and case

The normalizer lowercases **only** English command words and synonyms, for matching.
Extracted identifiers, unquoted text and quoted text keep their original spelling
(`totalAmount` stays `totalAmount`; `show "Hello"` prints `"Hello"`).
The normalizer also collapses repeated spaces and strips trailing punctuation
(`.`, `!`, `?`). The original input is always kept for the trace.

## 4. Variable vs. text policy (N1)

When an English operand is a bare word, it is resolved by the first rule that applies:

1. **Declared name.** An exact match to a declared variable becomes an identifier.
2. **Quoted text.** Quoted text is always a string.
3. **Near-miss of a declared name.** Ask to confirm (`Did you mean the variable score?`) when
   the word is close to a declared name, measured against the length of that declared name:

   | Declared name length | Asks when edit distance is |
   |---|---|
   | 1-2 letters | never (no typo check) |
   | 3-5 letters | <= 1 |
   | 6+ letters | <= 2 |

   Edit distance is the optimal-string-alignment distance: insert, delete, substitute, or
   swap two adjacent letters, each counting 1 (so `scroe` is 1 from `score`). A word on the
   common-English-word list (Section 4.1) is **never** treated as a typo.
4. **Operand of an operator word.** A word directly next to an operator word (`plus`,
   `minus`, `times`, `multiplied by`, `divided by`, `negative`, or the symbols `+ - * /`)
   becomes an identifier. If it is not declared, the semantic analyzer reports `E201`.
5. **Anything else.** It becomes a string literal (the whole run of words, e.g. `hello world`).

Only rule 3 asks a question. Other kinds of ambiguity (Section 7) still clarify.

Rule 3 also covers the target (`NAME`) of an assignment or update: `set scroe to 7` or
`increase scroe by 1` with `score` declared asks `Did you mean the variable score?` instead
of silently creating `scroe` (decision D-12). An explicit declaration (`let scroe be 7`,
`make a variable called scroe ...`) creates the name without asking.

If rule 4 makes an identifier that is not a legal one (`print hello world plus 1`), the
sentence fails with `E401` (stage `ir`); nothing is guessed.

Examples, after `LET age = 20;` and `LET score = 10;`:

| English | Result | Rule |
|---|---|---|
| `print age` | `PRINT age;` | 1 |
| `print "age"` | `PRINT "age";` | 2 |
| `print scroe` | clarify: `Did you mean the variable score?` | 3 (distance 1, 5-letter name) |
| `print store` | `PRINT "store";` | 5 (`store` is a common English word, so no typo check) |
| `set age to x plus 1` | `age = x + 1;` and then `E201` | 4 |
| `print total` | `PRINT "total";` | 5 |

### 4.1 Common-English-word list

The list is data in `parsley/nlp/patterns.py`. It contains every command word, synonym,
operator word, comparison word and pronoun in Section 6, plus this starting set:

```
a an the and or not no yes this these those is are was be been to by of in on at for
from with as all any some one two three more less most least than then else if
hello hi bye world done big small store start end stop go up down ok good bad true false
```

Adding a word is a spec change: update this list and the tests together.

## 5. Context rules (N1)

| Situation | Behaviour |
|---|---|
| Pronouns | `it`, `that`, `the variable` in a variable position resolve to the most recently assigned or referenced variable (top of the reference stack). |
| Empty reference stack | The pronoun is an unfilled required slot, so it clarifies (Section 7). |
| Implicit declaration | Assignment intents (`set`, `change`, `update`, `assign`, `make ... equal to`, `... becomes`) to an undeclared name generate `LET` instead of assignment, with warning `W301` (stage `context`: `x was not created yet, so this creates it`), rather than failing. Only at the top level: inside a block the assignment stays an assignment (and reports `E201`). |
| Typos | Section 4 rule 3: confirmation question, never silent auto-correction. When several declared names are close, the closest wins; on a tie, the first declared. |
| Type-aware wording | The symbol table stores inferred types. Arithmetic on a string variable (`add 5 to name`) gets a plain-English type error. |
| Type-hint re-scoring | After resolution each candidate's score is nudged, then candidates are re-ranked: -0.1 if rule 4 made an undeclared identifier; for increase/decrease/multiply/divide, -0.1 if the target is text, +0.05 if the target and the amount are numbers. Scores stay in [0, 1]. |

With context resolution off (`--no-context`, the N1 ablation), none of the above applies:
bare words and pronouns stay unresolved and the sentence fails with `E401` (stage `ir`),
and assignment to an undeclared name reports `E201`.

The `and set it to` inside pattern D1 is part of the pattern, not a context pronoun.

## 6. Supported English patterns

Notation: `NAME` = variable position (identifier or pronoun), `VALUE` = value
expression (Section 6.1), `COND` = condition (Section 6.2), `STMT` = block body
(Section 6.3), `N` = count. `(a|b)` = alternatives, `[x]` = optional. Matching is on
the normalized (lower-cased command word) text. Rule ids are stable and are used in
traces, `Candidate.rule_id` and N4 suggestions.

| Intent | Rule | Pattern | Example English | MiniLang |
|---|---|---|---|---|
| declare | D1 | `(make\|create\|declare\|define\|initialize) a [new] variable (called\|named) NAME and set it to VALUE` | make a variable called age and set it to 20 | `LET age = 20;` |
| declare | D2 | `(make\|create\|declare\|define\|initialize) a [new] variable (called\|named) NAME (with value\|equal to\|set to\|as\|=) VALUE` | create a variable named totalAmount with value 0 | `LET totalAmount = 0;` |
| declare | D3 | `let NAME be VALUE` | let greeting be "Hello" | `LET greeting = "Hello";` |
| declare | D4 | `(make\|create\|declare\|define\|initialize) a [new] variable NAME (with value\|equal to\|set to\|as\|=) VALUE` | create a variable total as 0 | `LET total = 0;` |
| declare | D5 | `(define\|initialize\|declare) NAME (with value\|equal to\|set to\|as\|to\|=) VALUE` | define total as 0 / initialize total to 0 | `LET total = 0;` |
| assign | S1 | `set NAME to [VALUE]` | set age to age plus 1 | `age = age + 1;` |
| assign | S2 | `change NAME (to\|as) [VALUE]` | change age to 30 | `age = 30;` |
| assign | S3 | `update NAME (to\|as) [VALUE]` | update score to 0 | `score = 0;` |
| assign | S4 | `assign VALUE to NAME` | assign 5 to score | `score = 5;` |
| assign | S5 | `set NAME (as\|equal to) [VALUE]` | set age as 30 | `age = 30;` |
| assign | S6 | `make NAME equal to [VALUE]` | make age equal to 30 | `age = 30;` |
| assign | S7 | `NAME becomes [VALUE]` | age becomes age plus 1 | `age = age + 1;` |
| increment | INC1 | `(increase\|increment\|raise\|grow) NAME [by VALUE]` | increase count by 2 | `count = count + 2;` |
| increment | INC2 | `add VALUE to NAME` | add 5 to score | `score = score + 5;` |
| decrement | DEC1 | `(decrease\|decrement\|reduce\|lower\|drop) NAME [by VALUE]` | decrease count by 1 | `count = count - 1;` |
| decrement | DEC2 | `subtract VALUE from NAME` | subtract 3 from lives | `lives = lives - 3;` |
| decrement | DEC3 | `(take\|remove) VALUE from NAME` | take 3 from lives | `lives = lives - 3;` |
| multiply | MUL1 | `multiply NAME [by VALUE]` | multiply total by 3 | `total = total * 3;` |
| divide | DIV1 | `divide NAME [by VALUE]` | divide total by 2 | `total = total / 2;` |
| print | P1 | `(print out\|show me\|print\|show\|display\|output) [VALUE]` | print age / show "Hello" / display hello world | `PRINT age;` / `PRINT "Hello";` / `PRINT "hello world";` |
| if | IF1 | `(if\|when) COND then STMT` | if score is at least 10 then print winner | `IF score >= 10 THEN { PRINT "winner"; }` |
| if | IF2 | `(if\|when) COND then STMT (else\|otherwise) STMT` | if age is greater than 17 then print adult else print minor | `IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }` |
| repeat | REP1 | `(repeat\|loop) [N times] STMT` | repeat 3 times print hello | `REPEAT 3 TIMES { PRINT "hello"; }` |
| repeat | REP2 | `repeat STMT N times` | repeat show score 2 times | `REPEAT 2 TIMES { PRINT score; }` |
| repeat | REP3 | `do STMT N times` | do print hello 3 times | `REPEAT 3 TIMES { PRINT "hello"; }` |
| repeat | REP4 | `STMT N times` | print hello 3 times | `REPEAT 3 TIMES { PRINT "hello"; }` |
| reference | (any NAME) | pronoun in a `NAME` position | add 5 to it (after a statement using score) | `score = score + 5;` |

The templates in this table are compiled directly into the pattern table
(`parsley/nlp/patterns.py`), so the table is the only place English phrasings live.

Bracketed optional slots (`[by VALUE]`, `[VALUE]`, `[N times]`) are **required** slots
that may be missing from the English. A missing one leads to a clarification question,
not a rejection (Section 7). This is how `increase x` produces `By how much?`.

Synonym groups (plan Phase 2): `make/create/declare`, `show/display/print`,
`plus/add`, `greater than/more than/above`. v1.1 adds `define/initialize` (declare),
`grow` (increase), `drop` (decrease), `print out/show me/output` (print), `when` (if),
`otherwise` (else) and `loop` (repeat).

Two-word verbs are tried before one-word verbs, so `print out x` prints `x`, not `"out x"`.
Rule S1 keeps its exact template: N4 builds the `store ... in` rewrite (`set NAME to VALUE`)
from it (Section 8), so `set ... as` and `set ... equal to` are a separate rule, S5.

**Fillers (v1.1).** A leading `please` is ignored (`please print x` = `print x`); `please`
alone is unsupported. The article `the` before a variable name is ignored: in a `NAME`
position always (`increase the score by 2`), and in a value only when the word after `the`
is a declared variable (`print the score`). Otherwise `the ...` is ordinary text
(`print the end` prints `"the end"`), and `the variable` stays a pronoun (Section 5).

### 6.1 Values

A `VALUE` is one operand, or operands joined by operator words, read with standard
precedence (`negative` first, then `times`/`divided by`, then `plus`/`minus`):

| Operator words | MiniLang |
|---|---|
| `plus`, `+` | `+` |
| `minus`, `-` (between two operands) | `-` |
| `times`, `multiplied by`, `*` | `*` |
| `divided by`, `/` | `/` |
| `negative OPERAND`, or `-` written directly before a number (`-5`) | unary `-` |

`minus` is always binary. A value that starts with `minus` is unsupported.

Operands are a number (`20`, `2.5`), quoted text (`"Hello"`), a bare word resolved by the
Section 4 policy, or a pronoun. Number words (`ten` -> `10`, for 0-20) are optional
in Phase 2 ("if cheap") and are not used in the fixtures.

### 6.2 Conditions

`COND := VALUE comparison VALUE`. The longest phrase wins (`is greater than or equal to`
before `is greater than`).

| English phrase | MiniLang |
|---|---|
| `is greater than`, `is more than`, `is above`, `is bigger than`, `is larger than` | `>` |
| `is less than`, `is below`, `is smaller than`, `is under` | `<` |
| `is greater than or equal to`, `is at least`, `is no less than` | `>=` |
| `is less than or equal to`, `is at most`, `is no more than` | `<=` |
| `is equal to`, `equals` | `==` |
| `is not equal to`, `does not equal`, `isn't`, `isn't equal to` | `!=` |

Bare `is` is **not** a comparison (it is too ambiguous).

### 6.3 Block bodies

In MVP, `IF` and `REPEAT` blocks hold **exactly one** statement. That statement may be a
`print`, `assign`, `increment`, `decrement`, `multiply` or `divide` sentence. It cannot be
a declaration (the MiniLang equivalent is error `E202`) or a nested `if`/`repeat`; such
input matches no pattern and is rejected.

An `and ...` continuation after an `IF`/`REPEAT` body (`if x is greater than 5 then print
big and print done`) is **rejected** with a suggestion to split the sentence (Section 8).
The same holds for any value in any sentence: one sentence is one statement, so
`set x to 5 and set y to 6` is rejected. `and` followed by something that is not a whole
statement is ordinary text (`print salt and pepper` prints `"salt and pepper"`).

## 7. Accept / clarify / reject rules (N2)

The NLP returns 0..k scored candidates. The ambiguity gate decides:

| Outcome | `NLPResult.status` | Rule (thresholds tuned in Phase 6) |
|---|---|---|
| **Accept** | `ok` | Exactly one candidate, or the top score is clearly ahead of the next (margin above threshold), and no required slot is missing or unresolved. |
| **Clarify** | `ambiguous` | Two or more plausible candidates, or a required slot is missing. Ask a targeted question listing the options. |
| **Reject** | `unsupported` | No candidate matches a supported pattern, or the input is an `and ...` block continuation. Hand over to N4 for a suggestion. |

Ambiguity sources covered: missing values, alternatives (`or`), likely typos of declared
names, and unclear operator scope.

**Score margin.** Readings are "too close" when their scores differ by less than
`CLARIFY_MARGIN = 0.05` (`parsley/nlp/ambiguity.py`, the one place it is set). The margin
equals the smallest context re-scoring nudge (Section 5), so a reading that type hints moved
ahead by a full nudge is accepted. Readings with the same intent and slots count as one.

**Order of checks** (the first that applies asks): alternatives (readings within the margin),
which variable is meant (typo, pronoun with an empty reference stack), operator scope, then
a missing slot. Alternatives come first, so a typo inside one reading is asked about only
once that reading is chosen. Which variable comes before operator scope, because both
groupings share the same words. A name the user confirmed as new (`no` to a typo question)
is not asked about again later in the same sentence.

### 7.1 What clarifies, and the exact question

Questions are filled from these templates. `{name}` keeps its original spelling.

| Ambiguity type | Trigger | Question template | Options |
|---|---|---|---|
| `missing_slot` | INC1 with no `by VALUE` | `By how much should {name} increase?` | free answer |
| `missing_slot` | DEC1 with no `by VALUE` | `By how much should {name} decrease?` | free answer |
| `missing_slot` | MUL1 with no `by VALUE` | `By how much should {name} be multiplied?` | free answer |
| `missing_slot` | DIV1 with no `by VALUE` | `By how much should {name} be divided?` | free answer |
| `missing_slot` | S1-S3 with nothing after `to` | `What value should {name} be set to?` | free answer |
| `missing_slot` | P1 with no `VALUE` | `What should be printed?` | free answer |
| `missing_slot` | REP1 with no `N times` | `How many times should it repeat?` | free answer |
| `missing_slot` | pronoun with an empty reference stack | `Which variable does "{pronoun}" refer to?` | free answer |
| `alternatives` | `VALUE or VALUE` in a value position (at most 4 alternatives; more is unsupported) | `{a} or {b}?` | `[a, b]` |
| `typo` | Section 4 rule 3 | `Did you mean the variable {name}?` | `["yes", "no"]` |
| `operator_scope` | MUL1/DIV1 whose `VALUE` contains `plus` or `minus` | `Do you mean ({name} {op} {a}) {op2} {b}, or {name} {op} ({a} {op2} {b})?` | the two readings |

In `operator_scope`, `{op}` is `times` or `divided by` and `{op2}` is `plus` or `minus`.
It applies to MUL1/DIV1 at any depth, including a block body (`repeat 2 times multiply x by
2 plus 3`). The first reading is `NAME op VALUE` read with standard precedence, the second
is `NAME op (VALUE)`. With a longer amount every grouping in the first option is spelled
out: `multiply x by 2 minus 3 minus 4` asks `Do you mean ((x times 2) minus 3) minus 4, or
x times (2 minus 3 minus 4)?`. Arithmetic in other positions (e.g. `set y to x times 2 plus 3`) uses standard
precedence and does **not** clarify.

With three or four alternatives the question lists them with commas: `1, 2 or 3?`. Quoted
alternatives keep their quotes (`"yes" or "no"?`). If readings differ in more than one
value, each whole reading is described (`print 1 or increase x by 1?`).

**Answers** (REPL). The answer is merged into the sentence and the sentence runs again from
the context resolver, so it can lead to a further question:

| Ambiguity | Accepted answers |
|---|---|
| `alternatives`, `operator_scope` | An option's text (case and quotes ignored), else its number (`1`, `2`, ...). |
| `missing_slot` | A `VALUE` (Section 6.1), or a number for a REPEAT count. |
| `missing_slot` (pronoun) | The name of a variable. |
| `typo` | `yes` / `y` uses the declared name. `no` / `n` keeps the word: text in a value, an identifier as an operand (rule 4), a new variable as an assignment target. |

An answer that does not fit asks the same question again; an empty answer cancels the
sentence, and nothing is recorded.

### 7.2 What auto-resolves (no question)

- Variable vs. text, by Section 4 rules 1, 2, 4 and 5.
- Pronouns when the reference stack is non-empty.
- Assignment to an undeclared name: implicit `LET` plus a warning.
- Operator precedence outside the `operator_scope` trigger.

### 7.3 Modes

- Interactive (REPL): the user's answer is merged into the slots and the candidate
  re-enters the pipeline at the context resolver.
- Non-interactive (a sentence argument or `--file`): a clarification becomes diagnostic
  `E102` (stage `ambiguity`) with the question and its options, so batch runs never hang.
- Back-translation (`I understood: ...`) is always shown. With `--confirm` (REPL only),
  every error-free statement is shown first and recorded only after `yes`; `no` reports
  `E103` and records nothing. Outside the REPL nobody can confirm, so `--confirm` reports
  `E103` for every statement.

### 7.4 Canonical back-translation (V1, Phase 5)

These are output descriptions of the AST, not additional accepted input patterns.
Identifiers and number spellings are preserved. Strings are always double-quoted,
escaping only quotes and backslashes as in Section 2.1, so text cannot be mistaken
for a variable or a command. Expression and comparison nodes render fragments;
a statement or nonempty program ends in one period. An empty program renders empty
text. Program statements are joined with `; ` within one sentence.

| Node | Canonical template (children rendered recursively) |
|---|---|
| `Program` | statements joined with `; ` |
| `Let` | `create variable NAME with value VALUE` |
| `Assign` | `set NAME to VALUE` |
| `Print` | `print VALUE` |
| `If` | `if CONDITION then begin THEN_BODY end` optionally followed by ` else begin ELSE_BODY end` |
| `Repeat` | `repeat COUNT times begin BODY end` |
| `Compare` | `LEFT COMPARISON RIGHT`; comparisons use `is greater than`, `is less than`, `is equal to`, `is not equal to`, `is greater than or equal to`, `is less than or equal to` |
| `BinOp` | `(LEFT OPERATOR RIGHT)`; operators use `plus`, `minus`, `times`, `divided by` |
| `Neg` | `negative (OPERAND)` |
| `Num` | original number text |
| `Str` | quoted, escaped string content |
| `Var` | original variable name |

An assignment whose value is exactly `NAME OP AMOUNT` uses the update template:
`increase NAME by AMOUNT`, `decrease NAME by AMOUNT`, `multiply NAME by AMOUNT`,
or `divide NAME by AMOUNT`, respectively. All other assignments use `set`.
Every binary expression is parenthesized and every unary operand is enclosed in
parentheses, so operator scope is explicit. Blocks use `begin ... end`, joining
their statements with `; `, with no internal sentence-ending periods.

## 8. Rejected English patterns

Rejected input returns `unsupported` with an N4 suggestion where one is close enough.
It never crashes and never produces code.

| Category (`reason`) | Examples | Suggestion |
|---|---|---|
| `out_of_scope`: functions | `define a function called greet` | none, or nearest pattern |
| `out_of_scope`: lists / collections | `create a list of numbers`, `sort the list descending` | none, or nearest pattern |
| `out_of_scope`: user input | `ask the user for their age` | none, or nearest pattern |
| `out_of_scope`: other loops | `while x is less than 10 print x` | none, or nearest pattern |
| `out_of_scope`: library maths | `calculate the square root of 16` | none, or nearest pattern |
| `out_of_scope`: files / I/O / jumps | `open the file data.txt`, `go to line 10` | none, or nearest pattern |
| `unsupported_phrasing` | `store 50 in bonus` | nearest pattern, e.g. `set bonus to 50` |
| `block_continuation` | `if count is greater than 5 then print big and print done`, `set x to 5 and set y to 6` | The sentence before `and`, e.g. `if count is greater than 5 then print big`. The E101 message adds: `Blocks hold one statement. Try: "{sentence before and}" and then "{clause}" as separate sentences.` |
| `malformed` | `!!!` (empty after normalization), an unterminated quote, input longer than 500 characters, or more than 64 readings of one rule | none |

## 9. Decision log

Decisions taken by the team on 2026-10-25 to close the Phase 1 open questions. They are
applied throughout this document.

| # | Question | Decision | Where |
|---|---|---|---|
| D-1 | Undeclared words in arithmetic | A word directly next to an operator word is an identifier; if undeclared, `E201`. | §4 rule 4 |
| D-2 | Typo distance | None for 1-2 letter names; <= 1 for 3-5; <= 2 for 6+; never for common English words. | §4 rule 3, §4.1 |
| D-3 | Typo question wording | `Did you mean the variable score?` | §7.1 |
| D-4 | Block boundaries | MVP blocks hold exactly one statement; an `and ...` continuation is rejected with a suggestion. Block boundaries are not an N2 ambiguity source. | §6.3, §8 |
| D-5 | Fixture location | `tests/fixtures/` is the source of truth; `examples/` holds runnable sessions from Phase 5. | TESTING.md |
| D-6 | Keyword case | Reserved in any case. | §2 |
| D-7 | String escapes | `\"` and `\\` only. | §2 |
| D-8 | Negative numbers | Unary minus added: `factor := "-" factor \| ...`. | §1, §2.1, §6.1 |
| D-9 | Block scope | `LET` inside a block is a semantic error, `E202`. | §2, §2.2 |
| D-10 | String comparison | Strings support only `==` and `!=`. | §2 |
| D-11 | REPEAT count | Integer literal from 1 to 1000. | §2 |
| D-12 | Typo in an assignment/update target | Asks the rule 3 typo question instead of an implicit `LET`; explicit declarations do not ask. *Accepted 2026-10-25.* | §4 |

Edit distance in D-2 is optimal string alignment (an adjacent swap counts as one edit), so
the plan's demo case `print scroe` stays a typo question for the 5-letter name `score`.

## Changelog: v1.1 vocabulary

*2026-10-28.* More English phrasings, each mapped onto an existing intent. The grammar,
AST and MiniLang are unchanged (Sections 1-2); all phrasings live in
`parsley/nlp/patterns.py`, and `tests/unit/test_vocabulary.py` checks each one against its
canonical phrasing. The submitted report and NOVELTY.md describe v1.0.

| Area | Added | Rules |
|---|---|---|
| declare | verbs `define`, `initialize`; value connectors `as`, `=`, `equal to`, `set to` (and `to` after `define`/`initialize`/`declare` NAME); `a variable NAME` without `called`/`named` | D1, D2, new D4, D5 |
| assign | `set NAME as/equal to VALUE`, `make NAME equal to VALUE`, `change/update NAME as VALUE`, `NAME becomes VALUE` | S2, S3, new S5, S6, S7 |
| increment | `grow` (`increment` and `raise` were already supported) | INC1 |
| decrement | `drop`; `take/remove VALUE from NAME` (`decrement` and `lower` were already supported) | DEC1, new DEC3 |
| print | `output`, `print out`, `show me` | P1 |
| conditions | `is bigger than`, `is larger than`, `is smaller than`, `is under`, `is no less than`, `is no more than`, `isn't`, `isn't equal to`; `otherwise` for `else`; `when` for `if` (`equals` and `is not equal to` were already supported) | 6.2, IF1, IF2 |
| repeat | `loop N times STMT`; `STMT N times` | REP1, new REP4 |
| fillers | leading `please`; `the` before a variable name | Section 6 |

Not added:

- **`write` (print).** Dropped: it is edit distance 2 from `while`, so N4 would suggest
  `write x is less than 10 print x` for an out-of-scope `while` loop (Section 8), which must
  get no suggestion.
- **Excluded by request:** `store VALUE in NAME` (stays rejected with the N4 suggestion
  `set NAME to VALUE`), `double`, `triple`, `quadruple`, `bump`, `exceed(s)`, `provided`.

Behaviour that changes for input v1.0 accepted: `show me` and `print out` with nothing
after them now ask `What should be printed?` instead of printing `"me"` or `"out"`;
`print the x` prints the variable `x` when it is declared, not the text `"the x"`. Input
v1.0 rejected that now asks a question: a repeated statement with a missing value
(`print 3 times`, `set x to 3 times`, REP4).
