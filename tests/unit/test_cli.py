"""Phase 0 smoke test: the placeholder CLI echoes its input and exits 0."""

from parsley.cli import main


def test_cli_echoes_input(capsys):
    assert main(["set", "age", "to", "21"]) == 0
    assert capsys.readouterr().out == "set age to 21\n"
