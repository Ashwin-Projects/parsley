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
    return first_difference(expected, actual, "Program")


def first_difference(expected: object, actual: object, path: str) -> str | None:
    """Describe the first place, in source order, where two trees differ; ``None`` if equal."""
    # The same field-by-field equality as the frozen dataclasses, but with an
    # explicit stack: long left-associative expressions must not exhaust Python's.
    pending = [(expected, actual, path)]
    while pending:
        want, got, location = pending.pop()
        if type(want) is not type(got):
            return f"{location}: expected {_name(want)}, got {_name(got)}"
        if is_dataclass(want):
            pending.extend(
                (getattr(want, field.name), getattr(got, field.name), f"{location}.{field.name}")
                for field in reversed(fields(want))
            )
        elif isinstance(want, tuple) and isinstance(got, tuple):
            if len(want) != len(got):
                return f"{location}: expected {len(want)} items, got {len(got)}"
            pending.extend(
                (want[index], got[index], f"{location}[{index}]")
                for index in reversed(range(len(want)))
            )
        elif want != got:
            return f"{location}: expected {want!r}, got {got!r}"
    return None


def _name(value: object) -> str:
    return "None" if value is None else type(value).__name__
