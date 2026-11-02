"""Side-by-side table of the rules, hybrid and llm evaluation runs.

    python -m parsley.eval.compare results/results.csv results/results_hybrid_<model>.csv
                                   results/results_llm_<model>.csv

Reads what ``run_eval`` wrote and runs nothing. Each column is the held-out baseline of one
file, without the blind sets, which are reported on their own. The rules file has no LLM
columns, so those rows say ``n/a``.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from parsley.eval.metrics import Metric, p95

Row = dict[str, str]
NOT_APPLICABLE = "n/a"
_BLIND = ("human_blind", "synthetic_blind")


def mode_of(path: Path) -> str:
    """``results_hybrid_<model>.csv`` is ``hybrid``; ``results.csv`` is ``rules``."""
    parts = Path(path).stem.split("_")
    return parts[1] if len(parts) > 1 else "rules"


def load(path: Path) -> list[Row]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [
            row for row in csv.DictReader(handle)
            if row["source"] == "held_out" and row["condition"] == "baseline" and row["subset"] not in _BLIND
        ]


def _rate(hits: int, total: int) -> str:
    return Metric("", hits, total).text


def _exact(rows: Sequence[Row]) -> str:
    golden = [r for r in rows if r["expected_minilang"]]
    return _rate(sum(r["exact_match"] == "True" for r in golden), len(golden))


def _discards(rows: Sequence[Row]) -> str:
    counts = Counter(reason for r in rows for reason in r["llm_discarded"].split())
    return ", ".join(f"{reason} {count}" for reason, count in sorted(counts.items())) or "none"


def _llm_column(rows: Sequence[Row]) -> dict[str, str]:
    derived = [r for r in rows if r["derived_question"] == "True"]
    golden = [r for r in derived if r["expected_minilang"]]
    latencies = [float(r["latency"]) for r in rows if r["latency"]]
    slowest = p95(latencies)
    return {
        "Would match if confirmed": _rate(
            sum(r["confirmed_minilang"] == r["expected_minilang"] for r in golden), len(golden),
        ),
        "Derived-value questions": str(len(derived)),
        "LLM calls": str(sum(r["llm_asked"] == "True" for r in rows)),
        "LLM call failures": str(sum(r.get("llm_failed") == "True" for r in rows)),
        "Discarded proposals": _discards(rows),
        "Mean latency (s)": f"{sum(latencies) / len(latencies):.3f}" if latencies else NOT_APPLICABLE,
        "P95 latency (s)": NOT_APPLICABLE if slowest is None else f"{slowest:.3f}",
    }


def column(rows: Sequence[Row]) -> dict[str, str]:
    """One run's measures, in report order."""
    asked = [r for r in rows if r["status"] == "needs_clarification"]
    ambiguous = [r for r in rows if r["expected_status"] == "ambiguous"]
    clear = [r for r in rows if r["expected_status"] == "ok"]
    unsupported = [r for r in rows if r["expected_status"] == "unsupported"]
    measures = {
        "Exact match": _exact(rows),
        "Paraphrase exact": _exact([r for r in rows if r["subset"] == "paraphrase"]),
        "Would match if confirmed": NOT_APPLICABLE,
        "Wrong code": _rate(sum(r["status"] == "ok" and r["category"] != "correct" for r in rows), len(rows)),
        "Ambiguity precision": _rate(sum(r["expected_status"] == "ambiguous" for r in asked), len(asked)),
        "Ambiguity recall": _rate(sum(r["status"] == "needs_clarification" for r in ambiguous), len(ambiguous)),
        "Unnecessary questions": _rate(sum(r["status"] == "needs_clarification" for r in clear), len(clear)),
        "Derived-value questions": NOT_APPLICABLE,
        "Safe rejection": _rate(sum(r["status"] != "crash" and not r["minilang"] for r in unsupported), len(unsupported)),
        "LLM calls": NOT_APPLICABLE,
        "LLM call failures": NOT_APPLICABLE,
        "Discarded proposals": NOT_APPLICABLE,
        "Mean latency (s)": NOT_APPLICABLE,
        "P95 latency (s)": NOT_APPLICABLE,
    }
    if rows and "llm_asked" in rows[0]:
        measures.update(_llm_column(rows))
    return measures


def table(paths: Sequence[Path]) -> str:
    columns = [column(load(path)) for path in paths]
    lines = [
        "| Measure | " + " | ".join(mode_of(path) for path in paths) + " |",
        "|---|" + "---|" * len(paths),
    ]
    lines += [f"| {name} | " + " | ".join(c[name] for c in columns) + " |" for name in columns[0]]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    paths = [Path(arg) for arg in (sys.argv[1:] if argv is None else argv)]
    if not paths:
        print("usage: python -m parsley.eval.compare RESULTS.csv [RESULTS.csv ...]", file=sys.stderr)
        return 2
    print(table(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
