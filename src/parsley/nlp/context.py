"""[N1] Context resolver: symbol-table-aware resolution, reference stack, typos (Phase 6).

``resolve(candidates, session)`` turns each candidate's unresolved ``word`` and ``pronoun``
slots into ``name`` or ``string`` slots, using the fixed policy of LANGUAGE_SPEC.md
sections 4 and 5, then re-scores and re-ranks the candidates with type hints.

It only reads the session (``Session.symbols``, a read-only view, and the reference stack)
and never changes it or its input candidates. It never guesses: a near-miss of a declared
name, or a pronoun with an empty reference stack, leaves the slot unresolved and returns a
question instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from parsley.diagnostics import Diagnostic
from parsley.nlp.candidates import Candidate
from parsley.nlp.patterns import COMMON_WORDS
from parsley.session import Session

STAGE = "context"
TYPO_OPTIONS = ("yes", "no")
UPDATE_INTENTS = frozenset({"increment", "decrement", "multiply", "divide"})

# Type-hint re-scoring (LANGUAGE_SPEC.md 5): small nudges, so they only reorder close calls.
UNDECLARED_PENALTY = 0.1  # a word made an identifier by rule 4 is not declared (E201 ahead)
TEXT_UPDATE_PENALTY = 0.1  # increase/decrease/multiply/divide on a text variable
NUMBER_UPDATE_BONUS = 0.05  # ... on a number variable by a number

Slot = dict[str, Any]


@dataclass(frozen=True)
class Resolution:
    """One candidate after context resolution; ``question`` is set when it cannot be resolved."""

    candidate: Candidate
    question: str | None = None
    options: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


def resolve(candidates: Sequence[Candidate], session: Session) -> list[Resolution]:
    """Resolve and re-score every candidate; best score first (ties keep their order)."""
    symbols = session.symbols
    names = [s.name for s in sorted(symbols.values(), key=lambda s: s.declared_at)]
    resolutions = [
        _Resolver(symbols, names, tuple(session.ref_stack)).resolve(c) for c in candidates
    ]
    resolutions.sort(key=lambda r: r.candidate.score, reverse=True)
    return resolutions


def edit_distance(a: str, b: str) -> int:
    """Optimal-string-alignment distance: insert, delete, substitute or swap neighbours."""
    rows = [list(range(len(b) + 1))]
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            row[j] = min(rows[i - 1][j] + 1, row[j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], rows[i - 2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]


def near_miss(word: str, names: Sequence[str]) -> str | None:
    """The declared name ``word`` is likely a typo of (LANGUAGE_SPEC.md 4 rule 3), or None.

    The closest name wins; on a tie, the first in ``names`` (declaration order).
    """
    if word.lower() in COMMON_WORDS:
        return None
    best: str | None = None
    best_distance = 0
    for name in names:
        limit = _typo_limit(len(name))
        if limit == 0 or name == word:
            continue
        distance = edit_distance(word, name)
        if distance <= limit and (best is None or distance < best_distance):
            best, best_distance = name, distance
    return best


def _typo_limit(length: int) -> int:
    if length <= 2:
        return 0
    return 1 if length <= 5 else 2


class _Resolver:
    """Resolves one candidate; records the first question and counts undeclared operands."""

    def __init__(self, symbols: Mapping[str, Any], names: list[str], ref_stack: tuple[str, ...]) -> None:
        self._known = symbols
        self._names = names
        self._ref_stack = ref_stack
        self._question: str | None = None
        self._options: tuple[str, ...] = ()
        self._undeclared = 0

    def resolve(self, candidate: Candidate) -> Resolution:
        slots = self._slots(candidate.intent, candidate.slots)
        intent, notes, diagnostics = candidate.intent, list(candidate.notes), ()
        target = slots.get("name")
        if (
            intent == "assign"
            and _is_name(target)
            and target["text"] not in self._known
            and slots.get("value") is not None  # nothing to declare until the value is given
            and self._question is None  # a near-miss target is asked about, never created
        ):
            name = target["text"]
            intent = "declare"
            notes.append(f"implicit declaration: {name} was not created yet")
            diagnostics = (Diagnostic("warning", STAGE, "W301", f"{name} was not created yet, so this creates it"),)
        score = self._rescore(intent, slots, candidate.score)
        resolved = replace(candidate, intent=intent, slots=slots, score=score, notes=notes)
        return Resolution(resolved, self._question, self._options, diagnostics)

    def _ask(self, question: str, options: tuple[str, ...] = ()) -> None:
        if self._question is None:
            self._question, self._options = question, options

    # Slots

    def _slots(self, intent: str, raw: Mapping[str, Slot | None]) -> dict[str, Slot | None]:
        return {
            key: self._target(slot, intent) if key == "name" else self._value(slot) for key, slot in raw.items()
        }

    def _target(self, slot: Slot | None, intent: str) -> Slot | None:
        """A NAME position: a pronoun resolves through the reference stack; outside an
        explicit declaration, an undeclared near-miss of a declared name asks (decision D-12)."""
        if slot is None:
            return None
        if slot.get("kind") == "pronoun":
            return self._pronoun(slot)
        text = slot.get("text", "")
        if intent != "declare" and slot.get("kind") == "name" and text not in self._known:
            match = near_miss(text, self._names)
            if match is not None:
                self._ask(f"Did you mean the variable {match}?", TYPO_OPTIONS)
        return dict(slot)

    def _value(self, slot: Slot | None, operand: bool = False) -> Slot | None:
        if slot is None:
            return None
        kind = slot.get("kind")
        if kind == "word":
            return self._word(slot, operand)
        if kind == "pronoun":
            return self._pronoun(slot)
        if kind == "binop":
            return {**slot, "left": self._value(slot["left"], True), "right": self._value(slot["right"], True)}
        if kind == "neg":
            return {**slot, "operand": self._value(slot["operand"], True)}
        if kind == "condition":
            return {**slot, "left": self._value(slot["left"]), "right": self._value(slot["right"])}
        if kind == "statement":
            return {**slot, "slots": self._slots(slot["intent"], slot["slots"])}
        return dict(slot)

    def _word(self, slot: Slot, operand: bool) -> Slot:
        """LANGUAGE_SPEC.md 4: declared name, near miss (ask), operand, else text."""
        text = slot["text"]
        if text in self._known:
            return {"kind": "name", "text": text}
        match = near_miss(text, self._names)
        if match is not None:
            self._ask(f"Did you mean the variable {match}?", TYPO_OPTIONS)
            return dict(slot)
        if operand:
            self._undeclared += 1
            return {"kind": "name", "text": text}
        return {"kind": "string", "text": text, "quoted": False}

    def _pronoun(self, slot: Slot) -> Slot:
        if self._ref_stack:
            return {"kind": "name", "text": self._ref_stack[-1]}
        self._ask(f'Which variable does "{slot["text"]}" refer to?')
        return dict(slot)

    # Type hints

    def _rescore(self, intent: str, slots: Mapping[str, Slot | None], score: float) -> float:
        if self._undeclared:
            score -= UNDECLARED_PENALTY
        target = slots.get("name")
        if intent in UPDATE_INTENTS and _is_name(target):
            target_type = self._type_of(target)
            if target_type == "string":
                score -= TEXT_UPDATE_PENALTY
            elif target_type == "number" and self._type_of(slots.get("amount")) == "number":
                score += NUMBER_UPDATE_BONUS
        return round(min(1.0, max(0.0, score)), 4)

    def _type_of(self, slot: Slot | None) -> str | None:
        if slot is None:
            return None
        kind = slot.get("kind")
        if kind == "number":
            return "number"
        if kind == "string":
            return "string"
        if kind == "name":
            symbol = self._known.get(slot["text"])
            return None if symbol is None else symbol.type
        return None


def _is_name(slot: Slot | None) -> bool:
    return slot is not None and slot.get("kind") == "name"
