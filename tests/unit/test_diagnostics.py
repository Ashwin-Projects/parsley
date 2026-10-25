"""Diagnostic record (ARCHITECTURE.md 2.5): level, stage, code, plain-English message."""

import dataclasses

import pytest

from parsley.diagnostics import Diagnostic, has_errors


def test_fields_are_kept():
    d = Diagnostic("error", "semantic", "E201", "score is used before it is created")
    assert (d.level, d.stage, d.code, d.message) == (
        "error", "semantic", "E201", "score is used before it is created",
    )


def test_is_frozen():
    d = Diagnostic("warning", "semantic", "W208", "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.code = "W209"  # type: ignore[misc]


@pytest.mark.parametrize("level", ["fatal", "Error", ""])
def test_unknown_level_is_rejected(level):
    with pytest.raises(ValueError):
        Diagnostic(level, "semantic", "E201", "m")  # type: ignore[arg-type]


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError):
        Diagnostic("error", "typechecker", "E201", "m")


@pytest.mark.parametrize("code", ["E20", "E2011", "201", "X201", "e201"])
def test_malformed_code_is_rejected(code):
    with pytest.raises(ValueError):
        Diagnostic("error", "semantic", code, "m")


@pytest.mark.parametrize("level,code", [("error", "W208"), ("warning", "E201"), ("info", "E201")])
def test_code_letter_must_match_level(level, code):
    with pytest.raises(ValueError):
        Diagnostic(level, "semantic", code, "m")


def test_has_errors():
    warning = Diagnostic("warning", "semantic", "W208", "m")
    error = Diagnostic("error", "semantic", "E201", "m")
    assert not has_errors([])
    assert not has_errors([warning])
    assert has_errors([warning, error])
