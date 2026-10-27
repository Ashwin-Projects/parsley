"""eval/run_eval.py: real pipeline, three conditions, honest outcomes, reproducible output."""

import csv
import json
from pathlib import Path

import pytest

from parsley.eval import run_eval
from parsley.eval.dataset import Item

ROOT = Path(__file__).resolve().parents[2]


def item(input_, *, expected_status="ok", expected_minilang=None, setup=(), setup_minilang=(),
         subset="valid", item_id="T1", expected_suggestion=None):
    return Item(
        id=item_id, source="held_out", subset=subset, group=None, input=input_, setup=tuple(setup),
        setup_minilang=tuple(setup_minilang), expected_status=expected_status,
        expected_minilang=expected_minilang, expected_suggestion=expected_suggestion,
        expected_codes=(), context=None,
    )


def test_baseline_correct_translation():
    o = run_eval.evaluate(item("let x be 1", expected_minilang="LET x = 1;"), "baseline")
    assert (o.status, o.minilang, o.condition) == ("ok", "LET x = 1;", "baseline")
    assert o.ast_key == o.gold_key


def test_forced_top1_answers_the_question_with_the_first_option():
    ambiguous = item("set x to 10 or 20", expected_status="ambiguous")
    assert run_eval.evaluate(ambiguous, "baseline").status == "needs_clarification"
    forced = run_eval.evaluate(ambiguous, "forced_top1")
    assert forced.status == "ok" and forced.minilang == "LET x = 10;"


def test_forced_top1_cannot_invent_a_missing_value():
    missing = item("increase score", expected_status="ambiguous", setup=("let score be 0",),
                   setup_minilang=("LET score = 0;",))
    assert run_eval.evaluate(missing, "forced_top1").status == "needs_clarification"


def test_context_off_changes_only_the_evaluated_sentence():
    # The setup always runs with context on; only the target sentence is ablated.
    pronoun = item("add 2 to it", expected_minilang="x = x + 2;", setup=("let x be 1",),
                   setup_minilang=("LET x = 1;",))
    assert run_eval.evaluate(pronoun, "baseline").minilang == "x = x + 2;"
    assert run_eval.evaluate(pronoun, "context_off").status != "ok"


def test_rejected_input_with_a_known_meaning_judges_the_suggestion_by_running_it():
    o = run_eval.evaluate(item("store 50 in bonus", expected_minilang="LET bonus = 50;"), "baseline")
    assert o.status == "unsupported" and o.suggestion == "set bonus to 50"
    assert o.suggestion_useful is True


def test_rejected_input_with_an_expected_suggestion_compares_the_text():
    o = run_eval.evaluate(item("store 50 in bonus", expected_status="unsupported",
                               expected_suggestion="set bonus to 50"), "baseline")
    assert o.suggestion_useful is True
    o = run_eval.evaluate(item("sort the list", expected_status="unsupported"), "baseline")
    assert o.suggestion_useful is None


def test_setup_that_does_not_reproduce_its_gold_is_a_setup_failure():
    o = run_eval.evaluate(item("print x", expected_minilang="PRINT x;", setup=("let x be 1",),
                               setup_minilang=("LET x = 2;",)), "baseline")
    assert o.status == "setup_failed"


def test_a_crash_is_recorded_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(run_eval, "run", boom)
    assert run_eval.evaluate(item("let x be 1", expected_minilang="LET x = 1;"), "baseline").status == "crash"


def _tiny_data(tmp_path):
    data, fixtures = tmp_path / "eval_data", tmp_path / "fixtures"
    data.mkdir(), fixtures.mkdir()
    (data / "valid.json").write_text(json.dumps({"version": 1, "category": "valid", "fixtures": [
        {"id": "HV1", "given": {"symbols": {}, "ref_stack": []}, "input": "let x be 1",
         "expected_minilang": "LET x = 1;"},
        {"id": "HV2", "given": {"symbols": {}, "ref_stack": []}, "input": "store 5 in y",
         "expected_minilang": "LET y = 5;"},
    ]}), encoding="utf-8")
    (fixtures / "ambiguous.json").write_text(json.dumps({"version": 1, "category": "ambiguous", "fixtures": [
        {"id": "A1", "given": {"symbols": {}, "ref_stack": []}, "input": "set x to 10 or 20",
         "expected_status": "ambiguous"},
    ]}), encoding="utf-8")
    return data, fixtures


