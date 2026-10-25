"""[N2] Ambiguity gate: accept / clarify / reject + questions (Phase 6).

``gate(resolutions)`` takes the context-resolved candidates (best first) and either accepts
the top one or returns a ``Clarification`` (LANGUAGE_SPEC.md 7). Checks, in order:

1. ``alternatives``: two or more different readings score within ``CLARIFY_MARGIN`` of the
   top (``set x to 10 or 20``). Asked first, so a typo inside one reading is asked about
   only once that reading is chosen.
2. ``typo`` / ``pronoun``: the context resolver's question (which variable is meant). Asked
   before operator scope, whose two readings share the same words, so a target is settled
   once for both groupings.
3. ``operator_scope``: a multiply/divide whose amount has ``plus``/``minus`` at the top
   (``multiply x by 2 plus 3``), at any depth; the two groupings become two readings.
4. ``missing_slot``: a required slot the English left out (what is missing).

Names the user confirmed as new (a "no" to a typo question) travel with every later
clarification of the same sentence, so a refused typo question is never asked again.

Unsupported input never reaches the gate (the pipeline rejects it first).
``apply_answer`` merges the user's reply into the source candidate (before context
resolution), so the pipeline can re-run it through context, the gate, IR and semantics.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from parsley.keywords import is_reserved
from parsley.nlp.candidates import Candidate, parse_count, parse_value
from parsley.nlp.context import Resolution
from parsley.nlp.patterns import IDENTIFIER

# Readings whose scores differ by less than this are too close to choose between
# (LANGUAGE_SPEC.md 7). It is equal to the smallest context re-scoring nudge, so a
# candidate that type hints moved ahead by a full nudge is accepted.
CLARIFY_MARGIN = 0.05

Kind = Literal["missing_slot", "alternatives", "operator_scope", "typo", "pronoun"]
Slot = dict[str, Any]

_YES = frozenset({"yes", "y"})
_NO = frozenset({"no", "n"})
_ARITH_WORDS = {"+": "plus", "-": "minus", "*": "times", "/": "divided by"}
_COMPARE_WORDS = {
    ">": "is greater than", "<": "is less than", "==": "is equal to", "!=": "is not equal to",
    ">=": "is greater than or equal to", "<=": "is less than or equal to",
}
_SCOPE_INTENTS = frozenset({"multiply", "divide"})
_INTENT_TEMPLATES = {
    "declare": "create variable {name} with value {value}",
    "assign": "set {name} to {value}",
    "increment": "increase {name} by {amount}",
    "decrement": "decrease {name} by {amount}",
    "multiply": "multiply {name} by {amount}",
    "divide": "divide {name} by {amount}",
    "print": "print {value}",
    "if": "if {condition} then {then}",
    "repeat": "repeat {count} times {body}",
}

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


@dataclass(frozen=True)
class Clarification:
    """A question for the user, and where the answer goes."""

    kind: Kind
    question: str
    options: tuple[str, ...] = ()  # empty for a free answer
    readings: tuple[Candidate, ...] = ()  # alternatives / operator_scope: one per option
    candidate: Candidate | None = None  # missing_slot / typo / pronoun: the answer goes in here
    path: str = ""  # dotted slot path the answer fills
    suggestion: str | None = None  # typo: the declared name
    accepted: frozenset[str] = frozenset()  # names already confirmed as new in this sentence


@dataclass(frozen=True)
class GateDecision:
    decision: Literal["ACCEPT", "CLARIFY"]
    resolution: Resolution | None = None  # set when accepted
    clarification: Clarification | None = None  # set when clarifying

    @property
    def candidate(self) -> Candidate | None:
        return None if self.resolution is None else self.resolution.candidate


@dataclass(frozen=True)
class Merged:
    """A source candidate with the answer merged in; ``accepted`` names skip the typo check."""

    candidate: Candidate
    accepted: frozenset[str] = frozenset()


def gate(resolutions: Sequence[Resolution], accepted: frozenset[str] = frozenset()) -> GateDecision:
    """Accept the top resolution, or say what to ask (see the module docstring for the order).

    ``accepted`` names were confirmed as new earlier in this sentence; they are carried on.
    """
    top = resolutions[0]
    clarification = _clarification(top, resolutions)
    if clarification is None:
        return GateDecision("ACCEPT", resolution=top)
    return GateDecision("CLARIFY", clarification=replace(clarification, accepted=accepted))


def _clarification(top: Resolution, resolutions: Sequence[Resolution]) -> Clarification | None:
    close = _close_readings(resolutions)
    if len(close) > 1:
        return _alternatives(close)
    source = _source(top)
    if top.question is not None and top.kind is not None:
        return Clarification(
            top.kind, top.question, top.options, candidate=source, path=top.path, suggestion=top.suggestion,
        )
    scope = _operator_scope(top)
    if scope is not None:
        return scope
    missing = _first_missing(top.candidate.intent, top.candidate.slots, "")
    if missing is not None:
        path, question = missing
        return Clarification("missing_slot", question, candidate=source, path=path)
    return None


def missing_slot_question(candidate: Candidate) -> str | None:
    """The question for the first required slot missing from the English, or None."""
    missing = _first_missing(candidate.intent, candidate.slots, "")
    return None if missing is None else missing[1]


def apply_answer(clarification: Clarification, answer: str) -> Merged | None:
    """Merge the user's answer; None if the answer does not fit the question."""
    merged = _merge(clarification, answer.strip())
    if merged is None:
        return None
    return replace(merged, accepted=merged.accepted | clarification.accepted)


