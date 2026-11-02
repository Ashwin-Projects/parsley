"""Recorded model responses replay offline to the committed evaluation results.

``tests/fixtures_llm/recorded_<mode>.json`` and ``tests/golden/<mode>_results.csv`` come from one
real run, ``run_eval --sets held_out --mode <mode> --record``. A mode that has not been recorded
is skipped, and says so. Latency is left out: a replay makes no real call.
"""

import csv
import json
from pathlib import Path

import pytest

from parsley.eval import run_eval
from parsley.llm.prompt import PROMPT_SHA256

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return [{key: value for key, value in row.items() if key != "latency"} for row in csv.DictReader(handle)]


@pytest.mark.parametrize("mode", ["hybrid", "llm"])
def test_a_recorded_run_replays_to_its_results(mode, tmp_path, monkeypatch):
    recorded = ROOT / "tests" / "fixtures_llm" / f"recorded_{mode}.json"
    if not recorded.is_file():
        pytest.skip(f"no real {mode} run has been recorded")
    data = json.loads(recorded.read_text(encoding="utf-8"))
    assert data["prompt_sha256"] == PROMPT_SHA256, "the prompt changed, so record the run again"
    monkeypatch.setenv("PARSLEY_LLM_PROVIDER", "fake")
    monkeypatch.setenv("PARSLEY_LLM_FIXTURES", str(recorded))
    assert run_eval.main(["--root", str(ROOT), "--sets", "held_out", "--mode", mode, "--out", str(tmp_path)]) == 0
    replayed = next(tmp_path.glob(f"results_{mode}_*.csv"))
    rows = read(replayed)
    assert any(row["llm_asked"] == "True" and row["llm_failed"] == "False" for row in rows), "nothing was replayed"
    assert rows == read(ROOT / "tests" / "golden" / f"{mode}_results.csv")
