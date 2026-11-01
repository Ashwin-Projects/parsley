"""Strict validation of model output: only data that fits the candidate schema gets through.

``validate(text, sentence)`` reads one raw model response. Model text is parsed as JSON and
never evaluated or executed. Whatever does not fit is discarded with a recorded reason: the
whole response if the envelope is wrong, otherwise that one reading. Slots are rebuilt key by
key, so nothing unknown survives.

Three rules keep the model below the deterministic stages:

- **N1 stays in charge.** In a value the model may write only ``number``, a quoted
  ``string``, ``word`` and ``pronoun`` operands. A ``name`` is allowed only in a NAME
  position, so the model cannot settle variable vs. text, a pronoun or a typo.
- **Grounding.** Every name, word, pronoun, number and quoted string must come from the
  sentence, spelled the same way, so a hostile response can only rearrange the user's own
  words. A number word grounds its number. Operators and intents are the model's reading.
- **One statement.** Block bodies follow LANGUAGE_SPEC.md 6.3, and a reading holds one
  statement: no extra fields and no lists of statements.
- **Coverage.** Grounding checks what a reading says, not what it leaves out, and a full
  check would refuse every paraphrase (the point of asking a model). So two omissions that
  change the meaning are checked: a reading that drops a negation, and one that drops a
  second statement after ``and`` or ``then`` when that clause matches a supported pattern.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, NoReturn

from parsley.compiler.ir_builder import ARITH_OPS, COMPARE_OPS
from parsley.keywords import is_reserved
from parsley.llm.prompt import MAX_READINGS, SlotSpec, intent_slots
from parsley.nlp import patterns
from parsley.nlp.candidates import is_statement
from parsley.nlp.normalizer import normalize

MAX_OUTPUT_CHARS = 64 * 1024
MAX_SLOT_DEPTH = 16
MIN_CONFIDENCE = 0.5  # below this the model itself does not believe the reading: no guessing
MAX_DETAIL_CHARS = 200

_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_COUNT = re.compile(r"[0-9]+")
_READING_KEYS = frozenset({"intent", "slots", "confidence"})
_NEGATORS = frozenset({"not", "never", "no", "don't", "dont", "cannot", "can't", "won't"})
_THEN = "then"

Slot = dict[str, Any]


class Discarded(StrEnum):
    """Why model output was dropped; shown in the trace (LANGUAGE_SPEC.md 7.5)."""

    TOO_LONG = "too_long"
    MALFORMED_JSON = "malformed_json"
    BAD_SHAPE = "bad_shape"
    TOO_MANY_READINGS = "too_many_readings"
    UNKNOWN_INTENT = "unknown_intent"
    BAD_CONFIDENCE = "bad_confidence"
    LOW_CONFIDENCE = "low_confidence"
    BAD_SLOTS = "bad_slots"
    NOT_GROUNDED = "not_grounded"
    NOT_COVERED = "not_covered"


@dataclass(frozen=True)
class Reading:
    """One valid reading: its slots use the ARCHITECTURE.md 2.3 shapes."""

    intent: str
    slots: dict[str, Slot | None]
    confidence: float


@dataclass(frozen=True)
class Discard:
    """One dropped reading or response, for the trace."""

    reason: Discarded
    detail: str


@dataclass(frozen=True)
class Validated:
    """What is left of one model response."""

    readings: tuple[Reading, ...] = ()
    discarded: tuple[Discard, ...] = ()


class _Reject(Exception):
    def __init__(self, reason: Discarded, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


def _bad_slots(detail: str) -> NoReturn:
    raise _Reject(Discarded.BAD_SLOTS, detail)


def _not_grounded(value: str) -> NoReturn:
    raise _Reject(Discarded.NOT_GROUNDED, f"{_short(value)} is not in the sentence")


def _short(value: object) -> str:
    """A printable, bounded form of model text."""
    return ascii(value)[:MAX_DETAIL_CHARS]


def validate(text: str, sentence: str) -> Validated:
    """The valid readings in one model response, and why the rest were dropped."""
    if len(text) > MAX_OUTPUT_CHARS:
        return _rejected(Discarded.TOO_LONG, f"{len(text)} characters")
    try:
        items = _envelope(text)
    except _Reject as rejected:
        return _rejected(rejected.reason, str(rejected))
    grounds = _Grounds(sentence)
    readings: list[Reading] = []
    discarded: list[Discard] = []
    for item in items[:MAX_READINGS]:
        try:
            readings.append(_reading(item, grounds))
        except _Reject as rejected:
            discarded.append(Discard(rejected.reason, str(rejected)))
    if len(items) > MAX_READINGS:
        discarded.append(Discard(Discarded.TOO_MANY_READINGS, f"{len(items)} readings; the first {MAX_READINGS} kept"))
    return Validated(tuple(readings), tuple(discarded))


def _rejected(reason: Discarded, detail: str) -> Validated:
    return Validated(discarded=(Discard(reason, detail),))


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def _no_constant(name: str) -> NoReturn:
    raise ValueError(f"{name} is not JSON")


def _envelope(text: str) -> list[Any]:
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (ValueError, RecursionError) as error:
        raise _Reject(Discarded.MALFORMED_JSON, type(error).__name__) from error
    if not isinstance(data, dict) or set(data) != {"readings"} or not isinstance(data["readings"], list):
        raise _Reject(Discarded.BAD_SHAPE, 'expected exactly {"readings": [...]}')
    return data["readings"]


def _reading(item: Any, grounds: _Grounds) -> Reading:
    if not isinstance(item, dict) or set(item) != _READING_KEYS or not isinstance(item["slots"], dict):
        raise _Reject(Discarded.BAD_SHAPE, "a reading has exactly intent, slots and confidence")
    intent = item["intent"]
    if not isinstance(intent, str) or intent not in intent_slots():
        raise _Reject(Discarded.UNKNOWN_INTENT, _short(intent))
    confidence = item["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise _Reject(Discarded.BAD_CONFIDENCE, _short(confidence))
    if confidence < MIN_CONFIDENCE:
        raise _Reject(Discarded.LOW_CONFIDENCE, f"{confidence} is below {MIN_CONFIDENCE}")
    slots = _slots(intent, item["slots"], grounds, 0)
    _check_coverage(intent, slots, grounds)
    return Reading(intent, slots, float(confidence))


def _slot_words(value: Any) -> list[str]:
    """Every word of the slot texts under ``value``."""
    if not isinstance(value, dict):
        return []
    text = value.get("text")
    own = text.split() if isinstance(text, str) else []
    return [*own, *(word for item in value.values() for word in _slot_words(item))]


def _check_coverage(intent: str, slots: dict[str, Slot | None], grounds: _Grounds) -> None:
    """Refuse a reading that drops a negation or a second statement (see the module docstring).

    An ``if`` may express a negation through its comparison, and its ``then`` is its own.
    """
    tokens = [t for t in grounds.norm.tokens if t.kind == "word"]
    used = {word.lower() for word in _slot_words(slots)}
    if intent != "if":
        dropped = sorted({t.lower for t in tokens if t.lower in _NEGATORS} - used)
        if dropped:
            raise _Reject(Discarded.NOT_COVERED, f"the reading drops {_short(dropped[0])}")
    joins = {patterns.CONTINUATION_WORD} if intent == "if" else {patterns.CONTINUATION_WORD, _THEN}
    everything = grounds.norm.tokens
    for position, token in enumerate(everything):
        if token.kind != "word" or token.lower not in joins:
            continue
        rest = position + 1
        if rest < len(everything) and everything[rest].lower == _THEN:
            rest += 1
        if rest < len(everything) and is_statement(grounds.norm, everything[rest].start):
            raise _Reject(Discarded.NOT_COVERED, "the reading drops a second statement")


class _Grounds:
    """What the sentence actually says; a slot's text must come from here."""

    def __init__(self, sentence: str) -> None:
        self.norm = normalize(sentence)
        tokens = self.norm.tokens
        self.words = {t.text for t in tokens if t.kind in ("word", "number")}
        self.lower_words = {t.lower for t in tokens if t.kind == "word"}
        self.quoted = {t.text for t in tokens if t.kind == "string"}
        self.numbers = {t.text for t in tokens if t.kind == "number"}
        self.numbers |= {patterns.NUMBER_WORDS[w] for w in self.lower_words & patterns.NUMBER_WORDS.keys()}


