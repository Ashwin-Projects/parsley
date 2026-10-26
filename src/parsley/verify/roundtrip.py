"""[N3-V2] Re-parse generated MiniLang and compare ASTs (Phase 7).

``check(source, expected)`` is the V2 layer of ARCHITECTURE.md 2.6. It parses ``source`` with
the Phase 3 parser and compares the result with ``expected`` by dataclass equality. On a
mismatch it returns the path of the first differing node, so the failure is easy to locate
(for example ``Program.statements[0].value.op: expected '+', got '-'``).
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from parsley.compiler.ast_nodes import Program
from parsley.compiler.lexer import LexError
from parsley.compiler.parser import ParseError, parse


def check(source: str, expected: Program) -> str | None:
    """Return ``None`` when ``source`` re-parses to ``expected``, else why it does not."""
    try:
        actual = parse(source)
    except (LexError, ParseError) as error:
        return f"re-parse failed: {error}"
    if actual == expected:
        return None
    return first_difference(expected, actual, "Program") or "the re-parsed AST differs"


def first_difference(expected: object, actual: object, path: str) -> str | None:
    """Describe the first place, in source order, where two trees differ; ``None`` if equal."""
    if type(expected) is not type(actual):
        return f"{path}: expected {_name(expected)}, got {_name(actual)}"
    if is_dataclass(expected):
        for field in fields(expected):
            found = first_difference(
                getattr(expected, field.name), getattr(actual, field.name), f"{path}.{field.name}",
            )
            if found is not None:
                return found
        return None
    if isinstance(expected, tuple) and isinstance(actual, tuple):
        for index, (want, got) in enumerate(zip(expected, actual, strict=False)):
            found = first_difference(want, got, f"{path}[{index}]")
            if found is not None:
                return found
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        return None
    if expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def _name(value: object) -> str:
    return "None" if value is None else type(value).__name__
