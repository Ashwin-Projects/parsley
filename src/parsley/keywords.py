"""MiniLang keywords: the single source for the NLP front end and the lexer (LANGUAGE_SPEC.md 2).

Keywords are written in upper case in MiniLang source and are reserved in any case, so
``let``, ``Let`` and ``LET`` can never be identifiers.
"""

from __future__ import annotations

KEYWORDS = frozenset({"LET", "PRINT", "IF", "THEN", "ELSE", "REPEAT", "TIMES"})


def is_reserved(word: str) -> bool:
    """Whether ``word`` is a MiniLang keyword in any casing (ASCII only: ``ıf`` is not ``IF``)."""
    return word.isascii() and word.upper() in KEYWORDS
