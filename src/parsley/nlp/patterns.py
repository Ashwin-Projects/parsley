"""Data-driven pattern table: rule_id, token/regex pattern, intent, slot extractors (Phase 2).

This module is the only place English phrasings live. Each rule is written in the
template notation of LANGUAGE_SPEC.md section 6 and compiled to a regex that is matched
(with ``fullmatch``) against ``Normalized.match_text``:

- ``word``         literal command word (matched lower-case)
- ``(a|b c)``      alternatives
- ``[x y]``        optional part; a placeholder inside it is a required slot that may be missing
- ``NAME`` ``VALUE`` ``COND`` ``STMT`` ``N``  placeholders, bound in order to ``slot_names``

The placeholder decides the slot extractor (``EXTRACTORS``); ``candidates.py`` runs it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from parsley.keywords import KEYWORDS as MINILANG_KEYWORDS  # noqa: F401  (re-exported with the pattern data)

# Vocabulary (LANGUAGE_SPEC.md 6, 6.1, 6.2)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "declare": ("make", "create", "declare", "define", "initialize"),
    "define": ("define", "initialize", "declare"),  # D5: verbs that declare without "a variable"
    "named": ("called", "named"),
    "initial": ("with value", "equal to", "set to", "as", "="),
    "define_value": ("with value", "equal to", "set to", "as", "to", "="),
    "set_as": ("as", "equal to"),
    "change_to": ("to", "as"),
    "increase": ("increase", "increment", "raise", "grow"),
    "decrease": ("decrease", "decrement", "reduce", "lower", "drop"),
    "take": ("take", "remove"),
    # Two-word verbs first: alternatives are tried in order, so "print out x" is not "print" + "out x".
    # "write" is left out: it is a near miss of "while", so N4 would suggest a rewrite of a while loop.
    "print": ("print out", "show me", "print", "show", "display", "output"),
    "if": ("if", "when"),
    "else": ("else", "otherwise"),
    "repeat": ("repeat", "loop"),
}

BINARY_OPERATORS: tuple[tuple[str, str], ...] = (
    ("multiplied by", "*"),
    ("divided by", "/"),
    ("plus", "+"),
    ("minus", "-"),
    ("times", "*"),
    ("+", "+"),
    ("-", "-"),
    ("*", "*"),
    ("/", "/"),
)

# Longest phrase first, so "is greater than or equal to" wins over "is greater than".
COMPARISONS: tuple[tuple[str, str], ...] = (
    ("is greater than or equal to", ">="),
    ("is less than or equal to", "<="),
    ("is not equal to", "!="),
    ("is no less than", ">="),
    ("is no more than", "<="),
    ("is greater than", ">"),
    ("is more than", ">"),
    ("is bigger than", ">"),
    ("is larger than", ">"),
    ("is less than", "<"),
    ("is smaller than", "<"),
    ("is at least", ">="),
    ("is at most", "<="),
    ("is equal to", "=="),
    ("isn't equal to", "!="),
    ("does not equal", "!="),
    ("is above", ">"),
    ("is below", "<"),
    ("is under", "<"),
    ("equals", "=="),
    ("isn't", "!="),
)

PRONOUNS: tuple[str, ...] = ("the variable", "it", "that")
# Number words (v1.1): a REPEAT count, or a value word that is not a declared variable.
NUMBER_WORDS: dict[str, str] = {
    word: str(value)
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
ARTICLE = "the"  # "the NAME": ignored before a variable name (v1.1)
LEADING_FILLER: tuple[str, ...] = ("please",)  # ignored at the start of a sentence (v1.1)
UNARY_MINUS_WORD = "negative"
ALTERNATIVE_WORD = "or"  # "VALUE or VALUE" -> one candidate per alternative
CONTINUATION_WORD = "and"  # "STMT and STMT" in a block body -> rejected (D-4)
ELSE_WORDS: tuple[str, ...] = SYNONYMS["else"]  # never part of a block body; they belong to IF2

BLOCK_BODY_INTENTS = frozenset({"print", "assign", "increment", "decrement", "multiply", "divide"})

# MiniLang identifier rule (LANGUAGE_SPEC.md 2) used to validate NAME slots; keywords come
# from parsley.keywords (imported above as MINILANG_KEYWORDS).
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

# Placeholder -> slot extractor kind (implemented in candidates.py).
EXTRACTORS: dict[str, str] = {
    "NAME": "name",
    "VALUE": "value",
    "COND": "condition",
    "STMT": "statement",
    "N": "count",
}


@dataclass(frozen=True, slots=True)
class Pattern:
    """One supported English pattern."""

    rule_id: str
    intent: str
    template: str
    slot_names: tuple[str, ...]  # one per placeholder, in template order
    extractors: tuple[str, ...]  # extractor kind per slot, parallel to slot_names
    example: str
    regex: re.Pattern[str]


# Template compiler

_TEMPLATE_TOKEN = re.compile(r"[()\[\]|]|[^\s()\[\]|]+")
_PRONOUN_ALTERNATION = "|".join(re.escape(p) for p in sorted(PRONOUNS, key=len, reverse=True))
_PLACEHOLDER_REGEX = {
    "NAME": rf"(?:{_PRONOUN_ALTERNATION}|(?:{ARTICLE} )?\S+)",
    "N": r"\S+",
    "VALUE": r".+?",
    "COND": r".+?",
    "STMT": r".+?",
}


def _compile(template: str, slot_names: tuple[str, ...]) -> tuple[re.Pattern[str], tuple[str, ...]]:
    """Compile a LANGUAGE_SPEC.md template to a regex with one named group per slot."""
    tokens = _TEMPLATE_TOKEN.findall(template)
    names = iter(slot_names)
    extractors: list[str] = []
    position = 0

    def sequence(stop: frozenset[str]) -> str:
        nonlocal position
        out = ""
        first = True
        while position < len(tokens) and tokens[position] not in stop:
            token = tokens[position]
            position += 1
            if token == "[":
                if first:
                    raise ValueError(f"template {template!r} may not start with an optional part")
                inner = sequence(frozenset("]"))
                position += 1
                out += f"(?: {inner})?"
            else:
                if token == "(":
                    options = [sequence(frozenset("|)"))]
                    while tokens[position] == "|":
                        position += 1
                        options.append(sequence(frozenset("|)")))
                    position += 1
                    piece = "(?:" + "|".join(options) + ")"
                elif token in _PLACEHOLDER_REGEX:
                    extractors.append(EXTRACTORS[token])
                    piece = f"(?P<{next(names)}>{_PLACEHOLDER_REGEX[token]})"
                else:
                    piece = re.escape(token)
                out += piece if first else " " + piece
            first = False
        return out

    regex = sequence(frozenset())
    if len(extractors) != len(slot_names):
        raise ValueError(f"template {template!r} does not bind exactly {slot_names}")
    return re.compile(regex), tuple(extractors)


def _syn(group: str) -> str:
    """Template alternatives for a synonym group, e.g. ``(print|show|display)``."""
    return "(" + "|".join(SYNONYMS[group]) + ")"


def _rule(rule_id: str, intent: str, template: str, slot_names: tuple[str, ...], example: str) -> Pattern:
    """Build one table entry, compiling its template."""
    regex, extractors = _compile(template, slot_names)
    return Pattern(rule_id, intent, template, slot_names, extractors, example, regex)


# The pattern table (LANGUAGE_SPEC.md section 6)

PATTERNS: tuple[Pattern, ...] = (
    _rule("D1", "declare", f"{_syn('declare')} a [new] variable {_syn('named')} NAME and set it to VALUE",
          ("name", "value"), "make a variable called age and set it to 20"),
    _rule("D2", "declare", f"{_syn('declare')} a [new] variable {_syn('named')} NAME {_syn('initial')} VALUE",
          ("name", "value"), "create a variable named totalAmount with value 0"),
    _rule("D3", "declare", "let NAME be VALUE", ("name", "value"), 'let greeting be "Hello"'),
    _rule("D4", "declare", f"{_syn('declare')} a [new] variable NAME {_syn('initial')} VALUE",
          ("name", "value"), "create a variable total as 0"),
    _rule("D5", "declare", f"{_syn('define')} NAME {_syn('define_value')} VALUE", ("name", "value"),
          "define total as 0"),
    # S1 stays exactly "set NAME to [VALUE]": N4 builds its "store ... in" rewrite from it.
    _rule("S1", "assign", "set NAME to [VALUE]", ("name", "value"), "set age to age plus 1"),
    _rule("S2", "assign", f"change NAME {_syn('change_to')} [VALUE]", ("name", "value"), "change age to 30"),
    _rule("S3", "assign", f"update NAME {_syn('change_to')} [VALUE]", ("name", "value"), "update score to 0"),
    _rule("S4", "assign", "assign VALUE to NAME", ("value", "name"), "assign 5 to score"),
    _rule("S5", "assign", f"set NAME {_syn('set_as')} [VALUE]", ("name", "value"), "set age as 30"),
    _rule("S6", "assign", "make NAME equal to [VALUE]", ("name", "value"), "make age equal to 30"),
    _rule("S7", "assign", "NAME becomes [VALUE]", ("name", "value"), "age becomes age plus 1"),
    _rule("INC1", "increment", f"{_syn('increase')} NAME [by VALUE]", ("name", "amount"), "increase count by 2"),
    _rule("INC2", "increment", "add VALUE to NAME", ("amount", "name"), "add 5 to score"),
    _rule("DEC1", "decrement", f"{_syn('decrease')} NAME [by VALUE]", ("name", "amount"), "decrease count by 1"),
    _rule("DEC2", "decrement", "subtract VALUE from NAME", ("amount", "name"), "subtract 3 from lives"),
    _rule("DEC3", "decrement", f"{_syn('take')} VALUE from NAME", ("amount", "name"), "take 3 from lives"),
    _rule("MUL1", "multiply", "multiply NAME [by VALUE]", ("name", "amount"), "multiply total by 3"),
    _rule("DIV1", "divide", "divide NAME [by VALUE]", ("name", "amount"), "divide total by 2"),
    _rule("P1", "print", f"{_syn('print')} [VALUE]", ("value",), "print age"),
    _rule("IF1", "if", f"{_syn('if')} COND then STMT", ("condition", "then"),
          "if score is at least 10 then print winner"),
    _rule("IF2", "if", f"{_syn('if')} COND then STMT {_syn('else')} STMT", ("condition", "then", "else"),
          "if age is greater than 17 then print adult else print minor"),
    _rule("REP1", "repeat", f"{_syn('repeat')} [N times] STMT", ("count", "body"), "repeat 3 times print hello"),
    _rule("REP2", "repeat", "repeat STMT N times", ("body", "count"), "repeat show score 2 times"),
    _rule("REP3", "repeat", "do STMT N times", ("body", "count"), "do print hello 3 times"),
    _rule("REP4", "repeat", "STMT N times", ("body", "count"), "print hello 3 times"),
)


# Common-English-word list (LANGUAGE_SPEC.md 4.1): never treated as typos in Phase 6.

COMMON_WORDS_START = frozenset(
    """
    a an the and or not no yes this these those is are was be been to by of in on at for
    from with as all any some one two three more less most least than then else if
    hello hi bye world done big small store start end stop go up down ok good bad true false
    """.split()
)


def _vocabulary() -> frozenset[str]:
    """Every literal word in the pattern table and vocabulary tuples (placeholders excluded)."""
    phrases: list[str] = [p.template for p in PATTERNS]
    phrases += [phrase for group in SYNONYMS.values() for phrase in group]
    phrases += [phrase for phrase, _ in COMPARISONS + BINARY_OPERATORS]
    phrases += [*NUMBER_WORDS, *PRONOUNS, ARTICLE, *LEADING_FILLER, UNARY_MINUS_WORD, ALTERNATIVE_WORD, CONTINUATION_WORD]
    words = {word for phrase in phrases for word in re.findall(r"[A-Za-z][A-Za-z']*|=", phrase)}  # "isn't", "="
    return frozenset(word for word in words if word not in _PLACEHOLDER_REGEX)


COMMON_WORDS = COMMON_WORDS_START | _vocabulary()
