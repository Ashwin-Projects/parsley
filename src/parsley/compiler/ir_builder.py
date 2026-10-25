"""[D] IR builder: accepted Candidate to AST nodes, one function per intent (Phase 3).

``build`` turns one accepted, fully resolved Candidate into one statement node from
``ast_nodes``. It never guesses (ARCHITECTURE.md 2.9):

- An unresolved ``word`` or ``pronoun`` slot raises ``UnresolvedSlotError``; the context
  resolver (Phase 6) must turn it into a ``name`` or ``string`` first.
- A required slot that is ``None`` raises ``MissingSlotError``; the ambiguity gate must
  clarify it first.
- Anything else malformed raises ``IRBuildError``.

Each error carries ``path``, the dotted slot path (e.g. ``value.left``, ``body.value``).
Semantic checks (types, REPEAT range, implicit declaration) belong to later stages.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from parsley.compiler.ast_nodes import (
    ArithOp,
    Assign,
    BinOp,
    Compare,
    CompareOp,
    Expr,
    If,
    Let,
    Neg,
    Num,
    Print,
    Repeat,
    Stmt,
    Str,
    Var,
)
from parsley.keywords import is_reserved
from parsley.nlp.candidates import Candidate
from parsley.nlp.patterns import IDENTIFIER

Slot = Mapping[str, Any]

UNRESOLVED_KINDS = frozenset({"word", "pronoun"})
ARITH_OPS = frozenset({"+", "-", "*", "/"})
COMPARE_OPS = frozenset({">", "<", "==", ">=", "<=", "!="})


class IRBuildError(ValueError):
    """A candidate cannot become an AST node; ``path`` names the offending slot."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path


class UnresolvedSlotError(IRBuildError):
    """A ``word``/``pronoun`` slot reached the IR builder before the context resolver ran."""


class MissingSlotError(IRBuildError):
    """A required slot is ``None``; the ambiguity gate should have asked for it."""


def build(candidate: Candidate) -> Stmt:
    """Build the statement node for one accepted, resolved candidate."""
    return _statement(candidate.intent, candidate.slots, "")


# One function per intent


def _declare(s: _Slots) -> Stmt:
    return Let(s.name("name"), s.expr("value"))


def _assign(s: _Slots) -> Stmt:
    return Assign(s.name("name"), s.expr("value"))


def _update(op: ArithOp) -> Callable[[_Slots], Stmt]:
    """increment / decrement / multiply / divide: ``name = name op amount``."""

    def build_update(s: _Slots) -> Stmt:
        target = s.name("name")
        return Assign(target, BinOp(op, Var(target), s.expr("amount")))

    return build_update


def _print(s: _Slots) -> Stmt:
    return Print(s.expr("value"))


def _if(s: _Slots) -> Stmt:
    otherwise = s.optional_statement("else")
    return If(s.condition("condition"), (s.statement("then"),), None if otherwise is None else (otherwise,))


def _repeat(s: _Slots) -> Stmt:
    return Repeat(s.count("count"), (s.statement("body"),))


_BUILDERS: dict[str, Callable[[_Slots], Stmt]] = {
    "declare": _declare,
    "assign": _assign,
    "increment": _update("+"),
    "decrement": _update("-"),
    "multiply": _update("*"),
    "divide": _update("/"),
    "print": _print,
    "if": _if,
    "repeat": _repeat,
}


# Slot access with paths


def _statement(intent: str, slots: Mapping[str, Any], prefix: str) -> Stmt:
    builder = _BUILDERS.get(intent)
    if builder is None:
        raise IRBuildError(prefix, f"unknown intent {intent!r}")
    return builder(_Slots(slots, prefix))


