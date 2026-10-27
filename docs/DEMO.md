# Demonstration guide (about 6 minutes)

## Setup and reliable rehearsal

Use Python 3.11+ from the new contribution branch, in a clean environment:

```
python -m venv .venv
# Activate .venv for your operating system.
python -m pip install -r requirements.txt -e .
python -m pytest -q
python scripts/validate_paraphrases.py
python scripts/demo.py --with-mutations
```

`scripts/demo.py` calls the real pipeline with scripted replies to clarification questions;
it checks every status, generated statement, V2/V3 result, and final execution. It returns
nonzero when a check fails. `--with-mutations` runs the test-only mutations using pytest.
`docs/demo-transcript.txt` is actual captured output from rehearsal, a text backup rather
than a video recording. A presenter can record a screen rehearsal separately.

## Speaking script and interactive alternative

Start `python -m parsley --trace` to present the same session interactively. Wait for each
clarification prompt and type the reply in the table. The automatic script is useful when
presentation time is short or typing is unreliable.

| Time | Type / show | Explain |
|---|---|---|
| 0:00 | `make a variable called score and set it to 10` | Point to candidate, AST, canonical English and V2/V3 results. Classical parsing and semantic analysis are real compiler stages. |
| 0:45 | `add 5 to it` | The compiler's declaration history resolves `it` to `score`; the value becomes 15. |
| 1:15 | `print total` then `print scroe`; reply `yes` | Undeclared normal text stays text; a likely typo asks rather than silently changing meaning. The printed variable value is 15. |
| 2:00 | `increase score`; reply `2` | Missing information causes a targeted question. No statement is recorded until answered. |
| 2:30 | `set score to 10 or 20`; reply `20` | Alternatives are clarified, not guessed. |
| 3:00 | `if score is at least 17 then print "adult" else print "minor"` | Show the comparison and branches in MiniLang and canonical English. |
| 3:20 | `repeat 2 times print "hello"` | Show a bounded repeat. Final output includes two `hello` lines. |
| 3:40 | `store 50 in bonus` | Rejection remains rejection, followed by `Try: set bonus to 50`. No bonus variable is created by a suggestion. |
| 4:00 | `set score to missingValue plus 1` | E201 demonstrates an undeclared arithmetic operand. Failed input does not alter the accepted program. |
| 4:20 | Automatic script's strict-confirmation and context-ablation sections | E103 records nothing after rejection. The same pronoun example succeeds with context on and fails with it off. This is a demo case, not the full held-out ablation. |
| 4:50 | Mutation rows from `--with-mutations` | Explain which checks catch which generation errors; equivalent behavior can evade V3. |
| 5:30 | Frozen dataset and validation result | Show 15 groups / 60 inputs. State that full N5 metrics and clarification ablation are still the Evaluation owner's task. |

## Precise claims for the viva

- N1 is symbol-table/history feedback into English interpretation. N2 is explicit clarification.
- N4 suggests a supported rewrite without executing rejected input.
- V1 exposes the interpretation for human review; it cannot prove intent.
- V2 checks AST structure and catches printer/parser drift; it cannot judge English intent.
- V3 compares final variables, printed lines and runtime errors using independently implemented
  evaluators. Equal behavior or a shared evaluator bug can evade it.
- The mutation suite includes six behavior-changing corruptions, two structural changes with
  identical behavior in the tested run, and one harmless whitespace control. V2 catches the
  eight structural changes; V3 catches the six behavior-changing ones. These are curated
  tests, not general detection-rate guarantees.
- The full evaluation modules are unfinished. Do not present the small demo ablation or
  schema/gold validation as the project's full evaluation results.

## Expected final demonstration state

`score = 20`; printed lines are `total`, `15`, `adult`, `hello`, `hello`; no runtime errors.
The rejected suggestion, semantic error and denied strict confirmation create no statements.
