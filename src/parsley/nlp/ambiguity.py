"""[N2] Ambiguity gate: accept / clarify / reject + questions (Phase 6).

So far this module holds the missing-slot questions (LANGUAGE_SPEC.md 7.1). The score-margin
decision, alternatives and operator-scope questions are the next step.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parsley.nlp.candidates import Candidate

# (intent, slot) -> question; {name} is the target's text, spelled as typed.
_MISSING_SLOT_QUESTIONS: dict[tuple[str, str], str] = {
    ("increment", "amount"): "By how much should {name} increase?",
    ("decrement", "amount"): "By how much should {name} decrease?",
    ("multiply", "amount"): "By how much should {name} be multiplied?",
    ("divide", "amount"): "By how much should {name} be divided?",
    ("assign", "value"): "What value should {name} be set to?",
    ("print", "value"): "What should be printed?",
    ("repeat", "count"): "How many times should it repeat?",
}


def missing_slot_question(candidate: Candidate) -> str | None:
    """The question for the first required slot missing from the English, or None."""
    return _first_missing(candidate.intent, candidate.slots)


def _first_missing(intent: str, slots: Mapping[str, Any]) -> str | None:
    for key, slot in slots.items():
        if slot is None:
            target = slots.get("name")
            name = target.get("text", "it") if isinstance(target, Mapping) else "it"
            template = _MISSING_SLOT_QUESTIONS.get((intent, key), "What is missing from this sentence?")
            return template.format(name=name)
        if isinstance(slot, Mapping) and slot.get("kind") == "statement":
            nested = _first_missing(slot["intent"], slot["slots"])
            if nested is not None:
                return nested
    return None
