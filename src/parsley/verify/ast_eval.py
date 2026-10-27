"""[N3-V3] Tree-walking evaluator over the original AST; independent of interpreter.py (Phase 7).

``run(program)`` evaluates the AST it is given; nothing is lexed or parsed here, and no code
is shared with ``interpreter.py`` (CLAUDE.md rule 5).

Run-time rules (shared with the interpreter only as a written contract, so V3 can compare):

* A number literal without ``.`` is an ``int``, with ``.`` a ``float``. ``int / int`` is an
  ``int`` when it divides exactly and a ``float`` otherwise.
* A statement that fails records one message in ``errors`` and stops; the statements after it
  still run, and effects made before the failure stay.
* Every REPEAT loop runs at most ``REPEAT_CAP`` (1000) times; nested loops multiply.
* Each statement, expression node and loop iteration costs one step of a ``STEP_LIMIT``
  budget (``parsley.verify``); running out records ``STEP_LIMIT_ERROR`` and ends the run.
* ``output`` holds the printed lines: strings as they are, ``int`` with ``str``, ``float``
  with ``repr``.
"""

from __future__ import annotations

from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, Expr, If, Let, Neg, Num, Print, Program, Repeat, Stmt, Str, Var,
)
from parsley.verify import STEP_LIMIT, STEP_LIMIT_ERROR

REPEAT_CAP = 1000

Value = int | float | str
Result = tuple[dict[str, Value], list[str], list[str]]


class _Failure(Exception):
    """A run-time error; its message goes to ``errors`` and the current statement stops."""


class _OutOfSteps(Exception):
    """The work budget is spent; the whole run stops."""


class _State:
    def __init__(self, max_steps: int) -> None:
        self.variables: dict[str, Value] = {}
        self.output: list[str] = []
        self.errors: list[str] = []
        self.steps_left = max_steps

    def spend(self) -> None:
        self.steps_left -= 1
        if self.steps_left < 0:
            raise _OutOfSteps


def run(program: Program, *, max_steps: int = STEP_LIMIT) -> Result:
    """Evaluate ``program``; returns ``(variables, output, errors)``."""
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    state = _State(max_steps)
    for statement in program.statements:
        try:
            _execute(statement, state)
        except _OutOfSteps:
            state.errors.append(STEP_LIMIT_ERROR)
            break
        except _Failure as failure:
            state.errors.append(str(failure))
        except (OverflowError, ValueError):
            state.errors.append("number out of range")
    return state.variables, state.output, state.errors


def _execute(statement: Stmt, state: _State) -> None:
    state.spend()
    if isinstance(statement, Let):
        state.variables[statement.name] = _evaluate(statement.value, state)
    elif isinstance(statement, Assign):
        value = _evaluate(statement.value, state)
        if statement.name not in state.variables:
            raise _Failure(f"undefined variable: {statement.name}")
        state.variables[statement.name] = value
    elif isinstance(statement, Print):
        state.output.append(_render(_evaluate(statement.value, state)))
    elif isinstance(statement, If):
        if _holds(statement.condition, state):
            _execute_all(statement.then_body, state)
        elif statement.else_body is not None:
            _execute_all(statement.else_body, state)
    elif isinstance(statement, Repeat):
        for _ in range(_loop_count(statement.count)):
            state.spend()
            _execute_all(statement.body, state)
    else:  # pragma: no cover - the AST contract has no other statement
        raise TypeError(f"not a statement: {statement!r}")


def _execute_all(body: tuple[Stmt, ...], state: _State) -> None:
    for statement in body:
        _execute(statement, state)


def _loop_count(count: Num) -> int:
    text = count.text
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise _Failure(f"invalid REPEAT count: {text}")
    return min(int(text), REPEAT_CAP)


def _evaluate(expression: Expr, state: _State) -> Value:
    state.spend()
    if isinstance(expression, Num):
        return float(expression.text) if "." in expression.text else int(expression.text)
    if isinstance(expression, Str):
        return expression.value
    if isinstance(expression, Var):
        if expression.name not in state.variables:
            raise _Failure(f"undefined variable: {expression.name}")
        return state.variables[expression.name]
    if isinstance(expression, Neg):
        operand = _evaluate(expression.operand, state)
        if isinstance(operand, str):
            raise _Failure("type error: cannot negate text")
        return -operand
    if isinstance(expression, BinOp):
        left = _evaluate(expression.left, state)
        right = _evaluate(expression.right, state)
        return _arithmetic(expression.op, left, right)
    raise TypeError(f"not an expression: {expression!r}")  # pragma: no cover


def _kind(value: Value) -> str:
    return "text" if isinstance(value, str) else "number"


def _arithmetic(op: str, left: Value, right: Value) -> Value:
    if isinstance(left, str) or isinstance(right, str):
        if op == "+" and isinstance(left, str) and isinstance(right, str):
            return left + right
        raise _Failure(f"type error: cannot apply '{op}' to {_kind(left)} and {_kind(right)}")
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if right == 0:
        raise _Failure("division by zero")
    if isinstance(left, int) and isinstance(right, int) and left % right == 0:
        return left // right
    return left / right


def _holds(condition: Compare, state: _State) -> bool:
    left = _evaluate(condition.left, state)
    right = _evaluate(condition.right, state)
    op = condition.op
    if isinstance(left, str) or isinstance(right, str):
        if not (isinstance(left, str) and isinstance(right, str) and op in ("==", "!=")):
            raise _Failure(f"type error: cannot compare {_kind(left)} and {_kind(right)} with '{op}'")
        return (left == right) if op == "==" else (left != right)
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    return left != right


def _render(value: Value) -> str:
    if isinstance(value, float):
        return repr(value)
    return str(value)
