"""Evaluation conditions ``llm`` and ``hybrid``: the same items, with a real model.

Loaded only by ``run_eval --mode llm|hybrid``, so the default evaluation never imports
``parsley.llm``. Results go to ``results_<mode>_<model>.csv`` and ``summary_<mode>_<model>.md``,
so the rules-mode files are never overwritten. Responses come through ``MeteredProvider``: a
re-run reads the disk cache, costs nothing and gives the same bytes. Setup sentences always
use the rules, so the same session state is tested in every mode. Mutation detection is left
out: it injects bugs into the code generator, which no model touches.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from parsley.eval import metrics, run_eval
from parsley.eval.dataset import Item
from parsley.eval.metrics import LLMFacts, Metric, Outcome
from parsley.llm import hybrid, validate
from parsley.llm.cache import MeteredProvider
from parsley.llm.config import UnavailableProvider, load_provider
from parsley.llm.prompt import PROMPT_CHANGES, PROMPT_SHA256
from parsley.nlp.candidates import LLM_RULE_ID
from parsley.pipeline import PipelineResult, answer
from parsley.session import Session

LLM_FIELDS = (
    "llm_asked", "llm_accepted", "llm_failed", "derived_question", "confirmed_minilang", "chosen_rule",
    "back_translation", "llm_discarded", "llm_reading",
)
BY_CONDITION = dict[str, list[Outcome]]


def facts(result: PipelineResult, session: Session, provider: object) -> LLMFacts:
    """What the model did for this result. A derived question is answered ``yes`` to see the code."""
    consulted = result.trace.llm
    clarification = result.clarification
    derived = clarification is not None and clarification.kind == "derived_value"
    chosen = result.trace.chosen.rule_id if result.trace.chosen is not None else ""
    proposed = [] if consulted is None else [
        {"intent": c.intent, "slots": c.slots, "score": c.score} for c in consulted.candidates
    ]
    return LLMFacts(
        asked=consulted is not None,
        accepted=result.status == "ok" and chosen == LLM_RULE_ID,
        discarded=() if consulted is None else tuple(str(d.reason) for d in consulted.discarded),
        derived_question=derived,
        confirmed_minilang=answer(result, "yes", copy.deepcopy(session)).minilang if derived else None,
        failed=any(d.code in ("W510", "W511") for d in result.diagnostics),
        latency=getattr(provider, "last_latency", None) if consulted is not None else None,
        proposed=json.dumps(proposed, sort_keys=True, ensure_ascii=False) if proposed else "",
        rule_id=chosen,
        back_translation=result.back_translation or "",
    )


def run(args: argparse.Namespace, held_items: Sequence[Item], dev_items: Sequence[Item], out: Path) -> int:
    """Run one LLM condition and write its own files; 2 if no provider is configured."""
    inner = load_provider(Path(args.root) / ".env")
    if isinstance(inner, UnavailableProvider):
        print(f"run_eval: the LLM is not configured: {inner.error}", file=sys.stderr)
        return 2
    model = getattr(inner, "model", inner.name)
    provider = MeteredProvider(inner, model, args.cache or out / "llm_cache", delay=args.delay)
    held = [i for i in held_items if i.subset not in ("human_blind", "synthetic_blind")]
    synthetic = [i for i in held_items if i.subset == "synthetic_blind"]
    groups = {
        "Held-out": held, "Synthetic blind set": synthetic, "Development fixtures (not evidence)": list(dev_items),
    }
    results = {
        name: run_eval._run_all(items[:args.limit], args.mode, provider) for name, items in groups.items() if items
    }
    stem = f"{args.mode}_{_slug(model)}" + (f"_limit{args.limit}" if args.limit else "")
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / f"results_{stem}.csv", results)
    (out / f"summary_{stem}.md").write_text(_summary(args.mode, model, results), encoding="utf-8", newline="\n")
    if args.record:
        provider.write_fixture(args.record)
    print(
        f"wrote {out / f'results_{stem}.csv'} and {out / f'summary_{stem}.md'} "
        f"({provider.network_calls} network calls, {provider.cache_hits} cached, "
        f"{provider.failures} failed, {provider.rate_limited} rate limited)"
    )
    return 0


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", model).strip("-")


def _write_csv(path: Path, results: dict[str, BY_CONDITION]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(*run_eval.CSV_FIELDS, *LLM_FIELDS), lineterminator="\n")
        writer.writeheader()
        for by_condition in results.values():
            for condition in run_eval.CONDITIONS:
                writer.writerows({**run_eval._row(o), **_llm_row(o.llm)} for o in by_condition[condition])


def _llm_row(llm: LLMFacts | None) -> dict[str, str]:
    if llm is None:  # the item crashed or its setup failed
        return dict.fromkeys(LLM_FIELDS, "")
    return {
        "llm_asked": str(llm.asked), "llm_accepted": str(llm.accepted), "llm_failed": str(llm.failed),
        "derived_question": str(llm.derived_question), "confirmed_minilang": llm.confirmed_minilang or "",
        "chosen_rule": llm.rule_id, "back_translation": llm.back_translation,
        "llm_discarded": " ".join(llm.discarded), "llm_reading": llm.proposed,
    }


# Report


def _wrong(outcomes: Sequence[Outcome]) -> list[Outcome]:
    return [o for o in outcomes if o.status == "ok" and metrics.category(o) != "correct"]


def _headline(name: str, outcomes: Sequence[Outcome]) -> str:
    wrong = _wrong(outcomes)
    from_model = sum(o.llm is not None and o.llm.accepted for o in wrong)
    return f"**Wrong code: {metrics.wrong_code_rate(outcomes).text}** on {name}, {from_model} of them from LLM readings."


def _activity(outcomes: Sequence[Outcome]) -> list[str]:
    llm = [o.llm for o in outcomes if o.llm is not None]
    derived = [o for o in outcomes if o.llm is not None and o.llm.derived_question and o.expected_minilang]
    confirmed = sum(o.llm.confirmed_minilang == o.expected_minilang for o in derived)
    latencies = [fact.latency for fact in llm if fact.latency is not None]
    average = f"{sum(latencies) / len(latencies):.3f}" if latencies else "n/a"
    rows = [
        ("LLM calls", sum(fact.asked for fact in llm)),
        ("LLM call failures", sum(fact.failed for fact in llm)),
        ("LLM-sourced accepted items", sum(fact.accepted for fact in llm)),
        ("Derived-value questions", sum(fact.derived_question for fact in llm)),
        ("Derived questions whose confirmed reading is the gold code", Metric("", confirmed, len(derived)).text),
        ("Average latency (seconds)", average),
    ]
    lines = ["| Measure | Value |", "|---|---|", *[f"| {name} | {value} |" for name, value in rows]]
    failed = sum(fact.failed for fact in llm)
    if failed:
        lines += ["", f"{failed} items fell back to the rule result because the call failed, so these numbers "
                      "understate the model."]
    return lines


def _discards(outcomes: Sequence[Outcome]) -> list[str]:
    counts = Counter(reason for o in outcomes if o.llm is not None for reason in o.llm.discarded)
    if not counts:
        return ["No proposals were discarded."]
    return ["| Reason | Proposals |", "|---|---|", *[f"| {k} | {v} |" for k, v in sorted(counts.items())]]


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _wrong_table(outcomes: Sequence[Outcome]) -> list[str]:
    wrong = _wrong(outcomes)
    if not wrong:
        return ["None."]
    lines = ["| Item | Input | Expected | Got | Rule | Understood | Model proposed |", "|---|---|---|---|---|---|---|"]
    for o in wrong:
        llm = o.llm
        lines.append(
            f"| {o.item_id} | {_cell(o.input)} | {_cell(o.expected_minilang) or '(no code)'} | {_cell(o.minilang)} "
            f"| {llm.rule_id if llm else ''} | {_cell(llm.back_translation) if llm else ''} "
            f"| {_cell(llm.proposed) if llm else ''} |"
        )
    return lines


def _section(name: str, by_condition: BY_CONDITION) -> list[str]:
    baseline = by_condition["baseline"]
    return [
        f"## {name}", "",
        _headline(name, baseline), "",
        *run_eval._metric_table(baseline), "",
        f"### LLM activity ({name})", "", *_activity(baseline), "",
        f"### Discarded proposals by reason ({name})", "", *_discards(baseline), "",
        f"## Wrong-code items ({name})", "", *_wrong_table(baseline), "",
        f"### Ablations ({name})", "", *run_eval._ablation_table(by_condition), "",
        f"### Failures by category ({name})", "", *run_eval._failure_table(baseline), "",
    ]


def _summary(mode: str, model: str, results: dict[str, BY_CONDITION]) -> str:
    primary = next(iter(results))
    lines = [
        f"# Parsley evaluation: mode {mode}, model {model}", "",
        _headline(primary, results[primary]["baseline"]) if results else "No items.", "",
        "The rules-mode results stay in `results.csv` and `summary.md` (exact match 105/118 and wrong code",
        "0/168 at v1.1). Generated by `python -m parsley.eval.run_eval --mode " + mode + "`.", "",
        "## Provenance", "",
        f"- Mode: `{mode}`; model: `{model}`.",
        f"- System prompt SHA-256: `{PROMPT_SHA256}`.",
        f"- LLM scores {hybrid.LLM_SCORE_MIN} to {hybrid.LLM_SCORE_MAX}, consult threshold "
        f"{hybrid.CONSULT_THRESHOLD}, minimum confidence {validate.MIN_CONFIDENCE}.",
        "- The prompt and thresholds were not tuned on held-out data; any prompt change is made against "
        "the development fixtures only, and is listed here:",
        *[f"  - {change}" for change in PROMPT_CHANGES],
        "- Setup sentences use the rules. Mutation detection is not repeated: no model touches codegen.",
        "- A derived question on an item expected to compile counts as an unnecessary question and not as "
        "an exact match: the baseline compiles nothing unconfirmed. `forced_top1` simulates a yes, as it "
        "answers every question.", "",
    ]
    for name, by_condition in results.items():
        lines += _section(name, by_condition)
    return "\n".join(lines)
