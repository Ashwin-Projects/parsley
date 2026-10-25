"""Session state across sentences: symbol table, reference stack, history (Phase 4).

``Session`` mirrors ARCHITECTURE.md 2.7. ``semantic.py`` is the only writer of all three
fields; the context resolver (Phase 6) reads ``symbols``, a live read-only view.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from parsley.compiler.ast_nodes import Stmt
from parsley.compiler.symbols import Symbol, SymbolTable


@dataclass
class Session:
    """State shared by the sentences of one program (one REPL run or one input file)."""

    symbol_table: SymbolTable = field(default_factory=SymbolTable)
    ref_stack: list[str] = field(default_factory=list)  # most recent name last
    history: list[Stmt] = field(default_factory=list)  # accepted statements in order

    @property
    def symbols(self) -> Mapping[str, Symbol]:
        """Read-only view of the symbol table for readers such as the context resolver."""
        return self.symbol_table.view()
