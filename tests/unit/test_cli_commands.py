"""v1.1 CLI: --run, --version and the REPL ":" commands, wired to the real pipeline."""

import tomllib
from pathlib import Path
from unittest.mock import Mock

import pytest

from parsley import cli

ROOT = Path(__file__).resolve().parents[2]


def repl(monkeypatch: pytest.MonkeyPatch, *lines: str) -> int:
    monkeypatch.setattr("builtins.input", Mock(side_effect=[*lines, EOFError]))
    return cli.main([])


# --version


def test_version_prints_the_pyproject_version(capsys) -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"parsley {version}"


# --run


def test_run_flag_executes_the_file_program(tmp_path: Path, capsys) -> None:
    source = tmp_path / "program.txt"
    source.write_text("let score be 10\nadd 5 to it\nprint score\nrepeat 2 times print hi\n", encoding="utf-8")
    assert cli.main(["--file", str(source), "--run"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("Output:\n  15\n  hi\n  hi\n")


def test_run_flag_with_one_sentence(capsys) -> None:
    assert cli.main(['print "hello"', "--run"]) == 0
    assert capsys.readouterr().out.endswith("Output:\n  hello\n")


def test_run_reports_a_program_that_prints_nothing(capsys) -> None:
    assert cli.main(["let x be 1", "--run"]) == 0
    assert capsys.readouterr().out.endswith("Output: (nothing printed)\n")


def test_run_reports_runtime_errors_and_fails(tmp_path: Path, capsys) -> None:
    source = tmp_path / "program.txt"
    source.write_text("let x be 0\nlet y be 5\nprint y\ndivide y by x\n", encoding="utf-8")
    status = cli.main(["--file", str(source), "--run"])
    output = capsys.readouterr()
    assert "Output:\n  5\n" in output.out
    assert "runtime error:" in output.err
    assert status == 1


def test_run_never_changes_code_generation(tmp_path: Path, capsys) -> None:
    source = tmp_path / "program.txt"
    source.write_text("let x be 2\nprint x\n", encoding="utf-8")
    destination = tmp_path / "out.mini"
    assert cli.main(["--file", str(source), "--output", str(destination), "--run"]) == 0
    assert destination.read_text(encoding="utf-8") == "LET x = 2;\nPRINT x;\n"


# REPL commands


def test_repl_run_executes_the_program_so_far(monkeypatch, capsys) -> None:
    assert repl(monkeypatch, "let x be 3", "print x", ":run") == 0
    assert capsys.readouterr().out.endswith("Output:\n  3\n")


def test_repl_run_with_nothing_accepted(monkeypatch, capsys) -> None:
    assert repl(monkeypatch, ":run") == 0
    assert "Nothing to run yet." in capsys.readouterr().out


def test_repl_program_lists_accepted_minilang(monkeypatch, capsys) -> None:
    assert repl(monkeypatch, "let x be 3", "bad input here", "increase x by 2", ":program") == 1
    assert capsys.readouterr().out.endswith("LET x = 3;\nx = x + 2;\n")


def test_repl_program_when_empty(monkeypatch, capsys) -> None:
    repl(monkeypatch, ":program")
    assert "(no statements yet)" in capsys.readouterr().out


def test_repl_undo_removes_the_last_statement_and_restores_state(monkeypatch, capsys) -> None:
    # After undo, y no longer exists and "it" refers to x again.
    assert repl(monkeypatch, "let x be 1", "let y be 2", ":undo", "add 5 to it", "print y", ":program") == 0
    out = capsys.readouterr().out
    assert "Undid: LET y = 2;" in out
    assert out.endswith('LET x = 1;\nx = x + 5;\nPRINT "y";\n')


def test_repl_undo_with_nothing_to_undo(monkeypatch, capsys) -> None:
    repl(monkeypatch, ":undo")
    assert "Nothing to undo." in capsys.readouterr().out


def test_repl_reset_clears_the_session(monkeypatch, capsys) -> None:
    repl(monkeypatch, "let x be 1", ":reset", "print x", ":program")
    out = capsys.readouterr().out
    assert "Session cleared." in out
    assert out.endswith('PRINT "x";\n')  # x is no longer a variable


def test_repl_quit_stops_reading(monkeypatch, capsys) -> None:
    read = Mock(side_effect=["let x be 1", ":quit", "print x", EOFError])
    monkeypatch.setattr("builtins.input", read)
    assert cli.main([]) == 0
    assert read.call_count == 2


def test_repl_help_lists_commands_and_example_phrasings(monkeypatch, capsys) -> None:
    repl(monkeypatch, ":help")
    out = capsys.readouterr().out
    for command in (":run", ":program", ":undo", ":reset", ":quit", ":help"):
        assert command in out
    examples = [line.strip() for line in out.splitlines() if line.startswith("    ")]
    assert 8 <= len(examples) <= 10
    session = cli.Session()
    for example in examples:  # every example works, in order, as one session
        assert cli.pipeline.run(example, session).status == "ok", example


def test_repl_commands_ignore_case_and_spaces(monkeypatch, capsys) -> None:
    repl(monkeypatch, "let x be 1", "  :PROGRAM  ")
    assert capsys.readouterr().out.endswith("LET x = 1;\n")


def test_repl_unknown_command_is_reported_not_compiled(monkeypatch, capsys) -> None:
    assert repl(monkeypatch, ":frobnicate") == 0
    output = capsys.readouterr()
    assert "Unknown command :frobnicate" in output.err
    assert "candidates" not in output.err
