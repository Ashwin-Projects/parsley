"""[B] Candidate generator: run every pattern rule and return scored candidates (Phase 2).

``generate`` normalizes one English sentence, runs every rule in ``patterns.PATTERNS``
and returns **all** matches as an ``NLPResult`` (ARCHITECTURE.md 2.3-2.4). It does not
pick a winner, never consults a symbol table, and never raises.

Slots hold raw, unresolved meaning: bare words are ``word`` slots and pronouns are
``pronoun`` slots; deciding variable vs. text is the context resolver's job (Phase 6).
Phase 2 sets ``status`` to ``"ok"`` when anything matches and ``"unsupported"``
otherwise; the ambiguity gate (Phase 6) owns ``"ambiguous"``, ``question`` and
``suggestion``.

Two English ambiguities are already visible here, without picking a reading:

- ``VALUE or VALUE`` yields one candidate per alternative, with equal scores.
- A required slot missing from the English (``increase x``) is ``None``, with a note.

Deliberate limits:

- Each rule yields one split of the sentence (placeholders match leftmost-shortest).
- One statement per sentence: ``and`` followed by a whole statement inside any value is
  rejected (LANGUAGE_SPEC.md 6.3). Phase 6 re-detects this to build the suggestion.
- Cost is bounded: ``MAX_INPUT_CHARS``, ``MAX_ALTERNATIVES`` per value and
  ``MAX_READINGS`` per rule; beyond them the input is unsupported.
"""

from __future__ import annotations

import copy
import functools
import itertools
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, NamedTuple

from parsley.keywords import is_reserved
from parsley.nlp import patterns
from parsley.nlp.normalizer import Normalized, Token, normalize

logger = logging.getLogger(__name__)

Slot = dict[str, Any]
Status = Literal["ok", "ambiguous", "unsupported"]

MAX_INPUT_CHARS = 500
MAX_ALTERNATIVES = 4
MAX_READINGS = 64


class Reason(StrEnum):
    """Why a sentence is unsupported; stored in ``NLPResult.notes`` (ARCHITECTURE.md 2.4)."""

    NOT_TEXT = "NOT_TEXT"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    UNTERMINATED_QUOTE = "UNTERMINATED_QUOTE"
    EMPTY_INPUT = "EMPTY_INPUT"
    REJECT_AND_CONTINUATION = "REJECT_AND_CONTINUATION"
    TOO_MANY_ALTERNATIVES = "TOO_MANY_ALTERNATIVES"
    TOO_MANY_READINGS = "TOO_MANY_READINGS"
    NO_MATCH = "NO_MATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class Candidate:
    """One interpretation of a sentence (frozen contract, ARCHITECTURE.md 2.3)."""

    intent: str
    slots: dict[str, Slot | None]
    score: float
    rule_id: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NLPResult:
    """The NLP front end's answer for one sentence (frozen contract, ARCHITECTURE.md 2.4)."""

    status: Status
    candidates: list[Candidate]
    question: str | None = None
    suggestion: str | None = None
    notes: list[str] = field(default_factory=list)  # reason codes when unsupported


# Reasons recorded while matching the current sentence; None = not recording.
_rejections: ContextVar[set[str] | None] = ContextVar("_rejections", default=None)


def generate(text: str) -> NLPResult:
    """Return every candidate interpretation of ``text``, best score first."""
    try:
        if not isinstance(text, str):
            return _unsupported({Reason.NOT_TEXT})
        if len(text) > MAX_INPUT_CHARS:
            return _unsupported({Reason.INPUT_TOO_LONG})
        norm = normalize(text)
        if norm.malformed:
            return _unsupported({Reason.UNTERMINATED_QUOTE})
        if not norm.tokens:
            return _unsupported({Reason.EMPTY_INPUT})
        start = _after_filler(norm)
        found: list[Candidate] = []
        with _recording(set()) as rejections:
            for pattern in patterns.PATTERNS:
                found.extend(_match(pattern, norm, start, len(norm.text)))
        if not found:
            return _unsupported(rejections or {Reason.NO_MATCH})
        found.sort(key=lambda c: c.score, reverse=True)  # stable: ties keep table order
        return NLPResult("ok", found)
    except Exception:  # contract: no exception escapes the NLP front end
        logger.exception("candidate generation failed for %r", text)
        return _unsupported({Reason.INTERNAL_ERROR})


