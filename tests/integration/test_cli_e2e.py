"""Subprocess acceptance tests for the public ``python -m parsley`` CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "examples" / "valid"
VALID_SESSIONS = sorted(VALID.glob("*.txt"))
IMPLICIT_SESSIONS = sorted(VALID.glob("implicit-pronoun-*.txt"))
FIXTURES = {
    fixture["id"]: fixture
    for fixture in json.loads(
        (ROOT / "tests" / "fixtures" / "valid.json")
        .read_text(encoding="utf-8")
    )["fixtures"]
}


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the real module entry point from this checkout, without a shell."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "parsley", *arguments],
        cwd=ROOT,
        env=env,
        input="",
        capture_output=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


def _program(stdout: str) -> str:
    """Extract program lines, preserving their exact canonical formatting."""
    lines = [
        line.removeprefix("MiniLang: ")
        for line in stdout.splitlines()
        if line.startswith("MiniLang: ")
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def test_example_discovery_covers_valid_and_implicit_sessions() -> None:
    assert VALID_SESSIONS, "No valid example sessions were discovered"
    assert len(IMPLICIT_SESSIONS) >= 2
    for source in VALID_SESSIONS:
        assert source.with_suffix(".expected").is_file(), source


def test_single_sentence_prints_expected_minilang() -> None:
    fixture = FIXTURES["V01"]
    result = _cli(fixture["input"])
    assert result.returncode == 0, result.stderr
    assert _program(result.stdout) == fixture["expected_minilang"] + "\n"
    assert result.stderr == ""


@pytest.mark.parametrize("source", VALID_SESSIONS, ids=lambda path: path.stem)
def test_file_mode_matches_valid_example(source: Path) -> None:
    result = _cli("--file", str(source))
    assert result.returncode == 0, result.stderr
    expected = source.with_suffix(".expected").read_text(encoding="utf-8")
    assert _program(result.stdout) == expected


@pytest.mark.parametrize(
    "source", IMPLICIT_SESSIONS, ids=lambda path: path.stem,
)
def test_output_file_contains_the_whole_program(
    source: Path, tmp_path: Path,
) -> None:
    destination = tmp_path / "program.mini"
    result = _cli("--file", str(source), "--output", str(destination))
    assert result.returncode == 0, result.stderr
    assert destination.read_text(encoding="utf-8") == (
        source.with_suffix(".expected").read_text(encoding="utf-8")
    )


def test_single_sentence_output_file(tmp_path: Path) -> None:
    destination = tmp_path / "program.mini"
    fixture = FIXTURES["V01"]
    result = _cli(fixture["input"], "--output", str(destination))
    assert result.returncode == 0, result.stderr
    assert destination.read_text(encoding="utf-8") == (
        fixture["expected_minilang"] + "\n"
    )


def test_failed_sentence_writes_no_file(tmp_path: Path) -> None:
    destination = tmp_path / "failed.mini"
    result = _cli("print x times 2", "--output", str(destination))
    assert result.returncode == 1, result.stderr
    assert "E201" in result.stderr
    assert not destination.exists()
    assert _program(result.stdout) == ""
    assert "I understood:" not in result.stdout


def test_trace_contains_candidates_decision_and_ast() -> None:
    result = _cli("--trace", FIXTURES["V01"]["input"])
    assert result.returncode == 0, result.stderr
    assert "candidates:" in result.stdout
    assert "D1 declare" in result.stdout
    assert "decision: ACCEPT" in result.stdout
    assert "AST: Let(name='age', value=Num(text='20'))" in result.stdout


@pytest.mark.parametrize(
    "source", IMPLICIT_SESSIONS, ids=lambda path: path.stem,
)
def test_no_context_rejects_implicit_pronoun_sessions(source: Path) -> None:
    result = _cli("--no-context", "--file", str(source))
    assert result.returncode == 1, result.stderr
    assert "ir E401" in result.stderr
    assert _program(result.stdout) == ""


def test_unsupported_input_reports_reason_code() -> None:
    result = _cli("sort the list descending")
    assert result.returncode == 1, result.stderr
    assert "E101" in result.stderr
    assert "NO_MATCH" in result.stderr
    assert _program(result.stdout) == ""
    assert "I understood:" not in result.stdout
