"""[A] Normalizer: lowercase command words for matching, keep identifier and text case (Phase 2).

``normalize`` never raises and never consults the symbol table. It produces three
aligned views of one sentence:

- ``original``: the input exactly as typed (for the trace).
- ``text``: whitespace collapsed outside quotes, word-ending commas outside quotes dropped,
  trailing ``.``/``!``/``?`` stripped, original case kept. Slot values are always sliced
  from this view.
- ``match_text``: same length as ``text``; lower-cased outside quotes and with quoted
  content masked, so patterns can match command words but never text inside quotes.

English quoted text has no escapes: the next ``"`` closes the string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

TokenKind = Literal["word", "number", "string", "symbol"]

QUOTE = '"'
SYMBOLS = frozenset("+-*/")
MASK = "\x01"
TRAILING_PUNCTUATION = " .!?"
COMMA = ","  # dropped outside quotes when it ends a word (v1.1): "if x is 5, then ..."
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")  # ASCII only, like MiniLang NUMBER


@dataclass(frozen=True, slots=True)
class Token:
    """One token of ``Normalized.text``; ``start``/``end`` index into that text."""

    text: str  # original spelling; for strings, the content without quotes
    lower: str  # matching form (strings keep their content unchanged)
    kind: TokenKind
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Normalized:
    """The aligned views of one English sentence."""

    original: str
    text: str
    match_text: str
    tokens: tuple[Token, ...]
    malformed: bool  # an unterminated quote; the sentence cannot be matched


def normalize(raw: str) -> Normalized:
    """Normalize one English sentence (LANGUAGE_SPEC.md section 3)."""
    text, malformed = _clean(raw)
    tokens = () if malformed else _tokenize(text)
    return Normalized(raw, text, _match_copy(text), tokens, malformed)


def _clean(raw: str) -> tuple[str, bool]:
    """Collapse whitespace outside quotes, drop commas that end a word, strip trailing punctuation.

    A comma followed by a space or the end of the sentence is punctuation and reads as a
    space; a comma inside a word (``1,000``) is kept.
    """
    out: list[str] = []
    in_quote = False
    text = raw.strip()
    for i, ch in enumerate(text):
        ends_word = ch == COMMA and (i + 1 == len(text) or text[i + 1].isspace())
        if ch == QUOTE:
            in_quote = not in_quote
            out.append(ch)
        elif in_quote:
            out.append(ch)
        elif ch.isspace() or ends_word:
            if out and out[-1] != " ":
                out.append(" ")
        else:
            out.append(ch)
    text = "".join(out)
    if in_quote:
        return text, True
    return text.rstrip(TRAILING_PUNCTUATION), False


def _match_copy(text: str) -> str:
    """Lower-case outside quotes (length-preserving) and mask quoted content."""
    out: list[str] = []
    in_quote = False
    for ch in text:
        if ch == QUOTE:
            in_quote = not in_quote
            out.append(ch)
        elif in_quote:
            out.append(MASK)
        else:
            lowered = ch.lower()
            out.append(lowered if len(lowered) == 1 else ch)
    return "".join(out)


def _tokenize(text: str) -> tuple[Token, ...]:
    """Split into words, numbers, quoted strings and arithmetic symbols."""
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == " ":
            i += 1
        elif ch == QUOTE:
            close = text.index(QUOTE, i + 1)
            content = text[i + 1:close]
            tokens.append(Token(content, content, "string", i, close + 1))
            i = close + 1
        elif ch in SYMBOLS:
            tokens.append(Token(ch, ch, "symbol", i, i + 1))
            i += 1
        else:
            end = i
            while end < len(text) and text[end] not in SYMBOLS and text[end] not in (" ", QUOTE):
                end += 1
            word = text[i:end]
            kind: TokenKind = "number" if _NUMBER.fullmatch(word) else "word"
            tokens.append(Token(word, word.lower(), kind, i, end))
            i = end
    return tuple(tokens)
