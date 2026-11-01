"""run_eval --mode llm|hybrid: separate files, extra metrics, reproducible runs, no network."""

import csv
import json
import shutil
import socket
from pathlib import Path

import pytest

from parsley.eval import run_eval
from parsley.llm.prompt import PROMPT_SHA256

ROOT = Path(__file__).resolve().parents[2]
RECORDED = ROOT / "tests" / "fixtures_llm" / "recorded.json"
SLOT_X = {"name": {"kind": "name", "text": "x"}}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a real socket")
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Development fixtures with an LLM wrong answer, a decline, a failure and a derived amount."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    invalid = json.loads((ROOT / "tests" / "fixtures" / "invalid.json").read_text(encoding="utf-8"))
    invalid["fixtures"] = [f for f in invalid["fixtures"] if f["id"] in ("X01", "X03")]
    (fixtures / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")
    valid = json.loads((ROOT / "tests" / "fixtures" / "valid.json").read_text(encoding="utf-8"))
    valid["fixtures"] = [f for f in valid["fixtures"] if f["id"] == "V01"]
    valid["fixtures"].append({
        **valid["fixtures"][0], "id": "V90", "input": "double x", "rule": "MUL1", "intent": "multiply",
        "given": {"symbols": {"x": "number"}, "ref_stack": ["x"]}, "expected_minilang": "x = x * 2;",
    })
    (fixtures / "valid.json").write_text(json.dumps(valid), encoding="utf-8")
    recorded = tmp_path / "recorded.json"
    recorded.write_text(json.dumps({"model": "test/model:1", "responses": [
        *json.loads(RECORDED.read_text(encoding="utf-8"))["responses"],
        {"sentence": "double x", "readings": [{
            "intent": "multiply", "confidence": 0.9,
            "slots": {**SLOT_X, "amount": {"kind": "number", "text": "2", "derived": True}},
        }]},
    ]}), encoding="utf-8")
    monkeypatch.setenv("PARSLEY_LLM_PROVIDER", "fake")
    monkeypatch.setenv("PARSLEY_LLM_FIXTURES", str(recorded))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def evaluate(workspace, *extra, out="out"):
    return run_eval.main([
        "--root", str(workspace), "--fixtures", str(workspace / "fixtures"), "--out", str(workspace / out),
        "--sets", "development", *extra,
    ])


def summary(workspace, mode="hybrid", out="out"):
    return (workspace / out / f"summary_{mode}_test-model-1.md").read_text(encoding="utf-8")


def rows(workspace, mode="hybrid"):
    with (workspace / "out" / f"results_{mode}_test-model-1.csv").open(encoding="utf-8", newline="") as handle:
        return {row["item_id"]: row for row in csv.DictReader(handle) if row["condition"] == "baseline"}


def test_llm_results_go_to_separate_files_and_never_touch_the_v1_results(workspace):
    out = workspace / "out"
    out.mkdir()
    (out / "results.csv").write_text("v1.1", encoding="utf-8")
    (out / "summary.md").write_text("v1.1", encoding="utf-8")
    assert evaluate(workspace, "--mode", "hybrid") == 0
    assert (out / "results.csv").read_text(encoding="utf-8") == "v1.1"
    assert (out / "summary.md").read_text(encoding="utf-8") == "v1.1"
    assert (out / "results_hybrid_test-model-1.csv").is_file()
    assert (out / "summary_hybrid_test-model-1.md").is_file()


def test_rules_mode_with_the_flag_writes_the_v1_files_only(workspace):
    assert evaluate(workspace, "--mode", "rules") == 0
    assert sorted(p.name for p in (workspace / "out").iterdir()) == ["results.csv", "summary.md"]


def test_wrong_code_is_the_first_thing_in_the_summary(workspace):
    evaluate(workspace, "--mode", "hybrid")
    first = next(line for line in summary(workspace).splitlines() if line and not line.startswith("#"))
    assert first.startswith("**Wrong code: 1/4 (25.0%)")


def test_every_wrong_code_item_is_listed_with_what_the_model_proposed(workspace):
    evaluate(workspace, "--mode", "hybrid")
    text = summary(workspace)
    section = text[text.index("## Wrong-code items"):]
    assert "X01" in section and "store 50 in bonus" in section
    assert "LET bonus = 50;" in section and "create variable bonus with value 50." in section
    assert "LLM" in section


def test_the_llm_metrics_are_reported(workspace):
    evaluate(workspace, "--mode", "hybrid")
    text = summary(workspace)
    assert "| LLM calls | 3 |" in text
    assert "| LLM-sourced accepted items | 1 |" in text
    assert "| Derived-value questions | 1 |" in text
    assert "| Derived questions whose confirmed reading is the gold code | 1/1 (100.0%) |" in text
    assert "| Average latency (seconds) |" in text
    assert "| LLM call failures | 0 |" in text


def test_discards_are_counted_by_reason(tmp_path, workspace, monkeypatch):
    recorded = workspace / "recorded.json"
    data = json.loads(recorded.read_text(encoding="utf-8"))
    for entry in data["responses"]:
        if entry["sentence"] == "define a function called greet":
            entry["readings"] = [{"intent": "exec", "slots": {}, "confidence": 1}]
    recorded.write_text(json.dumps(data), encoding="utf-8")
    evaluate(workspace, "--mode", "hybrid")
    assert "| unknown_intent | 1 |" in summary(workspace)


def test_call_failures_are_prominent(workspace):
    recorded = workspace / "recorded.json"
    data = json.loads(recorded.read_text(encoding="utf-8"))
    data["responses"] = [r for r in data["responses"] if r["sentence"] != "store 50 in bonus"]
    recorded.write_text(json.dumps(data), encoding="utf-8")
    evaluate(workspace, "--mode", "hybrid")
    assert "| LLM call failures | 1 |" in summary(workspace)
    assert "fell back to the rule result" in summary(workspace)


def test_the_summary_records_the_model_prompt_and_tuning_note(workspace):
    evaluate(workspace, "--mode", "llm")
    text = summary(workspace, "llm")
    assert "test/model:1" in text
    assert PROMPT_SHA256 in text
    assert "development fixtures" in text
    assert "held-out" in text


def test_the_csv_carries_the_llm_columns(workspace):
    evaluate(workspace, "--mode", "hybrid")
    table = rows(workspace)
    assert table["X01"]["llm_asked"] == "True"
    assert table["X01"]["llm_accepted"] == "True"
    assert table["V01"]["llm_asked"] == "False"
    assert table["V90"]["derived_question"] == "True"
    assert '"intent": "assign"' in table["X01"]["llm_reading"]


def test_llm_mode_asks_for_every_item_rules_do_not_reject_for_a_reason(workspace):
    evaluate(workspace, "--mode", "llm")
    assert all(row["llm_asked"] == "True" for row in rows(workspace, "llm").values())


def test_a_rerun_from_the_cache_is_identical_and_free(workspace, monkeypatch):
    evaluate(workspace, "--mode", "hybrid", "--cache", str(workspace / "cache"))
    first = {p.name: p.read_bytes() for p in (workspace / "out").iterdir()}
    monkeypatch.setenv("PARSLEY_LLM_FIXTURES", str(workspace / "empty.json"))
    (workspace / "empty.json").write_text('{"model": "test/model:1", "responses": []}', encoding="utf-8")
    assert evaluate(workspace, "--mode", "hybrid", "--cache", str(workspace / "cache")) == 0
    assert {p.name: p.read_bytes() for p in (workspace / "out").iterdir()} == first


def test_record_saves_a_fixture_that_replays_the_same_results(workspace, monkeypatch):
    fixture = workspace / "replay.json"
    evaluate(workspace, "--mode", "hybrid", "--cache", str(workspace / "cache"), "--record", str(fixture))
    first = (workspace / "out" / "results_hybrid_test-model-1.csv").read_bytes()
    monkeypatch.setenv("PARSLEY_LLM_FIXTURES", str(fixture))
    shutil.rmtree(workspace / "out")
    evaluate(workspace, "--mode", "hybrid", "--cache", str(workspace / "cache2"))
    assert (workspace / "out" / "results_hybrid_test-model-1.csv").read_bytes() == first


def test_limit_marks_a_partial_run_in_the_file_name(workspace):
    assert evaluate(workspace, "--mode", "hybrid", "--limit", "2") == 0
    names = sorted(p.name for p in (workspace / "out").iterdir() if p.suffix)
    assert names == ["results_hybrid_test-model-1_limit2.csv", "summary_hybrid_test-model-1_limit2.md"]


def test_an_unconfigured_provider_stops_before_any_results(workspace, monkeypatch, capsys):
    monkeypatch.delenv("PARSLEY_LLM_PROVIDER")
    assert evaluate(workspace, "--mode", "hybrid") == 2
    assert "PARSLEY_LLM_PROVIDER" in capsys.readouterr().err
    assert not list((workspace / "out").glob("results*")) if (workspace / "out").exists() else True


def test_the_rules_evaluation_does_not_import_the_llm_package():
    source = (ROOT / "src" / "parsley" / "eval" / "run_eval.py").read_text(encoding="utf-8")
    top = source[:source.index("CONDITIONS = ")]
    assert "parsley.llm" not in top and "llm_eval" not in top