class _Slots:
    """The slots of one (possibly nested) statement, read by key with error paths."""

    def __init__(self, slots: Mapping[str, Any], prefix: str) -> None:
        self._slots = slots
        self._prefix = prefix

    def path(self, key: str) -> str:
        return f"{self._prefix}.{key}" if self._prefix else key

    def required(self, key: str) -> Slot:
        return _required(self._slots.get(key), self.path(key))

    def name(self, key: str) -> str:
        return _identifier(self.required(key), self.path(key))

    def expr(self, key: str) -> Expr:
        return _expression(self._slots.get(key), self.path(key))

    def condition(self, key: str) -> Compare:
        slot, path = self.required(key), self.path(key)
        _expect_kind(slot, "condition", path)
        op = cast(CompareOp, _operator(slot, COMPARE_OPS, path))
        left = _expression(_field(slot, "left", path), f"{path}.left")
        return Compare(op, left, _expression(_field(slot, "right", path), f"{path}.right"))

    def count(self, key: str) -> Num:
        slot, path = self.required(key), self.path(key)
        _expect_kind(slot, "count", path)
        return Num(_text(slot, path))

    def statement(self, key: str) -> Stmt:
        slot, path = self.required(key), self.path(key)
        _expect_kind(slot, "statement", path)
        intent = str(_field(slot, "intent", path))
        return _statement(intent, _required(_field(slot, "slots", path), f"{path}.slots"), path)

    def optional_statement(self, key: str) -> Stmt | None:
        """An absent key means the rule has no such slot (IF1 has no ``else``)."""
        return self.statement(key) if key in self._slots else None


def _expression(value: Any, path: str) -> Expr:
    slot = _required(value, path)
    kind = slot.get("kind")
    if kind == "number":
        return Num(_text(slot, path))
    if kind == "string":
        return Str(_text(slot, path))
    if kind == "name":
        return Var(_identifier(slot, path))
    if kind == "neg":
        return Neg(_expression(_field(slot, "operand", path), f"{path}.operand"))
    if kind == "binop":
        op = cast(ArithOp, _operator(slot, ARITH_OPS, path))
        left = _expression(_field(slot, "left", path), f"{path}.left")
        return BinOp(op, left, _expression(_field(slot, "right", path), f"{path}.right"))
    _reject_unresolved(slot, path)
    raise IRBuildError(path, f"unexpected slot kind {kind!r} in a value")


# Shape checks: a malformed candidate always raises IRBuildError, never KeyError/AttributeError


def _required(value: Any, path: str) -> Slot:
    if value is None:
        raise MissingSlotError(path, "required slot is missing; the ambiguity gate must clarify it")
    if not isinstance(value, Mapping):
        raise IRBuildError(path, f"expected a slot mapping, got {type(value).__name__}")
    return value


def _field(slot: Slot, key: str, path: str) -> Any:
    if key not in slot:
        raise IRBuildError(f"{path}.{key}", "missing field")
    return slot[key]


def _text(slot: Slot, path: str) -> str:
    return str(_field(slot, "text", path))


def _expect_kind(slot: Slot, kind: str, path: str) -> None:
    if slot.get("kind") != kind:
        _reject_unresolved(slot, path)
        raise IRBuildError(path, f"expected a {kind}, got {slot.get('kind')!r}")


def _operator(slot: Slot, allowed: frozenset[str], path: str) -> str:
    op = _field(slot, "op", path)
    if op not in allowed:
        raise IRBuildError(f"{path}.op", f"unknown operator {op!r}")
    return str(op)


def _identifier(slot: Slot, path: str) -> str:
    """A resolved ``name`` slot that is a legal MiniLang identifier (LANGUAGE_SPEC.md 2)."""
    _expect_kind(slot, "name", path)
    name = _text(slot, path)
    if not IDENTIFIER.fullmatch(name) or is_reserved(name):
        raise IRBuildError(path, f"{name!r} is not a legal MiniLang identifier")
    return name


def _reject_unresolved(slot: Slot, path: str) -> None:
    kind = slot.get("kind")
    if kind in UNRESOLVED_KINDS:
        raise UnresolvedSlotError(
            path, f"{kind} {slot.get('text')!r} is unresolved; the context resolver (Phase 6) must resolve it first"
        )
