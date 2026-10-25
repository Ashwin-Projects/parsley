"""Session (ARCHITECTURE.md 2.7): symbol table, reference stack, history, read-only view."""

import pytest

from parsley.compiler.symbols import Symbol, SymbolTable
from parsley.session import Session


def test_new_session_is_empty():
    session = Session()
    assert len(session.symbol_table) == 0
    assert session.ref_stack == []
    assert session.history == []


def test_sessions_do_not_share_state():
    a, b = Session(), Session()
    a.ref_stack.append("x")
    a.history.append(object())
    assert b.ref_stack == [] and b.history == []
    assert a.symbol_table is not b.symbol_table


def test_symbols_is_a_live_read_only_view():
    table = SymbolTable()
    session = Session(symbol_table=table)
    view = session.symbols
    table.declare("score", "number", 0)
    assert view["score"] == Symbol("score", "number", 0)
    with pytest.raises(TypeError):
        view["x"] = Symbol("x", "number", 1)  # type: ignore[index]