def parse_value(text: str) -> Slot | None:
    """Exactly one VALUE reading of ``text`` (LANGUAGE_SPEC.md 6.1), or None.

    Used to read a clarification answer ("2", "score plus 1", "hello world"). Words stay
    unresolved ``word`` slots; alternatives (``1 or 2``) are not one value.
    """
    norm = _answer_text(text)
    if norm is None:
        return None
    try:
        with _recording(None):
            readings = _values(norm, norm.tokens)
        return readings[0] if len(readings) == 1 else None
    except Exception:  # same contract as generate: never raise on user text
        logger.exception("value parsing failed for %r", text)
        return None


def parse_count(text: str) -> Slot | None:
    """A REPEAT count slot if ``text`` is one number, or None."""
    norm = _answer_text(text)
    if norm is None:
        return None
    readings = _counts(norm, norm.tokens)
    return readings[0] if readings else None


def _answer_text(text: str) -> Normalized | None:
    """The normalized answer, or None if it breaks the input limits ``generate`` enforces."""
    if not isinstance(text, str) or len(text) > MAX_INPUT_CHARS or not text.isprintable():
        return None
    norm = normalize(text)
    return None if norm.malformed or not norm.tokens else norm


def _after_filler(norm: Normalized) -> int:
    """Where matching starts: after a leading filler word ("please"), if anything follows it."""
    first = norm.tokens[0]
    if len(norm.tokens) > 1 and first.kind == "word" and first.lower in patterns.LEADING_FILLER:
        return norm.tokens[1].start
    return 0


def _unsupported(reasons: set[str]) -> NLPResult:
    return NLPResult("unsupported", [], notes=sorted(str(r) for r in reasons))


@contextmanager
def _recording(target: set[str] | None) -> Iterator[set[str] | None]:
    """Record rejection reasons into ``target`` (None suspends recording) for the block."""
    token = _rejections.set(target)
    try:
        yield target
    finally:
        _rejections.reset(token)


def _reject(reason: Reason) -> None:
    recorded = _rejections.get()
    if recorded is not None:
        recorded.add(str(reason))


def _match(pattern: patterns.Pattern, norm: Normalized, start: int, end: int) -> list[Candidate]:
    """Match one rule against ``norm.text[start:end]``; one candidate per reading."""
    m = pattern.regex.fullmatch(norm.match_text, start, end)
    if m is None:
        return []
    span_tokens = _tokens(norm, start, end)
    if not span_tokens:
        return []

    options: list[list[Slot | None]] = []
    notes: list[str] = []
    slot_token_count = 0
    for name, kind in zip(pattern.slot_names, pattern.extractors, strict=True):
        slot_start, slot_end = m.span(name)
        if slot_start == -1:
            options.append([None])
            notes.append(f"missing required slot '{name}'")
            continue
        slot_tokens = _tokens(norm, slot_start, slot_end)
        if not slot_tokens:
            return []
        readings = _EXTRACTORS[kind](norm, slot_tokens)
        if not readings:
            return []
        options.append(list(readings))
        slot_token_count += len(slot_tokens)

    reading_count = 1
    for slot_options in options:
        reading_count *= len(slot_options)
    if reading_count > MAX_READINGS:
        _reject(Reason.TOO_MANY_READINGS)
        return []

    # Specificity: the share of tokens matched by the rule's own command words.
    score = round(0.5 + 0.5 * (len(span_tokens) - slot_token_count) / len(span_tokens), 4)
    if reading_count > 1:
        notes.append(f"one of {reading_count} alternative readings")
    return [
        Candidate(
            pattern.intent,
            copy.deepcopy(dict(zip(pattern.slot_names, combo, strict=True))),  # no shared slot objects
            score,
            pattern.rule_id,
            list(notes),
        )
        for combo in itertools.product(*options)
    ]


def _tokens(norm: Normalized, start: int, end: int) -> tuple[Token, ...] | None:
    """Tokens inside ``[start, end)``, or None if a token straddles a boundary."""
    inside = []
    for token in norm.tokens:
        if token.start >= start and token.end <= end:
            inside.append(token)
        elif token.start < end and token.end > start:
            return None
    return tuple(inside)