def _keys(slot: Any, *keys: str) -> Mapping[str, Any]:
    if not isinstance(slot, dict) or set(slot) != {"kind", *keys}:
        _bad_slots(f"expected the keys kind, {', '.join(keys)} in {_short(slot)}")
    return slot


def _text(slot: Mapping[str, Any]) -> str:
    text = slot["text"]
    if not isinstance(text, str) or not text.strip():
        _bad_slots(f"{_short(text)} is not text")
    return text


def _slots(intent: str, raw: dict[str, Any], grounds: _Grounds, depth: int) -> dict[str, Slot | None]:
    schema = intent_slots()[intent]
    if not raw.keys() <= schema.keys():
        _bad_slots(f"{intent} has no slot {_short(sorted(raw.keys() - schema.keys()))}")
    slots: dict[str, Slot | None] = {}
    for name, spec in schema.items():
        if name not in raw:
            if spec.required:
                _bad_slots(f"{intent} needs the slot {name}")
        elif raw[name] is None:
            if not spec.nullable:
                _bad_slots(f"the slot {name} of {intent} cannot be null")
            slots[name] = None
        else:
            slots[name] = _slot(spec, raw[name], grounds, depth)
    return slots


def _slot(spec: SlotSpec, slot: Any, grounds: _Grounds, depth: int) -> Slot:
    if spec.kind == "name":
        return _name(slot, grounds)
    if spec.kind == "value":
        return _value(slot, grounds, depth)
    if spec.kind == "condition":
        return _condition(slot, grounds, depth)
    if spec.kind == "statement":
        return _statement(slot, grounds, depth)
    return _count(slot, grounds)


