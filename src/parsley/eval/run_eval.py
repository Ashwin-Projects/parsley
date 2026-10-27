"""Run the evaluation and ablations; write CSV and summary table (Phase 8, N5).

    python -m parsley.eval.run_eval [--root DIR] [--data DIR] [--fixtures DIR] [--out DIR]

Every item runs through the real pipeline in a fresh session after its setup sentences,
under three conditions that differ in one switch each:

* ``baseline``: context resolution (N1) on, clarification (N2) on.
* ``context_off``: N1 off for the evaluated sentence only. The setup always runs with N1
  on, so the ablation measures the sentence, not a broken session.
* ``forced_top1``: N2 cannot ask. Every question is answered with its first option (the
  top-ranked reading), or ``yes`` to a typo question; a question with no options (a
  missing value, an empty pronoun) cannot be guessed and stays a question.

A setup that does not reproduce its gold MiniLang is a ``setup_failed`` outcome, and an
exception is a ``crash`` outcome; both count as failures. Suggestions are judged
automatically: for a rejected input with a known meaning, the suggestion is compiled in
the same setup and is useful only if it gives the gold code. Mutation detection uses the
test-only operators in ``tests/mutations/operators.py`` (CLAUDE.md rule 6) on the gold
programs, checked with the real V2 and V3 layers. Optional ``human_blind.json`` and
``synthetic_blind.json`` sets are run the same way and each reported in its own section,
outside the headline numbers; the synthetic section also prints the file's provenance.
Output is deterministic: no timestamps, items in data order.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections.abc import Sequence
from itertools import zip_longest
from pathlib import Path
from types import ModuleType

from parsley.compiler.ast_nodes import Program
from parsley.compiler.codegen import generate
from parsley.compiler.lexer import LexError
from parsley.compiler.parser import ParseError, parse
from parsley.eval import metrics
from parsley.eval.dataset import DatasetError, Item, digest, load_development, load_held_out
from parsley.eval.metrics import Metric, MutationResult, Outcome
from parsley.pipeline import PipelineResult, answer, run
from parsley.session import Session
from parsley.verify import STEP_LIMIT_ERROR, ast_eval, interpreter, roundtrip

CONDITIONS = ("baseline", "context_off", "forced_top1")
MAX_FORCED_ANSWERS = 5
CSV_FIELDS = (
    "source", "condition", "subset", "group", "item_id", "input", "expected_status", "status",
    "category", "exact_match", "expected_minilang", "minilang", "suggestion", "suggestion_useful",
    "codes", "context_dependent",
)


# Running one item


def evaluate(item: Item, condition: str) -> Outcome:
    """Run ``item`` under ``condition``; never raises."""
    use_context = condition != "context_off"
    try:
        session = _setup(item)
        if session is None:
            return _outcome(item, condition, "setup_failed")
        result = run(item.input, session, use_context=use_context)
        if condition == "forced_top1":
            result = _force_top1(result, session, use_context)
        return _outcome(item, condition, result.status, result, _judge_suggestion(item, result, use_context))
    except Exception:  # an evaluation records a crash; it never stops on one
        return _outcome(item, condition, "crash")


def _setup(item: Item) -> Session | None:
    """A fresh session after the setup sentences (N1 on), or None if one misses its gold."""
    session = Session()
    for sentence, gold in zip_longest(item.setup, item.setup_minilang):
        if sentence is None:
            return None
        result = run(sentence, session)
        if result.status != "ok" or (gold is not None and result.minilang != gold):
            return None
    return session


def _force_top1(result: PipelineResult, session: Session, use_context: bool) -> PipelineResult:
    for _ in range(MAX_FORCED_ANSWERS):
        clarification = result.clarification
        if result.status != "needs_clarification" or clarification is None:
            break
        if clarification.options:
            reply = clarification.options[0]
        elif clarification.kind == "typo" and clarification.suggestion is not None:
            reply = "yes"
        else:
            break  # nothing to guess from
        answered = answer(result, reply, session, use_context=use_context)
        if answered is result:
            break
        result = answered
    return result


def _judge_suggestion(item: Item, result: PipelineResult, use_context: bool) -> bool | None:
    if result.status != "unsupported":
        return None
    if item.expected_suggestion is not None:
        return result.suggestion == item.expected_suggestion
    if item.expected_status != "ok" or item.expected_minilang is None:
        return None  # out of scope: no intended meaning to carry
    if result.suggestion is None:
        return False
    session = _setup(item)
    if session is None:
        return False
    retry = run(result.suggestion, session, use_context=use_context)
    return retry.status == "ok" and retry.minilang == item.expected_minilang


def _outcome(item: Item, condition: str, status: str, result: PipelineResult | None = None,
             useful: bool | None = None) -> Outcome:
    ast = result.trace.ast if result is not None and result.status == "ok" else None
    return Outcome(
        item_id=item.id, source=item.source, subset=item.subset, group=item.group,
        condition=condition, input=item.input, expected_status=item.expected_status, status=status,
        expected_minilang=item.expected_minilang,
        minilang=result.minilang if result is not None else None,
        ast_key=repr((ast,)) if ast is not None else None, gold_key=_gold_key(item.expected_minilang),
        context_dependent=item.context_dependent,
        suggestion=result.suggestion if result is not None else None, suggestion_useful=useful,
        codes=tuple(d.code for d in result.diagnostics) if result is not None else (),
        expected_codes=item.expected_codes,
    )


def _gold_key(minilang: str | None) -> str | None:
    if minilang is None:
        return None
    try:
        return repr(parse(minilang).statements)
    except (LexError, ParseError):
        return None


# Mutation detection (N3)


def load_operators(root: Path) -> ModuleType | None:
    path = Path(root) / "tests" / "mutations" / "operators.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("parsley_test_mutation_operators", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gold_programs(items: Sequence[Item]) -> list[tuple[str, Program]]:
    """Distinct gold programs (setup + expected statement), labelled by their first item."""
    seen: dict[str, tuple[str, Program]] = {}
    for item in items:
        if item.expected_status != "ok" or item.expected_minilang is None:
            continue
        source = "\n".join((*item.setup_minilang, item.expected_minilang))
        if source in seen:
            continue
        try:
            seen[source] = (item.group or item.id, parse(source))
        except (LexError, ParseError):
            continue
    return list(seen.values())


def check_mutant(original: Program, mutant: Program) -> tuple[bool, bool | None]:
    """(V2 caught it, V3 caught it or None when V3 ran out of budget), as the pipeline checks."""
    position = len(original.statements) - 1
    statement = Program(original.statements[position:])
    v2 = roundtrip.check(generate(Program(mutant.statements[position:])), statement) is not None
    expected, actual = ast_eval.run(original), interpreter.run(generate(mutant))
    if STEP_LIMIT_ERROR in expected[2] or STEP_LIMIT_ERROR in actual[2]:
        return v2, None
    return v2, expected != actual


def mutation_results(items: Sequence[Item], operators: ModuleType) -> list[MutationResult]:
    results = []
    for label, program in gold_programs(items):
        for name, mutant in operators.mutants(program):
            v2, v3 = check_mutant(program, mutant)
            results.append(MutationResult(label, name, v2, v3))
    return results


# Report


def _metric_rows(outcomes: Sequence[Outcome]) -> list[tuple[Metric, str]]:
    subsets = sorted({o.subset for o in outcomes if o.expected_minilang is not None})
    rows = [(metrics.exact_match_accuracy(outcomes, {s}), s) for s in subsets]
    rows.append((metrics.exact_match_accuracy(outcomes, set(subsets)), "all with gold code"))
    if any(o.subset == "session" for o in outcomes):
        rows.append((metrics.session_exact_match(outcomes), "session"))
    raw, gold = metrics.paraphrase_consistency(outcomes)
    rows += [(raw, "paraphrase"), (gold, "paraphrase")]
    rows += [
        (metrics.ambiguity_precision(outcomes), "all"),
        (metrics.ambiguity_recall(outcomes), "ambiguous"),
        (metrics.unnecessary_question_rate(outcomes), "expected to compile"),
        (metrics.context_resolution_accuracy(outcomes), "context-dependent"),
        (metrics.safe_rejection_rate(outcomes), "unsupported"),
        (metrics.suggestion_usefulness(outcomes), "rejected, meaning known"),
        (metrics.wrong_code_rate(outcomes), "all"),
        (Metric("crashes", sum(o.status == "crash" for o in outcomes), len(outcomes)), "all"),
    ]
    return rows


def _metric_table(outcomes: Sequence[Outcome]) -> list[str]:
    lines = ["| Metric | Result | Over |", "|---|---|---|"]
    lines += [f"| {m.name} | {m.text} | {over} |" for m, over in _metric_rows(outcomes)]
    return lines


def _ablation_table(by_condition: dict[str, list[Outcome]]) -> list[str]:
    measures = [
        lambda o: metrics.exact_match_accuracy(o, {x.subset for x in o}),
        metrics.wrong_code_rate, metrics.unnecessary_question_rate, metrics.ambiguity_recall,
        metrics.context_resolution_accuracy, metrics.safe_rejection_rate,
    ]
    names = [measure(by_condition["baseline"]).name for measure in measures]
    lines = ["| Condition | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for condition in CONDITIONS:
        cells = [measure(by_condition[condition]).text for measure in measures]
        lines.append(f"| {condition} | " + " | ".join(cells) + " |")
    lines.append("")
    for condition in CONDITIONS[1:]:
        deltas = []
        for name, measure in zip(names, measures):
            base, other = measure(by_condition["baseline"]).value, measure(by_condition[condition]).value
            if base is not None and other is not None:
                deltas.append(f"{name} {100 * (other - base):+.1f} pp")
        lines.append(f"- {condition} vs baseline: " + ("; ".join(deltas) or "no comparable items") + ".")
    return lines


def _failure_table(outcomes: Sequence[Outcome]) -> list[str]:
    breakdown = metrics.failure_breakdown(outcomes)
    if not breakdown:
        return ["No failures."]
    lines = ["| Subset | Category | Count | Items |", "|---|---|---|---|"]
    for (subset, kind), count in breakdown.items():
        ids = [o.item_id for o in outcomes if o.subset == subset and metrics.category(o) == kind]
        shown = ", ".join(ids[:8]) + (f", ... (+{len(ids) - 8})" if len(ids) > 8 else "")
        lines.append(f"| {subset} | {kind} | {count} | {shown} |")
    return lines


def _mutation_section(results: Sequence[MutationResult] | None) -> list[str]:
    if results is None:
        return ["Not measured: mutation operators not found (tests/mutations/operators.py)."]
    if not results:
        return ["No gold programs to mutate."]
    layers = metrics.mutation_detection(results)
    lines = ["| Layer | Caught |", "|---|---|"]
    lines += [f"| {layer} | {m.text} |" for layer, m in layers.items()]
    skipped = sum(r.v3 is None for r in results)
    lines += ["", f"V3 skipped (work budget): {skipped}.", "",
              "| Operator | Mutants | V2 | V3 | Missed by both |", "|---|---|---|---|---|"]
    for name in sorted({r.operator for r in results}):
        group = [r for r in results if r.operator == name]
        missed = sum(not r.v2 and r.v3 is not True for r in group)
        lines.append(
            f"| {name} | {len(group)} | {sum(r.v2 for r in group)} | "
            f"{sum(r.v3 is True for r in group)} | {missed} |"
        )
    return lines


def _blind_section(blind: dict[str, list[Outcome]] | None) -> list[str]:
    if blind is None:
        return ["Not provided: add `tests/eval_data/human_blind.json` (format in TESTING.md) to",
                "report a set written by someone who has not seen the code."]
    return [
        "Written by someone who has not seen the code; kept out of the held-out numbers above.",
        "", *_metric_table(blind["baseline"]), "", *_ablation_table(blind), "",
        *_failure_table(blind["baseline"]),
    ]


def _synthetic_section(synthetic: dict[str, list[Outcome]] | None, provenance: str | None) -> list[str]:
    if synthetic is None:
        return ["Not provided: `tests/eval_data/synthetic_blind.json` (same format as the human",
                "blind set) is reported here when present."]
    return [
        f"Provenance: {provenance or 'not stated in the file'}",
        "",
        "Not written by a person; kept out of the held-out numbers above.",
        "", *_metric_table(synthetic["baseline"]), "", *_ablation_table(synthetic), "",
        *_failure_table(synthetic["baseline"]),
    ]


def _provenance(path: Path) -> str | None:
    """The ``provenance`` of a data file as one line (a string, or a mapping's values)."""
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8")).get("provenance")
    if isinstance(value, dict):
        return "; ".join(f"{key}: {text}" for key, text in value.items())
    return value if isinstance(value, str) else None


def summary(held: dict[str, list[Outcome]], development: dict[str, list[Outcome]],
            mutations: list[MutationResult] | None, files: Sequence[Path],
            blind: dict[str, list[Outcome]] | None = None,
            synthetic: dict[str, list[Outcome]] | None = None,
            synthetic_provenance: str | None = None) -> str:
    lines = [
        "# Parsley evaluation results",
        "",
        "Generated by `python -m parsley.eval.run_eval` from the files below; deterministic, so",
        "a clean clone reproduces these numbers. Each metric shows hits/total; there is no",
        "combined score. Failures are listed, not hidden.",
        "",
        "| Held-out file | SHA-256 |", "|---|---|",
        *[f"| {path.name} | `{digest(path)}` |" for path in files],
        "",
        "## Held-out results",
        "",
        "Baseline: context resolution (N1) on, clarification (N2) on.",
        "",
        *_metric_table(held["baseline"]),
        "",
        "## Ablations",
        "",
        "`context_off`: N1 off for the evaluated sentence (setup keeps N1 on). `forced_top1`: N2",
        "cannot ask; each question is answered with its top-ranked option.",
        "",
        *_ablation_table(held),
        "",
        "## Failures by category",
        "",
        "Held-out, baseline. Every condition's outcomes are in `results.csv`.",
        "",
        *_failure_table(held["baseline"]),
        "",
        "## Mutation detection by layer",
        "",
        "Test-only code-generation bugs injected into the held-out gold programs (last",
        "statement), checked with the real V2 (re-parse) and V3 (AST evaluator vs interpreter).",
        "",
        *_mutation_section(mutations),
        "",
        "## Human blind set",
        "",
        *_blind_section(blind),
        "",
        "## Synthetic blind set",
        "",
        *_synthetic_section(synthetic, synthetic_provenance),
        "",
        "## Development fixtures (not held-out)",
        "",
        "The system was built against `tests/fixtures/`, so these numbers are a sanity check,",
        "not evidence.",
        "",
        *_metric_table(development["baseline"]),
        "",
        *_ablation_table(development),
        "",
        *_failure_table(development["baseline"]),
        "",
        "## Method notes",
        "",
        "- Suggestion usefulness is judged automatically (the suggestion, compiled in the same",
        "  setup, must give the gold code); the plan asks for manual judgement, so treat it as a",
        "  lower bound. Held-out unsupported inputs have no intended meaning and are not judged.",
        "- Context-dependent items: every session sentence and every item with setup sentences.",
        "- Clarification question wording is not scored; only whether a question was asked.",
        "",
    ]
    return "\n".join(lines)


def _row(o: Outcome) -> dict[str, str]:
    return {
        "source": o.source, "condition": o.condition, "subset": o.subset, "group": o.group or "",
        "item_id": o.item_id, "input": o.input, "expected_status": o.expected_status,
        "status": o.status, "category": metrics.category(o),
        "exact_match": "" if o.expected_minilang is None else str(o.minilang == o.expected_minilang),
        "expected_minilang": o.expected_minilang or "", "minilang": o.minilang or "",
        "suggestion": o.suggestion or "",
        "suggestion_useful": "" if o.suggestion_useful is None else str(o.suggestion_useful),
        "codes": " ".join(o.codes), "context_dependent": str(o.context_dependent),
    }


def _mutation_row(r: MutationResult) -> dict[str, str]:
    caught = [layer for layer, hit in (("V2", r.v2), ("V3", r.v3 is True)) if hit]
    return {
        **dict.fromkeys(CSV_FIELDS, ""), "source": "mutation", "condition": "mutation",
        "subset": "mutation", "group": r.program, "item_id": f"{r.program}:{r.operator}",
        "status": "v3_skipped" if r.v3 is None else "checked",
        "category": "+".join(caught) if caught else "missed",
    }


def write_results(out: Path, outcomes: Sequence[Outcome], mutations: Sequence[MutationResult] | None,
                  text: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_row(o) for o in outcomes)
        writer.writerows(_mutation_row(r) for r in mutations or ())
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")


def _run_all(items: Sequence[Item]) -> dict[str, list[Outcome]]:
    return {condition: [evaluate(item, condition) for item in items] for condition in CONDITIONS}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m parsley.eval.run_eval", description="Run the evaluation and ablations.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument("--data", type=Path, help="held-out data (default: ROOT/tests/eval_data)")
    parser.add_argument("--fixtures", type=Path, help="development fixtures (default: ROOT/tests/fixtures)")
    parser.add_argument("--out", type=Path, help="output directory (default: ROOT/results)")
    args = parser.parse_args(argv)
    data = args.data or args.root / "tests" / "eval_data"
    fixtures = args.fixtures or args.root / "tests" / "fixtures"
    out = args.out or args.root / "results"
    try:
        held_items, dev_items = load_held_out(data), load_development(fixtures)
    except DatasetError as error:
        print(f"run_eval: {error}", file=sys.stderr)
        return 2
    blind_items = [i for i in held_items if i.subset == "human_blind"]
    synthetic_items = [i for i in held_items if i.subset == "synthetic_blind"]
    held_items = [i for i in held_items if i.subset not in ("human_blind", "synthetic_blind")]
    operators = load_operators(args.root)
    held, development = _run_all(held_items), _run_all(dev_items)
    blind = _run_all(blind_items) if blind_items else None
    synthetic = _run_all(synthetic_items) if synthetic_items else None
    mutations = None if operators is None else mutation_results(held_items, operators)
    text = summary(held, development, mutations, sorted(Path(data).glob("*.json")), blind,
                   synthetic, _provenance(Path(data) / "synthetic_blind.json"))
    groups = (held, *([blind] if blind else []), *([synthetic] if synthetic else []), development)
    outcomes = [o for by_condition in groups for condition in CONDITIONS for o in by_condition[condition]]
    write_results(out, outcomes, mutations, text)
    print(f"wrote {out / 'results.csv'} and {out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
