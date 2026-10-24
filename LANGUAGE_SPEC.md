# MiniLang and Constrained-English Specification

Status: **Phase 1 draft, pending team freeze.** Source of truth: plan v2.1, Section 4
(`Clarix_NL_MiniLang_Compiler_Plan_Final.pdf`; "Clarix" in the PDF = Parsley).

Changes to this file require updating tests in the same commit (CLAUDE.md rule 4).
Items marked **[P1 decision]** fill gaps the plan leaves open; they are Phase 1 work
(plan Phase 1, steps 2-3) and are open to review before the freeze. Items in
[Section 9](#9-open-questions-need-team-decision-before-freeze) are unresolved and are
deliberately kept out of the fixtures.

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
factor       := NUMBER | STRING | IDENT | "(" expression ")"
```

Precedence: `*` and `/` bind tighter than `+` and `-`; all four are left-associative.
Parentheses override precedence.

## 2. Types and lexical rules

| Rule | Decision |
|---|---|
| Types | `number` (integer or decimal) and `string`. No booleans as values in MVP; conditions appear only inside `IF`. |
| String + number | Semantic error in MVP (no implicit conversion). String + string is allowed (concatenation). |
| Identifiers | Letters, digits, underscore; must start with a letter; case-sensitive; MiniLang keywords reserved. |
| Keywords | `LET`, `PRINT`, `IF`, `THEN`, `ELSE`, `REPEAT`, `TIMES` (see open question Q3 on case). |
| NUMBER | Digits with an optional single decimal part (`20`, `2.5`). No sign; see open question Q5. |
| STRING | Double-quoted text (`"hello world"`). Escaping: see open question Q4. |

### 2.1 Canonical MiniLang formatting [P1 decision]

The code generator (Phase 5) prints exactly one canonical form, so golden fixtures can
compare text. The form follows the examples in plan Section 4:

- One statement per line; every simple statement ends with `;`.
- Single spaces around `=`, binary operators and comparison operators: `LET x = a + 1;`
- Keywords upper-case; identifiers and string contents keep their original spelling.
- Number literals are printed as written in the input (`2.5` stays `2.5`, `20` stays `20`).
- Blocks print on one line: `{ ` + statements separated by single spaces + ` }`.
  Example: `IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }`
- Parentheses appear only where precedence requires them: `x * (2 + 3)`, but `x * 2 + 3`.

### 2.2 Semantic errors (detected in Phase 4)

Undefined variable (e.g. `E201 'score is used before it is created'`), redeclaration
(warning), type mismatch (string arithmetic), division by literal zero, invalid
`REPEAT` count. Diagnostics are plain English with a stage and a code
(see ARCHITECTURE.md, `Diagnostic`). Errors exit non-zero and never print fake success.

## 3. Normalization and case

The normalizer lowercases **only** English command words and synonyms, for matching.
Extracted identifiers, unquoted text and quoted text keep their original spelling
(`totalAmount` stays `totalAmount`; `show "Hello"` prints `"Hello"`).
The normalizer also collapses repeated spaces and strips trailing punctuation
(`.`, `!`, `?`). The original input is always kept for the trace.

## 4. Variable vs. text policy (N1)

When an English value is a bare word or words, it is resolved in this fixed order:

1. Exact match to a declared variable -> identifier.
2. Quoted text -> always a string.
3. Anything else -> string literal by default.
4. Within edit distance 2 of a declared name -> ask to confirm
   (`Did you mean the variable score?`).

No other case of the variable-vs-text decision asks a question. (Other ambiguity types
in Section 7 still clarify.) Rule 1 is checked before rule 4, so an exact match never
asks.

Examples, after `LET age = 20;` and `LET score = 10;`:

| English | MiniLang | Why |
|---|---|---|
| `print age` | `PRINT age;` | rule 1 |
| `print "age"` | `PRINT "age";` | rule 2 |
| `print total` | `PRINT "total";` | rule 3 (not declared, not near a declared name) |
| `print scroe` | clarify: `Did you mean the variable score?` | rule 4 |

## 5. Context rules (N1)

| Situation | Behaviour |
|---|---|
| Pronouns | `it`, `that`, `the variable` in a variable position resolve to the most recently assigned or referenced variable (top of the reference stack). |
| Empty reference stack | The pronoun is an unfilled required slot -> clarify (Section 7). |
| Implicit declaration | Assignment intents (`set`, `change`, `update`, `assign`) to an undeclared name generate `LET` instead of assignment, with a warning diagnostic, rather than failing. |
| Typos | Edit distance <= 2 to a declared name -> confirmation question; never silently auto-correct. |
| Type-aware wording | The symbol table stores inferred types; arithmetic on a string variable (`add 5 to name`) is flagged with a plain-English type error. |

The `and set it to` inside pattern D1 is part of the pattern, not a context pronoun.

## 6. Supported English patterns

Notation: `NAME` = variable position (identifier or pronoun), `VALUE` = value
expression (Section 6.1), `COND` = condition (Section 6.2), `STMT` = block body
(Section 6.3), `N` = count. `(a|b)` = alternatives, `[x]` = optional. Matching is on
the normalized (lower-cased command word) text. Rule ids are stable and are used in
traces, `Candidate.rule_id` and N4 suggestions.

| Intent | Rule | Pattern | Example English | MiniLang |
|---|---|---|---|---|
| declare | D1 | `(make\|create\|declare) a [new] variable (called\|named) NAME and set it to VALUE` | make a variable called age and set it to 20 | `LET age = 20;` |
| declare | D2 | `(make\|create\|declare) a [new] variable (called\|named) NAME (with value\|equal to) VALUE` | create a variable named totalAmount with value 0 | `LET totalAmount = 0;` |
| declare | D3 | `let NAME be VALUE` | let greeting be "Hello" | `LET greeting = "Hello";` |
| assign | S1 | `set NAME to VALUE` | set age to age plus 1 | `age = age + 1;` |
| assign | S2 | `change NAME to VALUE` | change age to 30 | `age = 30;` |
| assign | S3 | `update NAME to VALUE` | update score to 0 | `score = 0;` |
| assign | S4 | `assign VALUE to NAME` | assign 5 to score | `score = 5;` |
| increment | INC1 | `(increase\|increment\|raise) NAME [by VALUE]` | increase count by 2 | `count = count + 2;` |
| increment | INC2 | `add VALUE to NAME` | add 5 to score | `score = score + 5;` |
| decrement | DEC1 | `(decrease\|decrement\|reduce\|lower) NAME [by VALUE]` | decrease count by 1 | `count = count - 1;` |
| decrement | DEC2 | `subtract VALUE from NAME` | subtract 3 from lives | `lives = lives - 3;` |
| multiply | MUL1 | `multiply NAME [by VALUE]` | multiply total by 3 | `total = total * 3;` |
| divide | DIV1 | `divide NAME [by VALUE]` | divide total by 2 | `total = total / 2;` |
| print | P1 | `(print\|show\|display) [VALUE]` | print age / show "Hello" / display hello world | `PRINT age;` / `PRINT "Hello";` / `PRINT "hello world";` |
| if | IF1 | `if COND then STMT` | if score is at least 10 then print winner | `IF score >= 10 THEN { PRINT "winner"; }` |
| if | IF2 | `if COND then STMT else STMT` | if age is greater than 17 then print adult else print minor | `IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }` |
| repeat | REP1 | `repeat [N times] STMT` | repeat 3 times print hello | `REPEAT 3 TIMES { PRINT "hello"; }` |
| repeat | REP2 | `repeat STMT N times` | repeat show score 2 times | `REPEAT 2 TIMES { PRINT score; }` |
| repeat | REP3 | `do STMT N times` | do print hello 3 times | `REPEAT 3 TIMES { PRINT "hello"; }` |
| reference | (any NAME) | pronoun in a `NAME` position | add 5 to it (after a statement using score) | `score = score + 5;` |

Bracketed optional slots (`[by VALUE]`, `[VALUE]`, `[N times]`) are **required** slots
that may be missing from the English. A missing one leads to a clarification question,
not a rejection (Section 7). This is how `increase x` produces `By how much?`.

Synonym groups (plan Phase 2): `make/create/declare`, `show/display/print`,
`plus/add`, `greater than/more than/above`.

### 6.1 Values

A `VALUE` is one operand, or operands joined by operator words, read with standard
precedence (`times`/`divided by` before `plus`/`minus`):

| Operator words | MiniLang |
|---|---|
| `plus`, `+` | `+` |
| `minus`, `-` | `-` |
| `times`, `multiplied by`, `*` | `*` |
| `divided by`, `/` | `/` |

Operands are a number (`20`, `2.5`), quoted text (`"Hello"`), a word or words resolved by
the Section 4 policy, or a pronoun. Number words (`ten` -> `10`, for 0-20) are optional
in Phase 2 ("if cheap") and are not used in the fixtures. How unquoted text that contains
operator words is read is open question Q1.

### 6.2 Conditions

`COND := VALUE comparison VALUE`. The longest phrase wins (`is greater than or equal to`
before `is greater than`).

| English phrase | MiniLang |
|---|---|
| `is greater than`, `is more than`, `is above` | `>` |
| `is less than`, `is below` | `<` |
| `is greater than or equal to`, `is at least` | `>=` |
| `is less than or equal to`, `is at most` | `<=` |
| `is equal to`, `equals` | `==` |
| `is not equal to`, `does not equal` | `!=` |

Bare `is` is **not** a comparison (it is too ambiguous).

### 6.3 Block bodies

In MVP English input, `IF` and `REPEAT` blocks contain exactly one statement.
**[P1 decision]** That statement may be a `print`, `assign`, `increment`, `decrement`,
`multiply` or `divide` sentence. It cannot be a declaration or a nested `if`/`repeat` (see
open question Q6 on scoping). Multi-statement blocks through `then ... and ...` are only
added if time allows. Until then, `and <statement>` after a block body is a
block-boundary ambiguity (Section 7).

## 7. Accept / clarify / reject rules (N2)

The NLP returns 0..k scored candidates. The ambiguity gate decides:

| Outcome | `NLPResult.status` | Rule (thresholds tuned in Phase 6) |
|---|---|---|
| **Accept** | `ok` | Exactly one candidate, or the top score is clearly ahead of the next (margin above threshold), and no required slot is missing or unresolved. |
| **Clarify** | `ambiguous` | Two or more plausible candidates, or a required slot is missing. Ask a targeted question listing the options. |
| **Reject** | `unsupported` | No candidate matches a supported pattern. Hand over to N4 for a suggestion. |

### 7.1 What clarifies, and the exact question [P1 decision on wording]

Questions are filled from these templates. `{name}` keeps its original spelling. Wording
follows the plan's demo and Phase 6 examples where they exist.

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
| `alternatives` | `VALUE or VALUE` in a value position | `{a} or {b}?` | `[a, b]` |
| `typo` | Section 4 rule 4 | `Did you mean the variable {name}?` | `["yes", "no"]` |
| `operator_scope` | MUL1/DIV1 whose `VALUE` contains `plus` or `minus` | `Do you mean ({name} {op} {a}) {op2} {b}, or {name} {op} ({a} {op2} {b})?` | the two readings |
| `block_boundary` | IF1/IF2 body followed by `and STMT` | `Should "{clause}" run only when the condition is true, or always?` | `["only when true", "always"]` |
| `block_boundary` | REP1-REP3 body followed by `and STMT` | `Should "{clause}" be repeated, or run once after the loop?` | `["repeated", "once after"]` |

In `operator_scope`, `{op}` is `times` or `divided by` and `{op2}` is `plus` or `minus`.
Arithmetic in other positions (e.g. `set y to x times 2 plus 3`) uses standard precedence
and does **not** clarify.

### 7.2 What auto-resolves (no question)

- Variable vs. text, by Section 4 rules 1-3.
- Pronouns when the reference stack is non-empty.
- Assignment to an undeclared name: implicit `LET` plus a warning.
- Operator precedence outside the `operator_scope` trigger.

### 7.3 Modes

- Interactive (REPL): the user's answer is merged into the slots and the candidate
  re-enters the pipeline at stage [B].
- Non-interactive (file mode): a clarification becomes a diagnostic, so batch runs never
  hang.
- Back-translation (`I understood: ...`) is always shown. Confirmation is requested only on
  CLARIFY, or for every statement with `--confirm`.

## 8. Rejected English patterns

Rejected input returns `unsupported` with an N4 suggestion where one is close enough.
It never crashes and never produces code.

| Category | Examples |
|---|---|
| Out of scope: functions | `define a function called greet` |
| Out of scope: lists / collections | `create a list of numbers`, `sort the list descending` |
| Out of scope: user input | `ask the user for their age` |
| Out of scope: other loops | `while x is less than 10 print x` |
| Out of scope: library maths | `calculate the square root of 16` |
| Out of scope: files / I/O / jumps | `open the file data.txt`, `go to line 10` |
| Unsupported phrasing of a supported idea | `store 50 in bonus` (suggest `set bonus to 50`) |
| Malformed / empty input | `!!!` (empty after normalization) |
| Nested IF/REPEAT, declarations inside blocks | see Section 6.3 |

## 9. Open questions (need team decision before freeze)

These are gaps or tensions in the plan. They are listed with a **proposed** fix but are
**not** decided. No fixture depends on them.

- **Q1. Variable-vs-text in arithmetic positions.** Rule 3 makes any undeclared bare word
  text. That means `set y to x plus 1` with `x` undeclared becomes `"x" + 1` (a type
  error), so the plan's "undefined variable" diagnostic (E201) can never come from
  English. *Proposed:* rule 3 applies to whole values. An operand of an operator word that
  is not declared is read as an identifier and reported as E201.
- **Q2. Typo distance for short names.** Distance <= 2 against a 1-2 letter name (`x`)
  makes almost every short word a typo (`print a` asks about `x`). *Proposed:* distance
  <= 1 for names of length <= 3, and <= 2 otherwise.
- **Q3. Keyword case.** Identifiers are case-sensitive, so is `let` (lower-case) a legal
  identifier? *Proposed:* reserve keywords case-insensitively.
- **Q4. String escaping.** Codegen must escape strings, but the grammar does not define
  escapes. *Proposed:* `\"` and `\\` only.
- **Q5. Negative numbers.** No unary minus in the grammar, so `set x to -5` cannot be
  expressed. *Proposed:* keep it out of MVP (reject with a suggestion), and document it as
  a limitation.
- **Q6. Block scope.** The grammar allows `LET` inside a block, but no scoping rule is
  given. *Proposed:* one global scope; English cannot declare inside a block (Section 6.3).
- **Q7. Comparing strings.** Types for `<`/`>` on strings, and string vs. number
  comparisons, are undefined. *Proposed:* `==`/`!=` allowed between same-typed values;
  ordering only on numbers; mixed comparisons are type errors.
- **Q8. REPEAT count range.** "Invalid REPEAT count" is not defined. *Proposed:* an
  integer literal from 1 to 1000 (1000 = the plan's V3 safety cap).
