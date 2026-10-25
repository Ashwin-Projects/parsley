"""Symbol table: name, inferred type, declaring statement, live read-only view."""

import dataclasses

import pytest

from parsley.compiler.symbols import Symbol, SymbolTable


def test_declare_and_lookup():
    table = SymbolTable()
    table.declare("age", "number", 0)
    assert table.lookup("age") == Symbol("age", "number", 0)
    assert "age" in table
    assert table.lookup("missing") is None
    assert "missing" not in table


def test_names_are_case_sensitive():
    table = SymbolTable()
    table.declare("Age", "number", 0)
    assert table.lookup("age") is None


def test_redeclare_replaces_type_and_position():
    table = SymbolTable()
    table.declare("x", "number", 0)
    table.declare("x", "string", 3)
    assert table.lookup("x") == Symbol("x", "string", 3)


@pytest.mark.parametrize("bad", ["boolean", "Number", ""])
def test_unknown_type_is_rejected(bad):
    with pytest.raises(ValueError):
        SymbolTable().declare("x", bad, 0)  # type: ignore[arg-type]


def test_table_has_no_retype():
    assert not hasattr(SymbolTable(), "retype")


def test_symbol_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Symbol("x", "number", 0).type = "string"  # type: ignore[misc]


def test_view_is_read_only():
    table = SymbolTable()
    table.declare("x", "number", 0)
    view = table.view()
    with pytest.raises(TypeError):
        view["y"] = Symbol("y", "number", 1)  # type: ignore[index]
    with pytest.raises(TypeError):
        del view["x"]  # type: ignore[attr-defined]
    assert not hasattr(view, "declare")


def test_view_is_live():
    table = SymbolTable()
    view = table.view()
    table.declare("x", "number", 0)
    assert dict(view) == {"x": Symbol("x", "number", 0)}
