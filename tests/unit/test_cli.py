"""CLI modes and exit codes, with the pipeline boundary mocked."""

from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

import pytest

from parsley import cli


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(return_value=0)
    monkeypatch.setattr(cli, "run_sentence", mock, raising=False)
    return mock


def test_sentence_and_default_options(runner: Mock, capsys) -> None:
    assert cli.main(["print Hello"]) == 0
    text, options = runner.call_args.args
    assert text == "print Hello"
    assert options.trace is False
    assert options.output is None
    assert options.confirm is False
    assert options.no_context is False
    assert options.interactive is False
    assert options.session is None
    assert capsys.readouterr().out == ""


def test_all_flags_reach_runner(runner: Mock) -> None:
    assert cli.main([
        "--trace", "--output", "result.mini", "--confirm", "--no-context",
        "print Hello",
    ]) == 0
    options = runner.call_args.args[1]
    assert options.trace is True
    assert options.output == Path("result.mini")
    assert options.confirm is True
    assert options.no_context is True


@pytest.mark.parametrize(
    "argv",
    [["--unknown"], ["--file"], ["--output"],
     ["print hello", "print goodbye"],
     ["print hello", "--file", "input.txt"]],
)
def test_invalid_arguments_exit_two(
    argv: list[str], runner: Mock, capsys,
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2
    runner.assert_not_called()
    assert "error:" in capsys.readouterr().err


def test_help_exits_zero(runner: Mock, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    runner.assert_not_called()
    output = capsys.readouterr().out
    for flag in ("--file", "--trace", "--output", "--confirm", "--no-context"):
        assert flag in output


def test_file_lines_share_session(tmp_path: Path, runner: Mock) -> None:
    source = tmp_path / "sentences.txt"
    source.write_text('let x be 1\n\n  \nprint "café"\n', encoding="utf-8")
    session = object()
    seen = []

    def process(text: str, options: Namespace) -> int:
        seen.append((text, options.session))
        options.session = session
        return 0

    runner.side_effect = process
    assert cli.main(["--file", str(source), "--trace"]) == 0
    assert seen == [("let x be 1", None), ('print "café"', session)]
    first, second = runner.call_args_list
    assert first.args[1] is second.args[1]
    assert second.args[1].interactive is False
    assert second.args[1].trace is True


def test_file_error_is_retained_after_later_success(
    tmp_path: Path, runner: Mock,
) -> None:
    source = tmp_path / "sentences.txt"
    source.write_text("bad\nprint hello\n", encoding="utf-8")
    runner.side_effect = [1, 0]
    assert cli.main(["--file", str(source)]) == 1
    assert runner.call_count == 2


def test_missing_file_is_an_error(
    tmp_path: Path, runner: Mock, capsys,
) -> None:
    assert cli.main(["--file", str(tmp_path / "missing.txt")]) == 1
    runner.assert_not_called()
    output = capsys.readouterr()
    assert output.out == ""
    assert "cli" in output.err and "read" in output.err.lower()


def test_invalid_utf8_file_is_an_error(
    tmp_path: Path, runner: Mock, capsys,
) -> None:
    source = tmp_path / "invalid.txt"
    source.write_bytes(b"\xff\n")
    assert cli.main(["--file", str(source)]) == 1
    assert capsys.readouterr().out == ""
    runner.assert_not_called()


def test_empty_file_is_a_successful_noop(
    tmp_path: Path, runner: Mock,
) -> None:
    source = tmp_path / "empty.txt"
    source.write_text("\n  \n", encoding="utf-8")
    assert cli.main(["--file", str(source)]) == 0
    runner.assert_not_called()


def test_repl_shares_session_and_skips_blank_input(
    monkeypatch: pytest.MonkeyPatch, runner: Mock,
) -> None:
    read = Mock(side_effect=["", "  ", "let x be 1", "print x", EOFError])
    monkeypatch.setattr("builtins.input", read)
    session = object()
    seen = []

    def process(text: str, options: Namespace) -> int:
        seen.append((text, options.session))
        options.session = session
        return 0

    runner.side_effect = process
    assert cli.main(["--confirm"]) == 0
    assert seen == [("let x be 1", None), ("print x", session)]
    first, second = runner.call_args_list
    assert first.args[1] is second.args[1]
    assert second.args[1].interactive is True
    assert second.args[1].confirm is True


def test_repl_retains_error_status(
    monkeypatch: pytest.MonkeyPatch, runner: Mock,
) -> None:
    monkeypatch.setattr(
        "builtins.input", Mock(side_effect=["bad", "print hello", EOFError]),
    )
    runner.side_effect = [1, 0]
    assert cli.main([]) == 1
    assert runner.call_count == 2


def test_repl_eof_is_success(
    monkeypatch: pytest.MonkeyPatch, runner: Mock,
) -> None:
    monkeypatch.setattr("builtins.input", Mock(side_effect=EOFError))
    assert cli.main([]) == 0
    runner.assert_not_called()


def test_interrupt_exits_130(
    monkeypatch: pytest.MonkeyPatch, runner: Mock, capsys,
) -> None:
    monkeypatch.setattr("builtins.input", Mock(side_effect=KeyboardInterrupt))
    assert cli.main([]) == 130
    runner.assert_not_called()
    assert "interrupt" in capsys.readouterr().err.lower()


def test_sentence_error_exits_nonzero_without_success(
    runner: Mock, capsys,
) -> None:
    runner.return_value = 1
    assert cli.main(["bad sentence"]) == 1
    assert capsys.readouterr().out == ""


def test_runner_exception_exits_nonzero_without_traceback(
    runner: Mock, capsys,
) -> None:
    runner.side_effect = RuntimeError("pipeline failed")
    assert cli.main(["print hello"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "pipeline failed" in output.err
    assert "Traceback" not in output.err


def test_failed_sentence_does_not_create_output(
    tmp_path: Path, capsys,
) -> None:
    destination = tmp_path / "result.mini"
    assert cli.main(["sort the list descending", "--output", str(destination)]) == 1
    output = capsys.readouterr()
    assert "MiniLang" not in output.out
    assert "candidates E101" in output.err
    assert not destination.exists()


# Wired to the real pipeline (no mock)


def test_sentence_prints_back_translation_and_minilang(capsys) -> None:
    assert cli.main(["make a variable called age and set it to 20"]) == 0
    out = capsys.readouterr().out
    assert "I understood: create variable age with value 20." in out
    assert "MiniLang: LET age = 20;" in out


def test_file_mode_shares_one_session_and_writes_the_program(
    tmp_path: Path, capsys,
) -> None:
    source = tmp_path / "program.txt"
    source.write_text(
        "make a variable called score and set it to 10\nadd 5 to it\nprint score\n",
        encoding="utf-8",
    )
    destination = tmp_path / "out.mini"
    assert cli.main(["--file", str(source), "--output", str(destination)]) == 0
    assert destination.read_text(encoding="utf-8") == (
        "LET score = 10;\nscore = score + 5;\nPRINT score;\n"
    )


def test_warning_is_shown_but_succeeds(capsys) -> None:
    assert cli.main(["set x to 5"]) == 0
    output = capsys.readouterr()
    assert "context W301" in output.err
    assert "MiniLang: LET x = 5;" in output.out


def test_semantic_error_exits_nonzero_without_minilang(capsys) -> None:
    assert cli.main(["print x times 2"]) == 1
    output = capsys.readouterr()
    assert "semantic E201: x is used before it is created" in output.err
    assert "MiniLang" not in output.out


def test_clarification_question_exits_nonzero(capsys) -> None:
    assert cli.main(["increase score"]) == 1
    output = capsys.readouterr()
    assert "By how much should score increase?" in output.err
    assert "MiniLang" not in output.out


def test_trace_shows_candidates_decision_and_ast(capsys) -> None:
    assert cli.main(["--trace", "set x to 5"]) == 0
    out = capsys.readouterr().out
    assert "input: set x to 5" in out
    assert "S1" in out and "assign" in out
    assert "decision: ACCEPT" in out
    assert "Let(name='x', value=Num(text='5'))" in out


def test_no_context_makes_unresolved_words_an_error(capsys) -> None:
    assert cli.main(["--no-context", "print hello"]) == 1
    output = capsys.readouterr()
    assert "ir E401" in output.err
    assert "MiniLang" not in output.out


def test_no_context_still_compiles_context_free_input(capsys) -> None:
    assert cli.main(["--no-context", 'print "hello"']) == 0
    assert 'MiniLang: PRINT "hello";' in capsys.readouterr().out