def _merge(clarification: Clarification, reply: str) -> Merged | None:
    if clarification.kind in ("alternatives", "operator_scope"):
        index = _choice(reply, clarification.options)
        return None if index is None else Merged(clarification.readings[index])
    candidate, path = clarification.candidate, clarification.path
    if candidate is None:
        return None
    if clarification.kind == "missing_slot":
        key = path.rsplit(".", 1)[-1]
        slot = parse_count(reply) if key == "count" else parse_value(reply)
        return None if slot is None else Merged(_with(candidate, path, slot))
    if clarification.kind == "pronoun":
        if not IDENTIFIER.fullmatch(reply) or is_reserved(reply):
            return None
        return Merged(_with(candidate, path, {"kind": "name", "text": reply}))
    word = reply.lower().rstrip(".!?")
    original = slot_at(candidate.slots, path)
    if word in _YES and clarification.suggestion is not None:
        return Merged(_with(candidate, path, {"kind": "name", "text": clarification.suggestion}))
    if word in _NO and isinstance(original, Mapping):
        text = original["text"]
        if original.get("kind") == "name":  # a NAME target: the user means a new variable
            return Merged(candidate, frozenset({text}))
        parent = slot_at(candidate.slots, path.rsplit(".", 1)[0]) if "." in path else None
        if isinstance(parent, Mapping) and parent.get("kind") in ("binop", "neg"):
            return Merged(_with(candidate, path, {"kind": "name", "text": text}))  # still rule 4
        return Merged(_with(candidate, path, {"kind": "string", "text": text, "quoted": False}))
    return None


# Slot paths (the dotted paths of ir_builder errors: ``value.left``, ``body.value``)


def slot_at(slots: Mapping[str, Any], path: str) -> Any:
    """The slot at a dotted path, or None."""
    current: Any = {"kind": "statement", "slots": slots}
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        container = current.get("slots") if current.get("kind") == "statement" else current
        current = container.get(key) if isinstance(container, Mapping) else None
    return current


def replace_at(slots: Mapping[str, Any], path: str, new: Slot) -> dict[str, Any]:
    """A deep copy of ``slots`` with the slot at ``path`` replaced."""
    copied: dict[str, Any] = copy.deepcopy(dict(slots))
    container: Any = copied
    *parents, last = path.split(".")
    for key in parents:
        node = container[key]
        container = node["slots"] if node.get("kind") == "statement" else node
    container[last] = copy.deepcopy(new)
    return copied


def _with(candidate: Candidate, path: str, slot: Slot) -> Candidate:
    return replace(candidate, slots=replace_at(candidate.slots, path, slot))


