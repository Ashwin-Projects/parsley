# Parsley viva checklist (about 6 minutes)

## Fresh-machine setup

Use Python 3.11+ and Git. In Windows PowerShell, run:

```powershell
git clone https://github.com/Ashwin-Projects/parsley.git
cd parsley
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -e .
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. Stay in the
repository root. Setup needs network access; the demonstration runs offline.

## Run these four commands in order

1. **Scripted demonstration:** `python scripts/demo.py`
   Expect `DEMO PASS`, final `score = 20`, and V2/V3 passing on accepted statements.
   **N1:** context and variable/text resolution. **N2:** clarification before recording.
   **N3:** V1 back-translation, V2 AST comparison, V3 independent execution checks.
   **N4:** `store 50 in bonus` is rejected with `Try: set bonus to 50`, without execution.

2. **Live clarification:** `python -m parsley --trace`
   Enter each line below, waiting for the prompt; `yes`, `2` and `20` are replies:

   ```text
   let score be 10
   add 5 to it
   print total
   print scroe
   yes
   increase score
   2
   set score to 10 or 20
   20
   print score
   ```

   **N1:** `it` resolves to `score`; `total` stays text. **N2:** typo, missing amount
   and alternatives ask questions. **N3:** trace and verification summaries are visible.
   The final statement is `PRINT score;` (value 20 when executed). End the REPL with
   Ctrl+Z then Enter on Windows, or Ctrl+D on macOS/Linux; expected exit code 0.

3. **Context ablation:** `python -m parsley --no-context`
   Enter `let score be 10`, then `add 5 to it`, then end the REPL as above.
   **N1:** the declaration succeeds; the pronoun produces `ir E401` because context
   resolution is disabled. Expected exit code **1** demonstrates controlled rejection.

4. **Measured evaluation:** `python -m parsley.eval.run_eval`
   Expect exit code 0 and paths to `results/results.csv` and `results/summary.md`.
   Open the summary: **N5** reports frozen held-out results, N1/N2 ablations and N3
   mutation detection. Explain failures too: baseline 104/118 exact matches, 1/15
   gold-consistent paraphrase groups, and N4 usefulness 0/13. See
   [NOVELTY.md](../NOVELTY.md#results-2026-10-27) for results and limitations.
   Exit 0 means the evaluation ran; it does not mean every input was correct.

## Fallback

- For import errors, check the repository root and activated environment; in PowerShell,
  `$env:PYTHONPATH = (Resolve-Path .\src).Path` also enables checkout imports.
- If live typing fails, use the already rehearsed scripted demo. If execution fails,
  show [demo-transcript.txt](demo-transcript.txt) and the checked-in
  [results summary](../results/summary.md), explicitly labeling them prior captures.
  Report the failing command; do not claim a fresh pass or alter data/scores during the viva.
- These checks verify defined properties, not arbitrary English intent. V3 may skip
  when its execution budget is exceeded; never describe a skip as a pass.
