"""Section 8 metrics (NOVELTY.md), computed only from recorded outcomes (Phase 8, N5).

Every metric is a ``Metric``: hits over a stated denominator, so a report always shows how
many items a number rests on. There is no combined score. Definitions:

* exact-match accuracy: generated MiniLang equals the gold, over items that have gold code.
* paraphrase consistency: raw = all members of a group give the same AST (the plan's
  definition); gold = all members give the gold AST (four equal wrong answers do not count).
* ambiguity precision: questions asked on truly ambiguous input / all questions asked.
* ambiguity recall: truly ambiguous inputs that got a question / all truly ambiguous inputs.
* unnecessary-question rate: questions asked / inputs expected to compile (``ok``).
* context-resolution accuracy: exact match over context-dependent items (a session, or a
  setup the sentence relies on: names, pronouns, variable vs. text, implicit declaration).
* safe-rejection rate: unsupported inputs that neither crashed nor produced code.
* suggestion usefulness: rejected inputs with a known meaning whose suggestion carries it
  (judged by ``run_eval``); a rejection with no suggestion counts as not useful.
* wrong-code rate: inputs that produced code other than the gold (or code at all when none
  was wanted) / all inputs; the N2 ablation measure.
* mutation detection: injected generation bugs caught by V2, by V3, and by either.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    name: str
    hits: int
    total: int

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    @property
    def text(self) -> str:
        if not self.total:
            return "n/a (no items)"
        return f"{self.hits}/{self.total} ({100 * self.hits / self.total:.1f}%)"


@dataclass(frozen=True)
class Outcome:
    """What the real pipeline did with one item under one condition."""

    item_id: str
    source: str
    subset: str
    group: str | None
    condition: str
    input: str
    expected_status: str  # "ok", "ambiguous", "unsupported" or "error"
    status: str  # a PipelineResult status, or "crash" / "setup_failed"
    expected_minilang: str | None
    minilang: str | None
    ast_key: str | None  # repr of the produced AST, for paraphrase consistency
    gold_key: str | None  # repr of the gold AST
    context_dependent: bool
    suggestion: str | None
    suggestion_useful: bool | None  # None: the intended meaning is unknown
    codes: tuple[str, ...]  # diagnostic codes produced
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class MutationResult:
    program: str
    operator: str
    v2: bool  # V2 caught it
    v3: bool | None  # V3 caught it; None: skipped (work budget)


def is_correct(o: Outcome) -> bool:
    if o.expected_status == "ok":
        if o.status != "ok":
            return False
        if o.expected_minilang is not None:
            return o.minilang == o.expected_minilang
        return set(o.expected_codes) <= set(o.codes)
    if o.expected_status == "ambiguous":
        return o.status == "needs_clarification"
    if o.expected_status == "unsupported":
        return o.status == "unsupported"
    return o.status == "error" and set(o.expected_codes) <= set(o.codes)


def category(o: Outcome) -> str:
    """``correct``, or the kind of failure."""
    if o.status in ("crash", "setup_failed"):
        return o.status
    if is_correct(o):
        return "correct"
    if o.status == "ok":
        return {
            "ok": "wrong_code", "ambiguous": "missed_ambiguity",
            "unsupported": "code_for_unsupported", "error": "missed_error",
        }[o.expected_status]
    if o.status == "needs_clarification":
        return "unneeded_question"
    if o.status == "unsupported":
        return "rejected"
    return "wrong_error" if o.expected_status == "error" else "error"


def failure_breakdown(outcomes: Iterable[Outcome]) -> dict[tuple[str, str], int]:
    """Failures counted by (subset, category), sorted."""
    counts = Counter((o.subset, category(o)) for o in outcomes)
    return {key: counts[key] for key in sorted(counts) if key[1] != "correct"}


def exact_match_accuracy(outcomes: Iterable[Outcome], subsets: set[str]) -> Metric:
    pool = [o for o in outcomes if o.subset in subsets and o.expected_minilang is not None]
    return Metric("exact-match accuracy", sum(o.minilang == o.expected_minilang for o in pool), len(pool))


def paraphrase_consistency(outcomes: Iterable[Outcome]) -> tuple[Metric, Metric]:
    groups: dict[str, list[Outcome]] = {}
    for o in outcomes:
        if o.subset == "paraphrase" and o.group is not None:
            groups.setdefault(o.group, []).append(o)
    raw = gold = 0
    for members in groups.values():
        keys = {o.ast_key if o.status == "ok" else None for o in members}
        if len(keys) == 1 and None not in keys:
            raw += 1
            gold += keys == {members[0].gold_key}
    return (Metric("paraphrase consistency (same AST)", raw, len(groups)),
            Metric("paraphrase consistency (gold AST)", gold, len(groups)))


def session_exact_match(outcomes: Iterable[Outcome]) -> Metric:
    """Whole sessions in which every sentence gave its gold code."""
    sessions: dict[str, bool] = {}
    for o in outcomes:
        if o.subset == "session" and o.group is not None:
            sessions[o.group] = sessions.get(o.group, True) and is_correct(o)
    return Metric("whole-session exact match", sum(sessions.values()), len(sessions))


def ambiguity_precision(outcomes: Iterable[Outcome]) -> Metric:
    asked = [o for o in outcomes if o.status == "needs_clarification"]
    return Metric("ambiguity precision", sum(o.expected_status == "ambiguous" for o in asked), len(asked))


def ambiguity_recall(outcomes: Iterable[Outcome]) -> Metric:
    ambiguous = [o for o in outcomes if o.expected_status == "ambiguous"]
    return Metric("ambiguity recall", sum(o.status == "needs_clarification" for o in ambiguous), len(ambiguous))


def unnecessary_question_rate(outcomes: Iterable[Outcome]) -> Metric:
    clear = [o for o in outcomes if o.expected_status == "ok"]
    return Metric("unnecessary-question rate", sum(o.status == "needs_clarification" for o in clear), len(clear))


def context_resolution_accuracy(outcomes: Iterable[Outcome]) -> Metric:
    pool = [o for o in outcomes if o.context_dependent and o.expected_minilang is not None]
    return Metric("context-resolution accuracy", sum(o.minilang == o.expected_minilang for o in pool), len(pool))


def safe_rejection_rate(outcomes: Iterable[Outcome]) -> Metric:
    pool = [o for o in outcomes if o.expected_status == "unsupported"]
    safe = sum(o.status != "crash" and o.minilang is None for o in pool)
    return Metric("safe-rejection rate", safe, len(pool))


def suggestion_usefulness(outcomes: Iterable[Outcome]) -> Metric:
    pool = [o for o in outcomes if o.status == "unsupported" and o.suggestion_useful is not None]
    return Metric("suggestion usefulness", sum(o.suggestion_useful is True for o in pool), len(pool))


def wrong_code_rate(outcomes: Sequence[Outcome]) -> Metric:
    wrong = sum(o.status == "ok" and category(o) != "correct" for o in outcomes)
    return Metric("wrong-code rate", wrong, len(outcomes))


def mutation_detection(results: Sequence[MutationResult]) -> dict[str, Metric]:
    ran_v3 = [r for r in results if r.v3 is not None]
    return {
        "V2": Metric("mutations caught by V2", sum(r.v2 for r in results), len(results)),
        "V3": Metric("mutations caught by V3", sum(r.v3 is True for r in ran_v3), len(ran_v3)),
        "V2 or V3": Metric("mutations caught by V2 or V3", sum(r.v2 or r.v3 is True for r in results), len(results)),
    }
