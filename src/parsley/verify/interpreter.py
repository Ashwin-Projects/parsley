"""[N3-V3] MiniLang interpreter over parsed code; independent of ast_eval.py (Phase 7).

``run(source)`` parses MiniLang text with the Phase 3 parser and walks the tree it got back.
It never sees the original AST and shares no evaluation code with ``ast_eval.py`` (CLAUDE.md
rule 5); the two agree only through the run-time rules written in ``ast_eval``'s docstring,
and V3 exists to check that they really do.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from typing import Any

import parsley.compiler.ast_nodes as nodes
from parsley.compiler.lexer import LexError
from parsley.compiler.parser import ParseError, parse

LOOP_LIMIT = 1000

_WHOLE_NUMBER = re.compile(r"[0-9]+")
_PLAIN: dict[str, Callable[[Any, Any], Any]] = {
    "+": operator.add, "-": operator.sub, "*": operator.mul,
}
_ORDER: dict[str, Callable[[Any, Any], bool]] = {
    ">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le,
    "==": operator.eq, "!=": operator.ne,
}


class _Fault(Exception):
    """A run-time error: reported in ``errors``, ends the current top-level statement."""


def run(source: str) -> tuple[dict[str, object], list[str], list[str]]:
    """Parse and run ``source``; returns ``(variables, output, errors)``.

    A program that does not parse runs nothing and reports one ``syntax error: ...``.
    """
    try:
        tree = parse(source)
    except (LexError, ParseError) as error:
        return {}, [], [f"syntax error: {error}"]
    machine = _Machine()
    for statement in tree.statements:
        machine.top_level(statement)
    return machine.memory, machine.printed, machine.problems


class _Machine:
    """Executes parsed nodes by dispatching on the node's class name."""

    def __init__(self) -> None:
        self.memory: dict[str, object] = {}
        self.printed: list[str] = []
        self.problems: list[str] = []

    def top_level(self, node: object) -> None:
        try:
            self.step(node)
        except _Fault as fault:
            self.problems.append(fault.args[0])
        except (OverflowError, ValueError):
            self.problems.append("number out of range")

    def step(self, node: object) -> None:
        getattr(self, f"do_{type(node).__name__}")(node)

    def value(self, node: object) -> object:
        return getattr(self, f"eval_{type(node).__name__}")(node)

    # Statements

    def do_Let(self, node: nodes.Let) -> None:
        self.memory[node.name] = self.value(node.value)

    def do_Assign(self, node: nodes.Assign) -> None:
        new_value = self.value(node.value)
        if node.name not in self.memory:
            raise _Fault(f"undefined variable: {node.name}")
        self.memory[node.name] = new_value

    def do_Print(self, node: nodes.Print) -> None:
        shown = self.value(node.value)
        self.printed.append(f"{shown!r}" if isinstance(shown, float) else f"{shown}")

    def do_If(self, node: nodes.If) -> None:
        chosen = node.then_body if self.test(node.condition) else (node.else_body or ())
        for inner in chosen:
            self.step(inner)

    def do_Repeat(self, node: nodes.Repeat) -> None:
        text = node.count.text
        if _WHOLE_NUMBER.fullmatch(text) is None or int(text) == 0:
            raise _Fault(f"invalid REPEAT count: {text}")
        for _ in range(min(int(text), LOOP_LIMIT)):
            for inner in node.body:
                self.step(inner)

    # Expressions

    def eval_Num(self, node: nodes.Num) -> object:
        return float(node.text) if node.text.count(".") else int(node.text)

    def eval_Str(self, node: nodes.Str) -> object:
        return node.value

    def eval_Var(self, node: nodes.Var) -> object:
        try:
            return self.memory[node.name]
        except KeyError:
            raise _Fault(f"undefined variable: {node.name}") from None

    def eval_Neg(self, node: nodes.Neg) -> object:
        inner = self.value(node.operand)
        if type(inner) is str:
            raise _Fault("type error: cannot negate text")
        return 0 - inner  # type: ignore[operator]

    def eval_BinOp(self, node: nodes.BinOp) -> object:
        lhs, rhs = self.value(node.left), self.value(node.right)
        texts = [type(side) is str for side in (lhs, rhs)]
        if any(texts):
            if node.op == "+" and all(texts):
                return "".join((lhs, rhs))  # type: ignore[arg-type]
            raise _Fault(f"type error: cannot apply '{node.op}' to {_name(lhs)} and {_name(rhs)}")
        if node.op in _PLAIN:
            return _PLAIN[node.op](lhs, rhs)
        if rhs == 0:
            raise _Fault("division by zero")
        if type(lhs) is int and type(rhs) is int:
            quotient, remainder = divmod(lhs, rhs)
            return quotient if remainder == 0 else lhs / rhs
        return lhs / rhs  # type: ignore[operator]

    def test(self, condition: nodes.Compare) -> bool:
        lhs, rhs = self.value(condition.left), self.value(condition.right)
        mixed = type(lhs) is str or type(rhs) is str
        if mixed and not (type(lhs) is str and type(rhs) is str and condition.op in ("==", "!=")):
            raise _Fault(f"type error: cannot compare {_name(lhs)} and {_name(rhs)} with '{condition.op}'")
        return _ORDER[condition.op](lhs, rhs)


def _name(value: object) -> str:
    return "text" if type(value) is str else "number"