# Slot extractors (keyed by patterns.EXTRACTORS kind). Each returns every reading; [] = no match.


def _names(norm: Normalized, toks: Sequence[Token]) -> list[Slot]:
    text = norm.text[toks[0].start:toks[-1].end]
    if " ".join(t.lower for t in toks) in patterns.PRONOUNS:
        return [{"kind": "pronoun", "text": text}]
    if len(toks) == 2 and toks[0].kind == "word" and toks[0].lower == patterns.ARTICLE:
        toks = toks[1:]  # "the score" names score
        text = norm.text[toks[0].start:toks[0].end]
    if (
        len(toks) == 1
        and toks[0].kind == "word"
        and patterns.IDENTIFIER.fullmatch(text)
        and not is_reserved(text)
    ):
        return [{"kind": "name", "text": text}]
    return []


def _counts(norm: Normalized, toks: Sequence[Token]) -> list[Slot]:
    if len(toks) == 1 and toks[0].kind == "number":
        return [{"kind": "count", "text": toks[0].text}]
    if len(toks) == 1 and toks[0].kind == "word" and toks[0].lower in patterns.NUMBER_WORDS:
        return [{"kind": "count", "text": patterns.NUMBER_WORDS[toks[0].lower]}]
    return []


def _values(norm: Normalized, toks: Sequence[Token]) -> list[Slot]:
    # One statement per sentence: "VALUE and STMT" is rejected (LANGUAGE_SPEC.md 6.3).
    end = toks[-1].end
    for k in range(1, len(toks) - 1):
        is_and = toks[k].kind == "word" and toks[k].lower == patterns.CONTINUATION_WORD
        if is_and and _is_statement(norm, toks[k + 1].start, end):
            _reject(Reason.REJECT_AND_CONTINUATION)
            return []
    parts = _split(toks, patterns.ALTERNATIVE_WORD)
    if len(parts) > MAX_ALTERNATIVES:
        _reject(Reason.TOO_MANY_ALTERNATIVES)
        return []
    readings: list[Slot] = []
    for part in parts:
        value = _expression(norm, part)
        if value is None:
            return []
        readings.append(value)
    return readings


@functools.lru_cache(maxsize=4096)
def _is_statement(norm: Normalized, start: int, end: int) -> bool:
    """Whether ``norm.text[start:end]`` is a whole statement; memoized so nested ``and``s stay polynomial.

    Failures inside this probe are not reasons for the sentence, so recording is suspended.
    """
    with _recording(None):
        return any(_match(p, norm, start, end) for p in patterns.PATTERNS)


def _conditions(norm: Normalized, toks: Sequence[Token]) -> list[Slot]:
    found: list[tuple[int, int, str]] = []
    i = 0
    while i < len(toks):
        hit = next(((len(words), op) for words, op in _COMPARISON_WORDS if _phrase_at(toks, i, words)), None)
        if hit is None:
            i += 1
        else:
            found.append((i, *hit))
            i += hit[0]
    if len(found) != 1:
        return []
    position, width, op = found[0]
    left, right = toks[:position], toks[position + width:]
    if not left or not right:
        return []
    return [
        {"kind": "condition", "op": op, "left": lhs, "right": rhs}
        for lhs, rhs in itertools.product(_values(norm, left), _values(norm, right))
    ]


def _statements(norm: Normalized, toks: Sequence[Token]) -> list[Slot]:
    # Exactly one statement (decision D-4); "STMT and STMT" fails in the body's value slot.
    start, end = toks[0].start, toks[-1].end
    if any(t.kind == "word" and t.lower in patterns.ELSE_WORDS for t in toks):
        return []
    return [
        {"kind": "statement", "intent": c.intent, "slots": c.slots}
        for p in _BODY_PATTERNS
        for c in _match(p, norm, start, end)
    ]


_EXTRACTORS: dict[str, Callable[[Normalized, Sequence[Token]], list[Slot]]] = {
    "name": _names,
    "value": _values,
    "condition": _conditions,
    "statement": _statements,
    "count": _counts,
}
_BODY_PATTERNS = tuple(p for p in patterns.PATTERNS if p.intent in patterns.BLOCK_BODY_INTENTS)
_COMPARISON_WORDS = tuple((tuple(phrase.split()), op) for phrase, op in patterns.COMPARISONS)
_OPERATOR_WORDS = tuple((tuple(phrase.split()), op) for phrase, op in patterns.BINARY_OPERATORS)


