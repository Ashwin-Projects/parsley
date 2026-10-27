"""eval/metrics.py: every Section 8 metric as hits/total, from recorded outcomes only."""

import pytest

from parsley.eval.metrics import (
    Metric, MutationResult, Outcome, ambiguity_precision, ambiguity_recall, category,
    context_resolution_accuracy, exact_match_accuracy, failure_breakdown, mutation_detection,
    paraphrase_consistency, safe_rejection_rate, session_exact_match, suggestion_usefulness, unnecessary_question_rate,
    wrong_code_rate,
)


def outcome(item_id="I1", *, subset="valid", group=None, expected_status="ok", status="ok",
            expected_minilang="PRINT 1;", minilang="PRINT 1;", ast_key=None, gold_key=None,
            context_dependent=False, suggestion=None, suggestion_useful=None, codes=(),
            expected_codes=()):
    return Outcome(
        item_id=item_id, source="held_out", subset=subset, group=group, condition="baseline",
        input="x", expected_status=expected_status, status=status,
        expected_minilang=expected_minilang, minilang=minilang,
        ast_key=ast_key if ast_key is not None else minilang,
        gold_key=gold_key if gold_key is not None else expected_minilang,
        context_dependent=context_dependent, suggestion=suggestion,
        suggestion_useful=suggestion_useful, codes=codes, expected_codes=expected_codes,
    )


def test_metric_reports_ratio_and_na_for_an_empty_denominator():
    assert Metric("m", 3, 4).value == 0.75 and Metric("m", 3, 4).text == "3/4 (75.0%)"
    assert Metric("m", 0, 0).value is None and Metric("m", 0, 0).text == "n/a (no items)"


def test_exact_match_counts_only_items_with_expected_code_in_the_given_subsets():
    outcomes = [
        outcome("a"), outcome("b", minilang="PRINT 2;"), outcome("c", status="unsupported", minilang=None),
        outcome("d", subset="paraphrase"),
        outcome("e", expected_status="ambiguous", status="needs_clarification", expected_minilang=None, minilang=None),
    ]
    assert exact_match_accuracy(outcomes, {"valid"}) == Metric("exact-match accuracy", 1, 3)


def test_paraphrase_consistency_raw_and_against_gold():
    same_wrong = [outcome(f"g1-{n}", subset="paraphrase", group="g1", minilang="PRINT 2;") for n in range(3)]
    all_right = [outcome(f"g2-{n}", subset="paraphrase", group="g2") for n in range(3)]
    one_rejected = [outcome("g3-1", subset="paraphrase", group="g3"),
                    outcome("g3-2", subset="paraphrase", group="g3", status="unsupported", minilang=None)]
    raw, gold = paraphrase_consistency(same_wrong + all_right + one_rejected)
    assert (raw.hits, raw.total) == (2, 3)   # g1 is consistent but wrong; g3 is not consistent
    assert (gold.hits, gold.total) == (1, 3)  # only g2 is consistent with the gold AST


def test_ambiguity_precision_recall_and_unnecessary_questions():
    asked = dict(status="needs_clarification", minilang=None)
    outcomes = [
        outcome("amb1", expected_status="ambiguous", expected_minilang=None, **asked),
        outcome("amb2", expected_status="ambiguous", expected_minilang=None),          # missed
        outcome("ok1", **asked),                                                        # unnecessary
        outcome("ok2"), outcome("ok3"), outcome("ok4"),
        outcome("bad", expected_status="unsupported", expected_minilang=None, status="unsupported", minilang=None),
    ]
    assert ambiguity_precision(outcomes) == Metric("ambiguity precision", 1, 2)
    assert ambiguity_recall(outcomes) == Metric("ambiguity recall", 1, 2)
    assert unnecessary_question_rate(outcomes) == Metric("unnecessary-question rate", 1, 4)


def test_context_resolution_uses_only_context_dependent_items_with_expected_code():
    outcomes = [outcome("c1", context_dependent=True), outcome("c2", context_dependent=True, minilang="X"),
                outcome("n1")]
    assert context_resolution_accuracy(outcomes) == Metric("context-resolution accuracy", 1, 2)


