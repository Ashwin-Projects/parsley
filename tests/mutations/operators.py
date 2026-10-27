"""Test-only mutation operators: injected code-generation bugs for the N3 evaluation.

CLAUDE.md rule 6: corruption hooks live only under ``tests/``. ``parsley.eval.run_eval``
loads this file by path to measure which verifier layer notices each bug; nothing in
``src/`` corrupts code. Each operator changes the first matching node, in source order,
of the program's last statement (the statement the pipeline just generated).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, is_dataclass, replace

from parsley.compiler.ast_nodes import BinOp, Compare, If, Let, Neg, Num, Program, Repeat, Str, Var

_ARITH = {"+": "-", "-": "+", "*": "/", "/": "*"}
_COMPARE = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "!=", "!=": "=="}


def _children(node: object) -> tuple:
    if isinstance(node, tuple):
        return node
    if is_dataclass(node):
        return tuple(getattr(node, field.name) for field in fields(node))
    return ()


def _first(node: object, kind: type) -> object | None:
    """The first node of ``kind`` in source (pre-)order."""
    if isinstance(node, kind):
        return node
    for child in _children(node):
        found = _first(child, kind)
        if found is not None:
            return found
    return None


def _replace_first(node: object, match: Callable[[object], bool], change: Callable[[object], object]):
    """``node`` with its first matching descendant changed, or None if none matches."""
    if match(node):
        return change(node)
    if isinstance(node, tuple):
        for index, child in enumerate(node):
            new = _replace_first(child, match, change)
            if new is not None:
                return node[:index] + (new,) + node[index + 1:]
    elif is_dataclass(node):
        for field in fields(node):
            new = _replace_first(getattr(node, field.name), match, change)
            if new is not None:
                return replace(node, **{field.name: new})
    return None


def _bump(num: Num) -> Num:
    return Num(str(int(num.text) + 1) if "." not in num.text else num.text + "1")


def _single(match, change):
    return lambda statement, names: _replace_first(statement, match, change)


def _swap_variable(statement, names):
    current = _first(statement, Var)
    others = [name for name in names if current is not None and name != current.name]
    if not others:
        return None
    return _replace_first(statement, lambda n: isinstance(n, Var), lambda n: Var(others[0]))


OPERATORS = {
    "arith_op_swap": _single(lambda n: isinstance(n, BinOp), lambda n: replace(n, op=_ARITH[n.op])),
    "operand_swap": _single(lambda n: isinstance(n, BinOp) and n.left != n.right,
                            lambda n: replace(n, left=n.right, right=n.left)),
    "compare_flip": _single(lambda n: isinstance(n, Compare), lambda n: replace(n, op=_COMPARE[n.op])),
    "literal_off_by_one": _single(lambda n: isinstance(n, Num), _bump),
    "string_change": _single(lambda n: isinstance(n, Str), lambda n: Str(n.value + "!")),
    "negation_drop": _single(lambda n: isinstance(n, Neg), lambda n: n.operand),
    "swap_branches": _single(lambda n: isinstance(n, If) and n.else_body is not None,
                             lambda n: replace(n, then_body=n.else_body, else_body=n.then_body)),
    "repeat_count": _single(lambda n: isinstance(n, Repeat), lambda n: replace(n, count=_bump(n.count))),
    "variable_swap": _swap_variable,
}


def mutants(program: Program) -> list[tuple[str, Program]]:
    """Every applicable (operator name, mutated program); the last statement is the target."""
    *before, last = program.statements
    names = [s.name for s in before if isinstance(s, Let)]
    result = []
    for name, operator in OPERATORS.items():
        changed = operator(last, names)
        if changed is not None and changed != last:
            result.append((name, Program((*before, changed))))
    result.append(("drop_statement", Program(tuple(before))))
    return result