# Value expressions (LANGUAGE_SPEC.md 6.1)

class _Item(NamedTuple):
    """A flattened expression element: an operand slot, a binary operator, or unary minus."""

    kind: Literal["operand", "op", "neg"]
    value: Any = None  # Slot for "operand", operator symbol for "op"


_NEG = _Item("neg")


def _expression(norm: Normalized, toks: Sequence[Token]) -> Slot | None:
    """Parse operands joined by operator words, with standard precedence."""
    items = _expression_items(norm, toks)
    if items is None:
        return None
    position = 0

    def unary() -> Slot:
        nonlocal position
        negations = 0
        while items[position].kind == "neg":  # iterative: long "negative" chains cannot recurse
            negations += 1
            position += 1
        value: Slot = items[position].value
        position += 1
        for _ in range(negations):
            value = {"kind": "neg", "operand": value}
        return value

    def binary(ops: frozenset[str], operand: Callable[[], Slot]) -> Slot:
        nonlocal position
        left = operand()
        while position < len(items) and items[position].kind == "op" and items[position].value in ops:
            op = items[position].value
            position += 1
            left = {"kind": "binop", "op": op, "left": left, "right": operand()}
        return left

    def term() -> Slot:
        return binary(frozenset("*/"), unary)

    return binary(frozenset("+-"), term)


def _expression_items(norm: Normalized, toks: Sequence[Token]) -> list[_Item] | None:
    """Flatten into operands, binary operators and unary-minus markers; None if malformed."""
    items: list[_Item] = []
    i, expect_operand = 0, True
    while i < len(toks):
        if expect_operand:
            if _is_unary_minus(toks, i):
                items.append(_NEG)
                i += 1
                continue
            if _operator_at(toks, i) is not None:
                return None  # e.g. a value starting with "minus"
            j = i
            while j < len(toks) and _operator_at(toks, j) is None and not _is_unary_minus(toks, j):
                j += 1
            operand = _operand(norm, toks[i:j])
            if operand is None:
                return None
            items.append(_Item("operand", operand))
            i, expect_operand = j, False
        else:
            found = _operator_at(toks, i)
            if found is None:
                return None
            width, op = found
            items.append(_Item("op", op))
            i, expect_operand = i + width, True
    return None if expect_operand else items


def _is_unary_minus(toks: Sequence[Token], i: int) -> bool:
    token = toks[i]
    if token.kind == "word" and token.lower == patterns.UNARY_MINUS_WORD:
        return True
    return (
        token.kind == "symbol"
        and token.text == "-"
        and i + 1 < len(toks)
        and toks[i + 1].kind == "number"
        and toks[i + 1].start == token.end
    )


def _operator_at(toks: Sequence[Token], i: int) -> tuple[int, str] | None:
    for words, op in _OPERATOR_WORDS:
        if _phrase_at(toks, i, words):
            return len(words), op
    return None


def _operand(norm: Normalized, run: Sequence[Token]) -> Slot | None:
    if not run:
        return None
    if len(run) == 1 and run[0].kind == "number":
        return {"kind": "number", "text": run[0].text}
    if len(run) == 1 and run[0].kind == "string":
        return {"kind": "string", "text": run[0].text, "quoted": True}
    if any(t.kind in ("string", "symbol") for t in run):
        return None
    text = norm.text[run[0].start:run[-1].end]
    if " ".join(t.lower for t in run) in patterns.PRONOUNS:
        return {"kind": "pronoun", "text": text}
    return {"kind": "word", "text": text}


def _phrase_at(toks: Sequence[Token], i: int, words: tuple[str, ...]) -> bool:
    if i + len(words) > len(toks):
        return False
    return all(toks[i + k].kind != "string" and toks[i + k].lower == w for k, w in enumerate(words))


def _split(toks: Sequence[Token], separator: str) -> list[Sequence[Token]]:
    """Split on a separator word (never inside quotes)."""
    parts: list[Sequence[Token]] = []
    current: list[Token] = []
    for token in toks:
        if token.kind == "word" and token.lower == separator:
            parts.append(current)
            current = []
        else:
            current.append(token)
    parts.append(current)
    return parts
