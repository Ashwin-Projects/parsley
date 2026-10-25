"""Diagnostic records (level, stage, code, message) shared by every stage (Phase 4).

``Diagnostic`` is a data contract (ARCHITECTURE.md 2.5). The code is the level's letter
(``E``/``W``/``I``) plus three digits; LANGUAGE_SPEC.md 2.2 lists the semantic codes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Level = Literal["error", "warning", "info"]

LEVEL_LETTERS: dict[str, str] = {"error": "E", "warning": "W", "info": "I"}
STAGES = frozenset({
    "normalizer", "candidates", "context", "ambiguity", "ir", "lexer", "parser",
    "semantic", "codegen", "verify", "cli",
})
CODE = re.compile(r"[EWI]\d{3}")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One plain-English message from one stage; any ``error`` fails the run."""

    level: Level
    stage: str
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.level not in LEVEL_LETTERS:
            raise ValueError(f"unknown diagnostic level {self.level!r}")
        if self.stage not in STAGES:
            raise ValueError(f"unknown diagnostic stage {self.stage!r}")
        if not CODE.fullmatch(self.code) or self.code[0] != LEVEL_LETTERS[self.level]:
            raise ValueError(f"code {self.code!r} does not fit level {self.level!r}")


def has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    """True when any diagnostic is an error."""
    return any(d.level == "error" for d in diagnostics)
