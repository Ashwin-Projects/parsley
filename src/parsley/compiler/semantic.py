"""[E] Semantic analyzer; the only writer of the symbol table (Phase 4).

``analyze(stmt, session)`` checks one statement against the session and returns its
diagnostics in source order (codes in LANGUAGE_SPEC.md 2.2). A statement with no errors is
then recorded: a declaration goes into the symbol table, the statement is appended to the
history, and the names it used move to the top of the reference stack. A statement with an
error changes nothing. Warnings do not block recording.

Types follow LANGUAGE_SPEC.md 2. A variable keeps its type; only a new top-level ``LET``
changes it. An expression whose type is unknown (an undefined name, or a sub-expression
that already failed) is not type-checked against its neighbours, so a failure does not
cascade into further type errors.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, Expr, If, Let, Neg, Num, Print, Repeat, Stmt, Str, Var,
)
from parsley.compiler.symbols import Symbol, SymbolType
from parsley.diagnostics import Diagnostic, has_errors
from parsley.session import Session

STAGE = "semantic"
REPEAT_MIN, REPEAT_MAX = 1, 1000

# Plain-English names for operators, matching the back-translation wording (LANGUAGE_SPEC.md 7.4)
_TEXT_ARITH_VERBS = {"-": "subtracted", "*": "multiplied", "/": "divided"}
_COMPARISON_PHRASES = {
    ">": "is greater than", "<": "is less than",
    ">=": "is greater than or equal to", "<=": "is less than or equal to",
}
_TEXT_COMPARISONS = frozenset({"==", "!="})
_WHOLE_NUMBER = re.compile(r"[0-9]+")
_LITERAL_ZERO = re.compile(r"0+(\.0+)?")


def analyze(stmt: Stmt, session: Session) -> list[Diagnostic]:
    """Check one statement; if it has no errors, record it in the session.

    Raises TypeError for anything that is not a statement node.
    """
    checker = _Checker(session.symbols)
    checker.statement(stmt, in_block=False)
    if not has_errors(checker.diagnostics):
        _record(stmt, session, checker.declared_type)
    return checker.diagnostics


class _Checker:
    """Walks one statement, collecting diagnostics; reads the symbol table, never writes it."""

    def __init__(self, symbols: Mapping[str, Symbol]) -> None:
        self._symbols = symbols
        self.diagnostics: list[Diagnostic] = []
        self.declared_type: SymbolType | None = None  # value type of a top-level LET

    def _error(self, code: str, message: str) -> None:
        self.diagnostics.append(Diagnostic("error", STAGE, code, message))

    def _warning(self, code: str, message: str) -> None:
        self.diagnostics.append(Diagnostic("warning", STAGE, code, message))

    # Statements

    def statement(self, stmt: Stmt, in_block: bool) -> None:
        if isinstance(stmt, Let):
            value_type = self.expression(stmt.value)
            if in_block:
                self._error("E202", "variables must be created outside IF and REPEAT blocks")
                return
            if stmt.name in self._symbols:
                self._warning("W208", f"{stmt.name} already exists, so creating it again replaces it")
            self.declared_type = value_type
        elif isinstance(stmt, Assign):
            value_type = self.expression(stmt.value)
            symbol = self._symbols.get(stmt.name)
            if symbol is None:
                self._error("E201", _used_before_created(stmt.name))
            elif value_type is not None and value_type != symbol.type:
                self._error(
                    "E209", f"{stmt.name} is {_noun(symbol.type)}, so it cannot be set to {_noun(value_type)}"
                )
        elif isinstance(stmt, Print):
            self.expression(stmt.value)
        elif isinstance(stmt, If):
            self.condition(stmt.condition)
            for inner in (*stmt.then_body, *(stmt.else_body or ())):
                self.statement(inner, in_block=True)
        elif isinstance(stmt, Repeat):
            self.repeat_count(stmt.count)
            for inner in stmt.body:
                self.statement(inner, in_block=True)
        else:
            raise TypeError(f"not a statement node: {stmt!r}")

    def repeat_count(self, count: Num) -> None:
        text = count.text
        if not (_WHOLE_NUMBER.fullmatch(text) and REPEAT_MIN <= int(text) <= REPEAT_MAX):
            self._error("E207", f"REPEAT needs a whole number of times from 1 to 1000, not {text}")

    def condition(self, cond: Compare) -> None:
        left, right = self.expression(cond.left), self.expression(cond.right)
        if left is None or right is None:
            return
        if left != right:
            self._error("E204", "cannot compare text with a number: " + _types(cond.left, left, cond.right, right))
        elif left == "string" and cond.op not in _TEXT_COMPARISONS:
            self._error(
                "E205",
                "text can only be compared with 'is equal to' or 'is not equal to', "
                f"not '{_COMPARISON_PHRASES[cond.op]}'",
            )

    # Expressions: return the inferred type, or None when unknown

    def expression(self, expr: Expr) -> SymbolType | None:
        if isinstance(expr, Num):
            return "number"
        if isinstance(expr, Str):
            return "string"
        if isinstance(expr, Var):
            symbol = self._symbols.get(expr.name)
            if symbol is None:
                self._error("E201", _used_before_created(expr.name))
                return None
            return symbol.type
        if isinstance(expr, Neg):
            operand = self.expression(expr.operand)
            if operand == "string":
                self._error("E203", f"{_describe(expr.operand)} is text, and text cannot be made negative")
                return None
            return operand
        if isinstance(expr, BinOp):
            return self.binop(expr)
        raise TypeError(f"not an expression node: {expr!r}")

    def binop(self, expr: BinOp) -> SymbolType | None:
        left, right = self.expression(expr.left), self.expression(expr.right)
        if expr.op == "/" and _is_literal_zero(expr.right):
            self._error("E206", "cannot divide by zero")
        if expr.op == "+":
            if left is None or right is None:
                return None
            if left != right:
                self._error("E204", "cannot add text and a number: " + _types(expr.left, left, expr.right, right))
                return None
            return left
        text_side = expr.left if left == "string" else expr.right if right == "string" else None
        if text_side is not None:
            self._error("E203", f"{_describe(text_side)} is text, and text cannot be {_TEXT_ARITH_VERBS[expr.op]}")
            return None
        return None if left is None or right is None else "number"


def _record(stmt: Stmt, session: Session, declared_type: SymbolType | None) -> None:
    """Apply an error-free statement to the session (the only symbol-table writes)."""
    if isinstance(stmt, Let) and declared_type is not None:
        session.symbol_table.declare(stmt.name, declared_type, len(session.history))
    for name in _names_used(stmt):
        if name in session.ref_stack:
            session.ref_stack.remove(name)
        session.ref_stack.append(name)
    session.history.append(stmt)


def _walk(stmt: Stmt) -> Iterator[Stmt]:
    """The statement and its nested block statements, in source order."""
    yield stmt
    if isinstance(stmt, If):
        for inner in (*stmt.then_body, *(stmt.else_body or ())):
            yield from _walk(inner)
    elif isinstance(stmt, Repeat):
        for inner in stmt.body:
            yield from _walk(inner)


def _names_used(stmt: Stmt) -> Iterator[str]:
    """Variable names in source order; an assignment target comes after its value."""
    for node in _walk(stmt):
        if isinstance(node, (Let, Assign)):
            yield from _expr_names(node.value)
            yield node.name
        elif isinstance(node, Print):
            yield from _expr_names(node.value)
        elif isinstance(node, If):
            yield from _expr_names(node.condition.left)
            yield from _expr_names(node.condition.right)


def _expr_names(expr: Expr) -> Iterator[str]:
    if isinstance(expr, Var):
        yield expr.name
    elif isinstance(expr, Neg):
        yield from _expr_names(expr.operand)
    elif isinstance(expr, BinOp):
        yield from _expr_names(expr.left)
        yield from _expr_names(expr.right)


# Message helpers


def _used_before_created(name: str) -> str:
    return f"{name} is used before it is created"


def _describe(expr: Expr) -> str:
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, Num):
        return expr.text
    if isinstance(expr, Str):
        return f'"{expr.value}"'
    return "the value"


def _noun(kind: SymbolType) -> str:
    return "text" if kind == "string" else "a number"


def _types(left: Expr, left_type: SymbolType, right: Expr, right_type: SymbolType) -> str:
    return f"{_describe(left)} is {_noun(left_type)} and {_describe(right)} is {_noun(right_type)}"


def _is_literal_zero(expr: Expr) -> bool:
    if isinstance(expr, Neg):
        return _is_literal_zero(expr.operand)
    return isinstance(expr, Num) and _LITERAL_ZERO.fullmatch(expr.text) is not None
