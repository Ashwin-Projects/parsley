"""Symbol table: name, inferred type, declaring statement, read-only view (Phase 4).

Only ``semantic.py`` calls ``declare`` (CLAUDE.md rule 3; guarded by
``tests/unit/test_boundaries.py``). Everyone else, including the context resolver, reads
through ``view()``. A variable keeps its type until a new ``LET`` replaces it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, get_args

SymbolType = Literal["number", "string"]

SYMBOL_TYPES = frozenset(get_args(SymbolType))


@dataclass(frozen=True, slots=True)
class Symbol:
    """A declared variable; ``declared_at`` indexes the declaring statement in the history."""

    name: str
    type: SymbolType
    declared_at: int


class SymbolTable:
    """Variables of the one global scope, by case-sensitive name."""

    def __init__(self) -> None:
        self._symbols: dict[str, Symbol] = {}

    def declare(self, name: str, kind: SymbolType, declared_at: int) -> None:
        """Create ``name``; a redeclaration replaces the old entry."""
        if kind not in SYMBOL_TYPES:
            raise ValueError(f"unknown symbol type {kind!r}")
        self._symbols[name] = Symbol(name, kind, declared_at)

    def lookup(self, name: str) -> Symbol | None:
        return self._symbols.get(name)

    def view(self) -> Mapping[str, Symbol]:
        """A live, read-only mapping of name to Symbol."""
        return MappingProxyType(self._symbols)

    def __contains__(self, name: object) -> bool:
        return name in self._symbols

    def __len__(self) -> int:
        return len(self._symbols)