def _source(resolution: Resolution) -> Candidate:
    return resolution.source if resolution.source is not None else resolution.candidate


# 1. Alternatives


def _close_readings(resolutions: Sequence[Resolution]) -> list[Resolution]:
    """Distinct readings scoring within the margin of the top one."""
    top = resolutions[0].candidate.score
    close: list[Resolution] = []
    for r in resolutions:
        if round(top - r.candidate.score, 4) >= CLARIFY_MARGIN:
            continue
        if all((r.candidate.intent, r.candidate.slots) != (c.candidate.intent, c.candidate.slots) for c in close):
            close.append(r)
    return close


def _alternatives(close: Sequence[Resolution]) -> Clarification:
    sources = [_source(r) for r in close]
    options = _differing_values(sources)
    if options is None or len(set(options)) < len(options):
        options = [_describe_statement(s.intent, s.slots) for s in sources]
    return Clarification("alternatives", _join_or(options) + "?", tuple(options), readings=tuple(sources))


def _differing_values(sources: Sequence[Candidate]) -> list[str] | None:
    """Descriptions of the first slot where same-intent readings differ, or None."""
    if len({s.intent for s in sources}) != 1:
        return None

    def first_difference(slot_maps: list[Mapping[str, Any]]) -> list[str] | None:
        for key in slot_maps[0]:
            values = [m.get(key) for m in slot_maps]
            if all(v == values[0] for v in values):
                continue
            if all(isinstance(v, Mapping) and v.get("kind") == "statement" for v in values) and len(
                {v["intent"] for v in values}
            ) == 1:
                return first_difference([v["slots"] for v in values])
            return [_describe(v) for v in values]
        return None

    return first_difference([s.slots for s in sources])


def _join_or(options: Sequence[str]) -> str:
    if len(options) <= 2:
        return " or ".join(options)
    return ", ".join(options[:-1]) + " or " + options[-1]


def _choice(reply: str, options: Sequence[str]) -> int | None:
    """Index of the chosen option: by its text (ignoring case and quotes), else by its 1-based
    number, so "20" picks the option 20 and "2" picks the second option only if no option is "2"."""
    wanted = reply.rstrip(".!?").strip('"').lower()
    matches = [i for i, option in enumerate(options) if option.strip('"').lower() == wanted]
    if len(matches) == 1:
        return matches[0]
    if reply.isascii() and reply.isdigit():
        index = int(reply) - 1
        return index if 0 <= index < len(options) else None
    return None


# 2. Operator scope


def _operator_scope(top: Resolution) -> Clarification | None:
    found = _scope_statement(top.candidate.intent, top.candidate.slots, "")
    if found is None:
        return None
    path, slots = found
    source = _source(top)
    source_slots = source.slots if not path else slot_at(source.slots, path)["slots"]
    amount = slots["amount"]
    op = "*" if (top.candidate.intent if not path else slot_at(top.candidate.slots, path)["intent"]) == "multiply" else "/"
    # Left reading: "x op amount" with standard precedence, i.e. ``x op`` applied to the
    # amount's leftmost operand: 2 plus 3 -> (x*2)+3; 2 minus 3 minus 4 -> ((x*2)-3)-4.
    # Right reading: x op (the whole amount).
    resolved_target = slots["name"]
    options = (
        _describe_grouped(_graft(op, resolved_target, amount)),
        f"{_describe(resolved_target)} {_ARITH_WORDS[op]} ({_describe(amount)})",
    )

    # Both readings become explicit assignments, so choosing one cannot trigger this check again.
    target, src_amount = source_slots["name"], source_slots["amount"]
    left_value = _graft(op, target, src_amount)
    right_value = {"kind": "binop", "op": op, "left": target, "right": src_amount}
    readings = tuple(
        _as_assignment(source, path, {"name": target, "value": value}, f"operator scope: {option}")
        for value, option in ((left_value, options[0]), (right_value, options[1]))
    )
    question = f"Do you mean {options[0]}, or {options[1]}?"
    return Clarification("operator_scope", question, options, readings=readings)


