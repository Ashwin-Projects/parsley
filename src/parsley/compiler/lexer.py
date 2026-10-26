"""MiniLang lexer with line/column error reporting (Phase 3).

Follows LANGUAGE_SPEC.md Section 2: keywords are upper-case and reserved in any case (a
keyword spelled in another case is a lexical error), identifiers are ASCII letters, digits
and underscores starting with a letter, numbers carry no sign and at most one decimal part,
and the only string escapes are ``\\"`` and ``\\\\``.
"""

from __future__ import annotations

from dataclasses import dataclass

KEYWORDS = frozenset({"LET", "PRINT", "IF", "THEN", "ELSE", "REPEAT", "TIMES"})

_TWO_CHAR_SYMBOLS = frozenset({"==", "!=", ">=", "<="})
_ONE_CHAR_SYMBOLS = frozenset("=;{}()+-*/<>")
_ESCAPES = {'"': '"', "\\": "\\"}


class LexError(ValueError):
    """A character sequence MiniLang does not allow; ``line`` and ``column`` start at 1."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"{message} (line {line}, column {column})")
        self.message = message
        self.line = line
        self.column = column


@dataclass(frozen=True, slots=True)
class Token:
    """One token. ``kind`` is a keyword, a symbol, ``IDENT``, ``NUMBER``, ``STRING`` or ``EOF``.

    ``text`` is the source text, except for ``STRING`` where it is the unescaped content.
    ``start``/``end`` are character offsets into the source (``end`` is exclusive).
    """

    kind: str
    text: str
    line: int
    column: int
    start: int
    end: int


def _is_letter(char: str) -> bool:
    return char.isascii() and char.isalpha()


def _is_digit(char: str) -> bool:
    return char.isascii() and char.isdigit()


def tokenize(source: str) -> list[Token]:
    """Split ``source`` into tokens, ending with an ``EOF`` token. Raises ``LexError``."""
    tokens: list[Token] = []
    length = len(source)
    index = 0
    line = 1
    line_start = 0  # offset of the first character of the current line
    while index < length:
        char = source[index]
        if char == "\n":
            index += 1
            line += 1
            line_start = index
            continue
        if char in " \t\r":
            index += 1
            continue
        column = index - line_start + 1
        if _is_letter(char):
            end = index + 1
            while end < length and (_is_letter(source[end]) or _is_digit(source[end]) or source[end] == "_"):
                end += 1
            word = source[index:end]
            if word.upper() in KEYWORDS:
                if word != word.upper():
                    raise LexError(f"keyword {word!r} must be written in upper case as {word.upper()}", line, column)
                kind = word
            else:
                kind = "IDENT"
            tokens.append(Token(kind, word, line, column, index, end))
            index = end
        elif _is_digit(char):
            end = index + 1
            while end < length and _is_digit(source[end]):
                end += 1
            if end + 1 < length and source[end] == "." and _is_digit(source[end + 1]):
                end += 2
                while end < length and _is_digit(source[end]):
                    end += 1
            tokens.append(Token("NUMBER", source[index:end], line, column, index, end))
            index = end
        elif char == '"':
            token, index, line, line_start = _string(source, index, line, line_start)
            tokens.append(token)
        elif source[index:index + 2] in _TWO_CHAR_SYMBOLS:
            tokens.append(Token(source[index:index + 2], source[index:index + 2], line, column, index, index + 2))
            index += 2
        elif char in _ONE_CHAR_SYMBOLS:
            tokens.append(Token(char, char, line, column, index, index + 1))
            index += 1
        elif char == "!":
            raise LexError("unexpected '!' (the only operator that starts with it is '!=')", line, column)
        else:
            raise LexError(f"unexpected character {char!r}", line, column)
    tokens.append(Token("EOF", "", line, index - line_start + 1, length, length))
    return tokens


def _string(source: str, start: int, line: int, line_start: int) -> tuple[Token, int, int, int]:
    """Read the string literal opening at ``start``; returns the token and the new position."""
    open_line, open_column = line, start - line_start + 1
    chars: list[str] = []
    index = start + 1
    length = len(source)
    while index < length:
        char = source[index]
        if char == '"':
            token = Token("STRING", "".join(chars), open_line, open_column, start, index + 1)
            return token, index + 1, line, line_start
        if char == "\\":
            if index + 1 >= length or source[index + 1] not in _ESCAPES:
                found = source[index + 1] if index + 1 < length else "end of input"
                column = index - line_start + 1
                raise LexError(f"unknown escape \\{found} (only \\\" and \\\\ are allowed)", line, column)
            chars.append(_ESCAPES[source[index + 1]])
            index += 2
            continue
        if char == "\n":
            line += 1
            line_start = index + 1
        chars.append(char)
        index += 1
    raise LexError("string is never closed", open_line, open_column)
