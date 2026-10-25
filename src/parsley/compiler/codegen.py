"""[F] AST to canonical MiniLang, one template per node (Phase 5)."""

from functools import singledispatch

from parsley.compiler.ast_nodes import (
    Assign, BinOp, Compare, Expr, If, Let, Neg, Num, Print, Program,
    Repeat, Stmt, Str, Var,
)


Node = Program | Stmt | Compare | Expr
_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


@singledispatch
def generate(node: Node) -> str:
    """Render an AST node in canonical MiniLang, without a trailing newline.

    This consumes a checked AST; semantic validation belongs to Phase 4.
    Unsupported node types raise TypeError for the pipeline to diagnose.
    """
    raise TypeError(f"Unsupported AST node: {type(node).__name__}")


@generate.register
def _program(node: Program) -> str:
    return "\n".join(generate(stmt) for stmt in node.statements)


@generate.register
def _let(node: Let) -> str:
    return f"LET {node.name} = {generate(node.value)};"


@generate.register
def _assign(node: Assign) -> str:
    return f"{node.name} = {generate(node.value)};"


@generate.register
def _print(node: Print) -> str:
    return f"PRINT {generate(node.value)};"


def _block(body: tuple[Stmt, ...]) -> str:
    return "{ " + " ".join(generate(stmt) for stmt in body) + " }"


@generate.register
def _if(node: If) -> str:
    text = f"IF {generate(node.condition)} THEN {_block(node.then_body)}"
    if node.else_body is not None:
        text += f" ELSE {_block(node.else_body)}"
    return text


@generate.register
def _repeat(node: Repeat) -> str:
    return f"REPEAT {generate(node.count)} TIMES {_block(node.body)}"


@generate.register
def _compare(node: Compare) -> str:
    return f"{generate(node.left)} {node.op} {generate(node.right)}"


def _operand(node: Expr, precedence: int, *, right: bool = False) -> str:
    text = generate(node)
    if isinstance(node, BinOp):
        child_precedence = _PRECEDENCE[node.op]
        # Equal precedence on the right needs grouping (left associativity).
        if child_precedence < precedence or (
            right and child_precedence == precedence
        ):
            return f"({text})"
    return text


@generate.register
def _binop(node: BinOp) -> str:
    precedence = _PRECEDENCE[node.op]
    left = _operand(node.left, precedence)
    right = _operand(node.right, precedence, right=True)
    return f"{left} {node.op} {right}"


@generate.register
def _neg(node: Neg) -> str:
    return "-" + _operand(node.operand, max(_PRECEDENCE.values()) + 1)


@generate.register
def _num(node: Num) -> str:
    return node.text


@generate.register
def _str(node: Str) -> str:
    escaped = node.value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@generate.register
def _var(node: Var) -> str:
    return node.name