def _graft(op: str, target: Slot, expr: Slot) -> Slot:
    """``target op expr`` with standard precedence: ``op`` (times / divided by) binds to the
    leftmost operand of ``expr``, because no binary operator in ``expr`` binds tighter."""
    if expr.get("kind") == "binop":
        return {**expr, "left": _graft(op, target, expr["left"])}
    return {"kind": "binop", "op": op, "left": target, "right": expr}


def _describe_grouped(slot: Slot) -> str:
    """Like ``_describe``, with every nested operation in parentheses: (x times 2) plus 3."""
    def inner(s: Any) -> str:
        if isinstance(s, Mapping) and s.get("kind") == "binop":
            return f"({_describe_grouped(s)})"
        return _describe(s)

    if slot.get("kind") != "binop":
        return _describe(slot)
    return f"{inner(slot['left'])} {_ARITH_WORDS[slot['op']]} {inner(slot['right'])}"


def _as_assignment(source: Candidate, path: str, slots: Slot, note: str) -> Candidate:
    """``source`` with the statement at ``path`` ("" = top level) replaced by an assignment."""
    notes = [*source.notes, note]
    if path:
        statement = {"kind": "statement", "intent": "assign", "slots": slots}
        return replace(source, slots=replace_at(source.slots, path, statement), notes=notes)
    return replace(source, intent="assign", slots=copy.deepcopy(slots), notes=notes)


def _scope_statement(intent: str, slots: Mapping[str, Any], prefix: str) -> tuple[str, Mapping[str, Any]] | None:
    """The first multiply/divide (path, slots) whose amount is a plus/minus binop."""
    amount = slots.get("amount")
    if (
        intent in _SCOPE_INTENTS
        and isinstance(amount, Mapping)
        and amount.get("kind") == "binop"
        and amount.get("op") in ("+", "-")
    ):
        return prefix, slots
    for key, slot in slots.items():
        if isinstance(slot, Mapping) and slot.get("kind") == "statement":
            path = f"{prefix}.{key}" if prefix else key
            found = _scope_statement(slot["intent"], slot["slots"], path)
            if found is not None:
                return found
    return None


# 4. Missing slots


def _first_missing(intent: str, slots: Mapping[str, Any], prefix: str) -> tuple[str, str] | None:
    for key, slot in slots.items():
        path = f"{prefix}.{key}" if prefix else key
        if slot is None:
            target = slots.get("name")
            name = target.get("text", "it") if isinstance(target, Mapping) else "it"
            template = _MISSING_SLOT_QUESTIONS.get((intent, key), "What is missing from this sentence?")
            return path, template.format(name=name)
        if isinstance(slot, Mapping) and slot.get("kind") == "statement":
            nested = _first_missing(slot["intent"], slot["slots"], path)
            if nested is not None:
                return nested
    return None


# Plain-English descriptions of slots (for questions and options; never MiniLang)


def _describe(slot: Any) -> str:
    if not isinstance(slot, Mapping):
        return "?"
    kind = slot.get("kind")
    if kind == "string":
        return f'"{slot["text"]}"' if slot.get("quoted") else str(slot["text"])
    if kind in ("number", "name", "word", "pronoun", "count"):
        return str(slot["text"])
    if kind == "binop":
        return f"{_describe(slot['left'])} {_ARITH_WORDS[slot['op']]} {_describe(slot['right'])}"
    if kind == "neg":
        return f"negative {_describe(slot['operand'])}"
    if kind == "condition":
        return f"{_describe(slot['left'])} {_COMPARE_WORDS[slot['op']]} {_describe(slot['right'])}"
    if kind == "statement":
        return _describe_statement(slot["intent"], slot["slots"])
    return "?"


def _describe_statement(intent: str, slots: Mapping[str, Any]) -> str:
    template = _INTENT_TEMPLATES.get(intent)
    if template is None:
        return intent
    text = template.format(**{key: _describe(value) for key, value in slots.items()},
                           **{k: "?" for k in ("name", "value", "amount", "condition", "then", "count", "body")
                              if k not in slots})
    if intent == "if" and "else" in slots:
        text += f" else {_describe(slots['else'])}"
    return text
