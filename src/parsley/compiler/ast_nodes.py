"""Frozen, comparable AST node dataclasses (Phase 3).

This module is a data contract (ARCHITECTURE.md 2.8): the IR builder produces these
nodes, and the parser, code generator and verifiers consume them. Nodes are frozen and
compare by value, so V2 round-trip checking is plain ``==``. Child sequences are tuples,
which keeps every tree hashable. Nodes hold no logic; types and value ranges are
checked by the semantic analyzer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

ArithOp = Literal["+", "-", "*", "/"]
CompareOp = Literal[">", "<", "==", ">=", "<=", "!="]


# Expressions


@dataclass(frozen=True, slots=True)
class Num:
    """Number literal, kept exactly as written (``"2.5"`` stays ``"2.5"``)."""

    text: str


@dataclass(frozen=True, slots=True)
class Str:
    """String literal; ``value`` is the unescaped content without quotes."""

    value: str


@dataclass(frozen=True, slots=True)
class Var:
    """Reference to a variable by its case-sensitive name."""

    name: str


@dataclass(frozen=True, slots=True)
class Neg:
    """Unary minus: ``-operand``."""

    operand: Expr


@dataclass(frozen=True, slots=True)
class BinOp:
    """Binary arithmetic: ``left op right``."""

    op: ArithOp
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Compare:
    """Condition inside ``IF``: ``left op right``."""

    op: CompareOp
    left: Expr
    right: Expr


# Statements


@dataclass(frozen=True, slots=True)
class Let:
    """``LET name = value;``"""

    name: str
    value: Expr


@dataclass(frozen=True, slots=True)
class Assign:
    """``name = value;``"""

    name: str
    value: Expr


@dataclass(frozen=True, slots=True)
class Print:
    """``PRINT value;``"""

    value: Expr


@dataclass(frozen=True, slots=True)
class If:
    """``IF condition THEN { then_body } [ELSE { else_body }]``; ``else_body`` is None without ELSE."""

    condition: Compare
    then_body: tuple[Stmt, ...]
    else_body: tuple[Stmt, ...] | None = None


@dataclass(frozen=True, slots=True)
class Repeat:
    """``REPEAT count TIMES { body }``; the count's 1-1000 integer range is a semantic check."""

    count: Num
    body: tuple[Stmt, ...]


@dataclass(frozen=True, slots=True)
class Program:
    """A whole MiniLang program: statements in order."""

    statements: tuple[Stmt, ...]


Expr = Union[Num, Str, Var, Neg, BinOp]
Stmt = Union[Let, Assign, Print, If, Repeat]