def test_safe_rejection_means_no_crash_and_no_code_for_unsupported_input():
    unsupported = dict(expected_status="unsupported", expected_minilang=None)
    outcomes = [
        outcome("s1", status="unsupported", minilang=None, **unsupported),
        outcome("s2", status="needs_clarification", minilang=None, **unsupported),  # safe, no code
        outcome("s3", status="ok", minilang="PRINT 1;", **unsupported),              # unsafe: code
        outcome("s4", status="crash", minilang=None, **unsupported),                 # unsafe: crash
    ]
    assert safe_rejection_rate(outcomes) == Metric("safe-rejection rate", 2, 4)


def test_suggestion_usefulness_only_judges_rejections_with_a_known_meaning():
    rejected = dict(status="unsupported", minilang=None)
    outcomes = [
        outcome("u1", suggestion="set x to 1", suggestion_useful=True, **rejected),
        outcome("u2", suggestion="print x", suggestion_useful=False, **rejected),
        outcome("u3", suggestion=None, suggestion_useful=False, **rejected),   # no suggestion offered
        outcome("u4", suggestion="foo", suggestion_useful=None, **rejected),   # meaning unknown
        outcome("u5"),
    ]
    assert suggestion_usefulness(outcomes) == Metric("suggestion usefulness", 1, 3)


def test_wrong_code_rate_counts_code_that_does_not_match_what_was_wanted():
    outcomes = [
        outcome("w1"), outcome("w2", minilang="PRINT 2;"),
        outcome("w3", expected_status="ambiguous", expected_minilang=None, minilang="PRINT 1;"),
        outcome("w4", status="unsupported", minilang=None),
    ]
    assert wrong_code_rate(outcomes) == Metric("wrong-code rate", 2, 4)


@pytest.mark.parametrize("kwargs,expected", [
    ({}, "correct"),
    ({"minilang": "PRINT 2;"}, "wrong_code"),
    ({"status": "unsupported", "minilang": None}, "rejected"),
    ({"status": "needs_clarification", "minilang": None}, "unneeded_question"),
    ({"status": "error", "minilang": None}, "error"),
    ({"status": "crash", "minilang": None}, "crash"),
    ({"status": "setup_failed", "minilang": None}, "setup_failed"),
    ({"expected_status": "ambiguous", "expected_minilang": None}, "missed_ambiguity"),
    ({"expected_status": "unsupported", "expected_minilang": None}, "code_for_unsupported"),
    ({"expected_status": "error", "expected_minilang": None, "status": "error", "minilang": None,
      "codes": ("E201",), "expected_codes": ("E201",)}, "correct"),
    ({"expected_status": "error", "expected_minilang": None, "status": "error", "minilang": None,
      "codes": ("E204",), "expected_codes": ("E201",)}, "wrong_error"),
    ({"expected_status": "ok", "expected_minilang": None, "codes": ("W208",),
      "expected_codes": ("W208",)}, "correct"),
])
def test_category_names_each_outcome(kwargs, expected):
    assert category(outcome(**kwargs)) == expected


def test_failure_breakdown_groups_by_subset_and_category():
    outcomes = [outcome("a"), outcome("b", minilang="X"), outcome("c", subset="paraphrase", minilang="X")]
    assert failure_breakdown(outcomes) == {("paraphrase", "wrong_code"): 1, ("valid", "wrong_code"): 1}


def test_mutation_detection_per_layer_and_combined():
    results = [
        MutationResult("p1", "op_swap", v2=True, v3=True),
        MutationResult("p1", "operand_swap", v2=True, v3=False),
        MutationResult("p2", "literal", v2=False, v3=True),
        MutationResult("p2", "loop", v2=True, v3=None),  # V3 skipped (budget)
    ]
    layers = mutation_detection(results)
    assert layers["V2"] == Metric("mutations caught by V2", 3, 4)
    assert layers["V3"] == Metric("mutations caught by V3", 2, 3)
    assert layers["V2 or V3"] == Metric("mutations caught by V2 or V3", 4, 4)


def test_whole_session_counts_only_sessions_where_every_sentence_is_right():
    outcomes = [outcome("s1-1", subset="session", group="s1"), outcome("s1-2", subset="session", group="s1"),
                outcome("s2-1", subset="session", group="s2"),
                outcome("s2-2", subset="session", group="s2", status="setup_failed", minilang=None),
                outcome("v", subset="valid")]
    assert session_exact_match(outcomes) == Metric("whole-session exact match", 1, 2)
