"""The side-by-side table of the rules, hybrid and llm evaluation runs."""

import csv

from parsley.eval import compare

BASE = {
    "source": "held_out", "condition": "baseline", "subset": "paraphrase", "expected_status": "ok",
    "status": "ok", "category": "correct", "exact_match": "True", "expected_minilang": "x = 1;",
    "minilang": "x = 1;",
}
LLM = {
    "llm_asked": "False", "derived_question": "False", "confirmed_minilang": "", "llm_discarded": "", "latency": "",
}


def write(path, *rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def column(tmp_path, *rows, name="results_hybrid_m.csv"):
    return compare.column(compare.load(write(tmp_path / name, *rows)))


def test_only_held_out_baseline_rows_count(tmp_path):
    rows = compare.load(write(
        tmp_path / "results.csv", BASE, {**BASE, "condition": "forced_top1"}, {**BASE, "source": "development"},
        {**BASE, "subset": "synthetic_blind"}, {**BASE, "subset": "human_blind"},
    ))
    assert len(rows) == 1


def test_the_mode_comes_from_the_file_name(tmp_path):
    assert compare.mode_of(tmp_path / "results.csv") == "rules"
    assert compare.mode_of(tmp_path / "results_hybrid_openai-gpt.csv") == "hybrid"
    assert compare.mode_of(tmp_path / "results_llm_m.csv") == "llm"


def test_exact_match_and_paraphrase_exact(tmp_path):
    got = column(
        tmp_path, {**BASE, **LLM}, {**BASE, **LLM, "exact_match": "False", "minilang": "", "status": "unsupported",
                                    "category": "rejected"},
        {**BASE, **LLM, "subset": "session"},
    )
    assert got["Exact match"] == "2/3 (66.7%)"
    assert got["Paraphrase exact"] == "1/2 (50.0%)"


def test_would_match_counts_a_derived_question_only_when_yes_gives_the_gold(tmp_path):
    asked = {**BASE, **LLM, "status": "needs_clarification", "minilang": "", "exact_match": "False",
             "category": "unneeded_question", "derived_question": "True"}
    got = column(tmp_path, {**asked, "confirmed_minilang": "x = 1;"}, {**asked, "confirmed_minilang": "x = 2;"})
    assert got["Would match if confirmed"] == "1/2 (50.0%)"
    assert got["Derived-value questions"] == "2"
    assert got["Unnecessary questions"] == "2/2 (100.0%)"


def test_wrong_code_counts_any_code_that_is_not_correct(tmp_path):
    got = column(tmp_path, {**BASE, **LLM}, {**BASE, **LLM, "category": "wrong_code", "minilang": "x = 2;"},
                 {**BASE, **LLM, "expected_status": "unsupported", "subset": "unsupported", "expected_minilang": "",
                  "category": "code_for_unsupported", "minilang": "x = 3;"})
    assert got["Wrong code"] == "2/3 (66.7%)"
    assert got["Safe rejection"] == "0/1 (0.0%)"


def test_ambiguity_precision_and_recall(tmp_path):
    asked = {**BASE, **LLM, "status": "needs_clarification", "minilang": ""}
    got = column(
        tmp_path, {**asked, "expected_status": "ambiguous", "subset": "ambiguous"},
        {**BASE, **LLM, "expected_status": "ambiguous", "subset": "ambiguous", "category": "missed_ambiguity"},
        {**asked, "category": "unneeded_question"},
    )
    assert got["Ambiguity precision"] == "1/2 (50.0%)"
    assert got["Ambiguity recall"] == "1/2 (50.0%)"


def test_llm_activity_and_latency(tmp_path):
    got = column(
        tmp_path, {**BASE, **LLM, "llm_asked": "True", "latency": "1.0", "llm_discarded": "not_grounded bad_slots"},
        {**BASE, **LLM, "llm_asked": "True", "latency": "3.0", "llm_discarded": "not_grounded"},
        {**BASE, **LLM},
    )
    assert got["LLM calls"] == "2"
    assert got["Discarded proposals"] == "bad_slots 1, not_grounded 2"
    assert got["Mean latency (s)"] == "2.000"
    assert got["P95 latency (s)"] == "3.000"


def test_results_written_before_the_latency_column_have_no_latency(tmp_path):
    older = {key: value for key, value in LLM.items() if key != "latency"}
    got = column(tmp_path, {**BASE, **older, "llm_asked": "True"})
    assert got["LLM calls"] == "1"
    assert got["Mean latency (s)"] == "n/a"
    assert got["P95 latency (s)"] == "n/a"


def test_rules_results_have_no_llm_columns(tmp_path):
    got = column(tmp_path, BASE, name="results.csv")
    assert got["LLM calls"] == "n/a"
    assert got["Discarded proposals"] == "n/a"
    assert got["P95 latency (s)"] == "n/a"
    assert got["Would match if confirmed"] == "n/a"


def test_the_table_has_a_column_per_run(tmp_path):
    rules = write(tmp_path / "results.csv", BASE)
    hybrid = write(tmp_path / "results_hybrid_m.csv", {**BASE, **LLM})
    lines = compare.table([rules, hybrid]).splitlines()
    assert lines[0] == "| Measure | rules | hybrid |"
    assert "| Exact match | 1/1 (100.0%) | 1/1 (100.0%) |" in lines


def test_main_prints_the_table(tmp_path, capsys):
    assert compare.main([str(write(tmp_path / "results.csv", BASE))]) == 0
    assert "| Measure | rules |" in capsys.readouterr().out
