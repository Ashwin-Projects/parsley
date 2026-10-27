"""Recursive-descent MiniLang parser following LANGUAGE_SPEC.md (Phase 3).

``parse(source)`` returns a ``Program`` of the frozen AST nodes. Lexical problems raise
``LexError`` and grammar problems raise ``ParseError``; both carry ``line`` and ``column``.
The parser checks syntax only: types, undefined names and the REPEAT count range belong to
the semantic analyzer (ARCHITECTURE.md 2.8).
"""

from __future__ import annotations

from parsley.compiler.ast_nodes import (
    ArithOp, Assign, BinOp, Compare, CompareOp, Expr, If, Let, Neg, Num, Print, Program,
    Repeat, Stmt, Str, Var,
)
from parsley.compiler.lexer import LexError, Token, tokenize

__all__ = ["LexError", "ParseError", "parse"]

MAX_DEPTH = 100  # nesting of parentheses, unary minus and blocks; keeps Python's stack safe

_COMPARISONS = frozenset({">", "<", "==", ">=", "<=", "!="})


class ParseError(ValueError):
    """Input that does not follow the MiniLang grammar; ``line`` and ``column`` start at 1."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"{message} (line {line}, column {column})")
        self.message = message
        self.line = line
        self.column = column


def parse(source: str) -> Program:
    """Parse MiniLang source text into a ``Program``."""
    return _Parser(tokenize(source)).program()


def _describe(token: Token) -> str:
    if token.kind == "EOF":
        return "the end of the input"
    if token.kind == "STRING":
        return "a string"
    return repr(token.text)


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._position = 0
        self._depth = 0

    # Token helpers

    @property
    def _current(self) -> Token:
        return self._tokens[self._position]

    def _advance(self) -> Token:
        token = self._tokens[self._position]
        if token.kind != "EOF":
            self._position += 1
        return token

    def _expect(self, kind: str, what: str) -> Token:
        token = self._current
        if token.kind != kind:
            raise ParseError(f"expected {what}, found {_describe(token)}", token.line, token.column)
        return self._advance()

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > MAX_DEPTH:
            token = self._current
            raise ParseError("input is too deeply nested", token.line, token.column)

    def _leave(self) -> None:
        self._depth -= 1

    # Statements

    def program(self) -> Program:
        statements = []
        while self._current.kind != "EOF":
            statements.append(self._statement())
        return Program(tuple(statements))

    def _statement(self) -> Stmt:
        token = self._current
        if token.kind == "LET":
            self._advance()
            name = self._expect("IDENT", "a variable name").text
            self._expect("=", "'='")
            value = self._expression()
            self._expect(";", "';'")
            return Let(name, value)
        if token.kind == "IDENT":
            self._advance()
            self._expect("=", "'='")
            value = self._expression()
            self._expect(";", "';'")
            return Assign(token.text, value)
        if token.kind == "PRINT":
            self._advance()
            value = self._expression()
            self._expect(";", "';'")
            return Print(value)
        if token.kind == "IF":
            return self._if()
        if token.kind == "REPEAT":
            self._advance()
            count = Num(self._expect("NUMBER", "a number").text)
            self._expect("TIMES", "TIMES")
            return Repeat(count, self._block())
        raise ParseError(f"expected a statement, found {_describe(token)}", token.line, token.column)

    def _if(self) -> If:
        self._advance()
        condition = self._condition()
        self._expect("THEN", "THEN")
        then_body = self._block()
        else_body = None
        if self._current.kind == "ELSE":
            self._advance()
            else_body = self._block()
        return If(condition, then_body, else_body)

    def _block(self) -> tuple[Stmt, ...]:
        self._enter()
        self._expect("{", "'{'")
        statements = []
        while self._current.kind not in ("}", "EOF"):
            statements.append(self._statement())
        self._expect("}", "'}'")
        self._leave()
        return tuple(statements)

    def _condition(self) -> Compare:
        left = self._expression()
        token = self._current
        if token.kind not in _COMPARISONS:
            raise ParseError(
                f"expected a comparison (>, <, ==, >=, <=, !=), found {_describe(token)}", token.line, token.column,
            )
        self._advance()
        return Compare(_comparison(token.kind), left, self._expression())

    # Expressions: expression := term (("+"|"-") term)*; term := factor (("*"|"/") factor)*

    def _expression(self) -> Expr:
        left = self._term()
        while self._current.kind in ("+", "-"):
            op = self._advance().kind
            left = BinOp(_arith(op), left, self._term())
        return left

    def _term(self) -> Expr:
        left = self._factor()
        while self._current.kind in ("*", "/"):
            op = self._advance().kind
            left = BinOp(_arith(op), left, self._factor())
        return left

    def _factor(self) -> Expr:
        token = self._current
        if token.kind == "-":
            self._advance()
            self._enter()
            operand = self._factor()
            self._leave()
            return Neg(operand)
        if token.kind == "NUMBER":
            self._advance()
            return Num(token.text)
        if token.kind == "STRING":
            self._advance()
            return Str(token.text)
        if token.kind == "IDENT":
            self._advance()
            return Var(token.text)
        if token.kind == "(":
            self._advance()
            self._enter()
            inner = self._expression()
            self._expect(")", "')'")
            self._leave()
            return inner
        raise ParseError(f"expected a value, found {_describe(token)}", token.line, token.column)


def _arith(kind: str) -> ArithOp:
    return kind  # type: ignore[return-value]  # the caller only passes + - * /


def _comparison(kind: str) -> CompareOp:
    return kind  # type: ignore[return-value]  # checked against _COMPARISONS by the caller