def test_main_writes_csv_and_summary_reproducibly(tmp_path):
    data, fixtures = _tiny_data(tmp_path)
    out = tmp_path / "results"
    args = ["--data", str(data), "--fixtures", str(fixtures), "--out", str(out), "--root", str(ROOT)]
    assert run_eval.main(args) == 0
    summary, table = (out / "summary.md").read_bytes(), (out / "results.csv").read_bytes()
    assert run_eval.main(args) == 0
    assert (out / "summary.md").read_bytes() == summary and (out / "results.csv").read_bytes() == table

    rows = list(csv.DictReader((out / "results.csv").open(encoding="utf-8", newline="")))
    held = [r for r in rows if r["source"] == "held_out"]
    assert {(r["item_id"], r["condition"]) for r in held} == {
        (i, c) for i in ("HV1", "HV2") for c in ("baseline", "context_off", "forced_top1")
    }
    assert any(r["source"] == "mutation" for r in rows)

    text = summary.decode("utf-8")
    for heading in ("## Held-out results", "## Ablations", "## Failures by category",
                    "## Mutation detection by layer", "## Development fixtures (not held-out)"):
        assert heading in text
    assert "exact-match accuracy" in text and "1/2 (50.0%)" in text
    assert "rejected" in text  # HV2 is a failure and is reported, not hidden


def test_main_without_mutation_operators_says_so(tmp_path):
    data, fixtures = _tiny_data(tmp_path)
    out = tmp_path / "results"
    assert run_eval.main(["--data", str(data), "--fixtures", str(fixtures), "--out", str(out),
                          "--root", str(tmp_path)]) == 0
    assert "mutation operators not found" in (out / "summary.md").read_text(encoding="utf-8")


def test_main_refuses_a_changed_frozen_file(tmp_path, capsys):
    data, fixtures = _tiny_data(tmp_path)
    (data / "valid.sha256").write_text("0" * 64 + "  valid.json\n")
    assert run_eval.main(["--data", str(data), "--fixtures", str(fixtures), "--out", str(tmp_path / "r")]) == 2
    assert "digest" in capsys.readouterr().err


def test_human_blind_set_is_reported_in_its_own_section_and_not_in_the_headline(tmp_path):
    data, fixtures = _tiny_data(tmp_path)
    (data / "human_blind.json").write_text(json.dumps({"version": 1, "category": "human_blind", "cases": [
        {"id": "HB01", "setup": [], "setup_minilang": "", "input": "let z be 3",
         "expected_status": "ok", "expected_minilang": "LET z = 3;"},
    ]}), encoding="utf-8")
    out = tmp_path / "results"
    assert run_eval.main(["--data", str(data), "--fixtures", str(fixtures), "--out", str(out),
                          "--root", str(ROOT)]) == 0
    text = (out / "summary.md").read_text(encoding="utf-8")
    held, _, rest = text.partition("## Human blind set")
    assert rest, "missing human blind section"
    blind = rest.split("\n## ")[0]
    assert "| exact-match accuracy | 1/1 (100.0%) | human_blind |" in blind
    assert "human_blind" not in held.split("## Held-out results")[1]  # headline excludes it
    assert "| exact-match accuracy | 1/2 (50.0%) | all with gold code |" in held
    rows = list(csv.DictReader((out / "results.csv").open(encoding="utf-8", newline="")))
    assert {r["condition"] for r in rows if r["subset"] == "human_blind"} == set(run_eval.CONDITIONS)


def test_without_a_human_blind_file_the_section_says_so(tmp_path):
    data, fixtures = _tiny_data(tmp_path)
    out = tmp_path / "results"
    run_eval.main(["--data", str(data), "--fixtures", str(fixtures), "--out", str(out), "--root", str(ROOT)])
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert "## Human blind set" in text and "Not provided" in text
