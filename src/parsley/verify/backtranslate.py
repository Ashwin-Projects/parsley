"""[N3-V1] AST to canonical English, one template per node (Phase 5)."""

from functools import singledispatch

from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, Expr, If, Let, Neg, Num, Print, Program,
    Repeat, Stmt, Str, Var,
)


Node = Program | Stmt | Compare | Expr
_ARITHMETIC = {"+": "plus", "-": "minus", "*": "times", "/": "divided by"}
_UPDATES = {"+": "increase", "-": "decrease", "*": "multiply", "/": "divide"}
_COMPARISONS = {
    ">": "is greater than",
    "<": "is less than",
    "==": "is equal to",
    "!=": "is not equal to",
    ">=": "is greater than or equal to",
    "<=": "is less than or equal to",
}


def backtranslate(node: Node) -> str:
    """Render canonical English; statements/programs end in one period.

    Expressions and comparisons return fragments. Explicit grouping and block
    boundaries make the description unambiguous (LANGUAGE_SPEC.md 7.4).
    Unsupported node types raise TypeError for the pipeline to diagnose.
    """
    text = _render(node)
    if text and isinstance(node, (Program, Let, Assign, Print, If, Repeat)):
        return text + "."
    return text


@singledispatch
def _render(node: Node) -> str:
    raise TypeError(f"Unsupported AST node: {type(node).__name__}")


@_render.register
def _program(node: Program) -> str:
    return "; ".join(_render(stmt) for stmt in node.statements)


@_render.register
def _let(node: Let) -> str:
    return f"create variable {node.name} with value {_render(node.value)}"


@_render.register
def _assign(node: Assign) -> str:
    value = node.value
    if isinstance(value, BinOp) and value.left == Var(node.name):
        return f"{_UPDATES[value.op]} {node.name} by {_render(value.right)}"
    return f"set {node.name} to {_render(value)}"


@_render.register
def _print(node: Print) -> str:
    return f"print {_render(node.value)}"


def _block(body: tuple[Stmt, ...]) -> str:
    return "begin " + "; ".join(_render(stmt) for stmt in body) + " end"


@_render.register
def _if(node: If) -> str:
    text = f"if {_render(node.condition)} then {_block(node.then_body)}"
    if node.else_body is not None:
        text += f" else {_block(node.else_body)}"
    return text


@_render.register
def _repeat(node: Repeat) -> str:
    return f"repeat {_render(node.count)} times {_block(node.body)}"


@_render.register
def _compare(node: Compare) -> str:
    phrase = _COMPARISONS[node.op]
    return f"{_render(node.left)} {phrase} {_render(node.right)}"


@_render.register
def _binop(node: BinOp) -> str:
    phrase = _ARITHMETIC[node.op]
    return f"({_render(node.left)} {phrase} {_render(node.right)})"


@_render.register
def _neg(node: Neg) -> str:
    return f"negative ({_render(node.operand)})"


@_render.register
def _num(node: Num) -> str:
    return node.text


@_render.register
def _str(node: Str) -> str:
    escaped = node.value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@_render.register
def _var(node: Var) -> str:
    return node.name