def _kind(slot: Any) -> Any:
    return slot.get("kind") if isinstance(slot, dict) else None


def _name(slot: Any, grounds: _Grounds) -> Slot:
    if _kind(slot) == "pronoun":
        return _pronoun(slot, grounds)
    if _kind(slot) != "name":
        _bad_slots(f"a NAME position needs a name or a pronoun, not {_short(_kind(slot))}")
    text = _text(_keys(slot, "text"))
    if not patterns.IDENTIFIER.fullmatch(text) or is_reserved(text):
        _bad_slots(f"{_short(text)} is not a legal identifier")
    if text not in grounds.words:
        _not_grounded(text)
    return {"kind": "name", "text": text}


def _pronoun(slot: Any, grounds: _Grounds) -> Slot:
    text = _text(_keys(slot, "text"))
    lowered = text.lower()
    if lowered not in patterns.PRONOUNS:
        _bad_slots(f"{_short(text)} is not a pronoun")
    if not set(lowered.split()) <= grounds.lower_words:
        _not_grounded(text)
    return {"kind": "pronoun", "text": text}


def _value(slot: Any, grounds: _Grounds, depth: int) -> Slot:
    if depth >= MAX_SLOT_DEPTH:
        _bad_slots("the value is nested too deeply")
    kind = _kind(slot)
    if kind == "number":
        return _number(slot, grounds)
    if kind == "string":
        return _string(slot, grounds)
    if kind == "word":
        return _word(slot, grounds)
    if kind == "pronoun":
        return _pronoun(slot, grounds)
    if kind == "binop":
        fields = _keys(slot, "op", "left", "right")
        return {
            "kind": "binop", "op": _operator(fields, ARITH_OPS),
            "left": _value(fields["left"], grounds, depth + 1),
            "right": _value(fields["right"], grounds, depth + 1),
        }
    if kind == "neg":
        return {"kind": "neg", "operand": _value(_keys(slot, "operand")["operand"], grounds, depth + 1)}
    _bad_slots(f"{_short(kind)} cannot be a value")


def _operator(fields: Mapping[str, Any], allowed: frozenset[str]) -> str:
    op = fields["op"]
    if not isinstance(op, str) or op not in allowed:
        _bad_slots(f"unknown operator {_short(op)}")
    return op


def _number(slot: Any, grounds: _Grounds) -> Slot:
    text = _text(_keys(slot, "text"))
    if not _NUMBER.fullmatch(text):
        _bad_slots(f"{_short(text)} is not a number")
    if text not in grounds.numbers:
        _not_grounded(text)
    return {"kind": "number", "text": text}


def _string(slot: Any, grounds: _Grounds) -> Slot:
    fields = _keys(slot, "text", "quoted")
    if fields["quoted"] is not True or not isinstance(fields["text"], str):
        _bad_slots("only quoted text is a string; a bare word is a word slot")
    text = fields["text"]
    if text not in grounds.quoted:
        _not_grounded(text)
    return {"kind": "string", "text": text, "quoted": True}


def _word(slot: Any, grounds: _Grounds) -> Slot:
    text = _text(_keys(slot, "text"))
    if not set(text.split()) <= grounds.words:
        _not_grounded(text)
    return {"kind": "word", "text": text}


def _condition(slot: Any, grounds: _Grounds, depth: int) -> Slot:
    if _kind(slot) != "condition":
        _bad_slots(f"expected a condition, not {_short(_kind(slot))}")
    fields = _keys(slot, "op", "left", "right")
    return {
        "kind": "condition", "op": _operator(fields, COMPARE_OPS),
        "left": _value(fields["left"], grounds, depth + 1),
        "right": _value(fields["right"], grounds, depth + 1),
    }


def _statement(slot: Any, grounds: _Grounds, depth: int) -> Slot:
    if _kind(slot) != "statement":
        _bad_slots(f"a block body is one statement, not {_short(_kind(slot))}")
    fields = _keys(slot, "intent", "slots")
    intent, body = fields["intent"], fields["slots"]
    if not isinstance(intent, str) or intent not in patterns.BLOCK_BODY_INTENTS or not isinstance(body, dict):
        _bad_slots(f"{_short(intent)} cannot be a block body (LANGUAGE_SPEC.md 6.3)")
    return {"kind": "statement", "intent": intent, "slots": _slots(intent, body, grounds, depth + 1)}


def _count(slot: Any, grounds: _Grounds) -> Slot:
    if _kind(slot) != "count":
        _bad_slots(f"expected a count, not {_short(_kind(slot))}")
    text = _text(_keys(slot, "text"))
    if not _COUNT.fullmatch(text):
        _bad_slots(f"{_short(text)} is not a whole number")
    if text not in grounds.numbers:
        _not_grounded(text)
    return {"kind": "count", "text": text}
