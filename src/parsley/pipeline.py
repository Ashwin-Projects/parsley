"""End-to-end pipeline wiring stages [A]-[H] together (Phase 5).

``run(text, session)`` compiles one English sentence in the context of a session:
normalize -> candidates -> context (N1) -> top candidate -> IR -> semantic -> codegen ->
back-translation (V1). It never guesses and never raises for bad input:

- ``ok``: MiniLang and back-translation are set; the session recorded the statement.
- ``needs_clarification``: a required slot is missing, a word may be a typo of a declared
  name, or a pronoun has nothing to refer to; ``question`` says what to ask.
- ``unsupported``: no supported pattern matches (decision REJECT); ``notes`` holds the
  NLPResult reason codes (ARCHITECTURE.md 2.4) and ``diagnostics`` an E101.
- ``error``: an unresolved slot or a semantic error; see ``diagnostics``.

Only the semantic analyzer changes the session. The score-margin ambiguity gate (N2) is the
next step; until then the top-ranked candidate is taken.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from parsley.compiler import codegen, semantic
from parsley.compiler.ast_nodes import Stmt
from parsley.compiler.ir_builder import IRBuildError, UnresolvedSlotError, build
from parsley.diagnostics import Diagnostic, has_errors
from parsley.nlp.ambiguity import missing_slot_question
from parsley.nlp.candidates import Candidate, Reason, generate
from parsley.nlp.context import Resolution, resolve
from parsley.nlp.normalizer import normalize
from parsley.session import Session
from parsley.verify.backtranslate import backtranslate

Status = Literal["ok", "error", "needs_clarification", "unsupported"]
Decision = Literal["ACCEPT", "CLARIFY", "REJECT"]

# Plain-English reasons for E101, keyed by NLPResult reason code (ARCHITECTURE.md 2.4).
_UNSUPPORTED_MESSAGES: dict[str, str] = {
    Reason.NOT_TEXT: "the input is not text",
    Reason.INPUT_TOO_LONG: "the sentence is longer than 500 characters",
    Reason.UNTERMINATED_QUOTE: "a quote is opened but never closed",
    Reason.EMPTY_INPUT: "there is nothing to compile",
    Reason.REJECT_AND_CONTINUATION: "one sentence can hold only one statement; split it at 'and'",
    Reason.TOO_MANY_ALTERNATIVES: "the sentence offers more than 4 alternatives",
    Reason.TOO_MANY_READINGS: "the sentence can be read in too many ways",
    Reason.NO_MATCH: "this sentence does not match any supported pattern",
    Reason.INTERNAL_ERROR: "an internal error stopped the sentence from being read",
}


@dataclass(frozen=True)
class Trace:
    """What each stage saw and decided, for ``--trace`` and evaluation."""

    input: str
    normalized: str
    candidates: tuple[Candidate, ...]  # as generated, best first
    ranked: tuple[Candidate, ...]  # after context resolution and re-scoring, best first
    decision: Decision
    chosen: Candidate | None = None
    ast: Stmt | None = None


@dataclass(frozen=True)
class PipelineResult:
    """The outcome of compiling one sentence."""

    status: Status
    trace: Trace
    minilang: str | None = None
    back_translation: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    question: str | None = None
    options: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()  # reason codes, only for "unsupported"


def run(text: str, session: Session, *, use_context: bool = True) -> PipelineResult:
    """Compile one sentence; ``use_context=False`` skips N1 (the ablation switch)."""
    normalized = normalize(text).text if isinstance(text, str) else ""
    nlp = generate(text)
    candidates = tuple(nlp.candidates)
    if nlp.status == "unsupported":
        trace = Trace(str(text), normalized, (), (), "REJECT")
        return PipelineResult(
            "unsupported", trace, diagnostics=(_unsupported(nlp.notes),), notes=tuple(nlp.notes),
        )

    resolutions = resolve(candidates, session) if use_context else [Resolution(c) for c in candidates]
    best = resolutions[0]
    ranked = tuple(r.candidate for r in resolutions)

    # Which variable is meant (typo, empty pronoun stack) comes before what is missing.
    question, options = best.question, best.options
    if question is None:
        question, options = missing_slot_question(best.candidate), ()
    if question is not None:
        trace = Trace(text, normalized, candidates, ranked, "CLARIFY", best.candidate)
        return PipelineResult("needs_clarification", trace, question=question, options=options)

    diagnostics = list(best.diagnostics)
    try:
        stmt = build(best.candidate)
    except IRBuildError as error:
        diagnostics.append(_ir_error(error, best.candidate, use_context))
        trace = Trace(text, normalized, candidates, ranked, "ACCEPT", best.candidate)
        return PipelineResult("error", trace, diagnostics=tuple(diagnostics))

    trace = Trace(text, normalized, candidates, ranked, "ACCEPT", best.candidate, stmt)
    diagnostics.extend(semantic.analyze(stmt, session))
    if has_errors(diagnostics):
        return PipelineResult("error", trace, diagnostics=tuple(diagnostics))
    return PipelineResult("ok", trace, codegen.generate(stmt), backtranslate(stmt), tuple(diagnostics))


def _unsupported(reasons: Sequence[str]) -> Diagnostic:
    reason = reasons[0] if reasons else Reason.NO_MATCH
    message = _UNSUPPORTED_MESSAGES.get(reason, _UNSUPPORTED_MESSAGES[Reason.NO_MATCH])
    return Diagnostic("error", "candidates", "E101", f"I could not understand this sentence: {message}")


def _ir_error(error: IRBuildError, candidate: Candidate, use_context: bool) -> Diagnostic:
    if isinstance(error, UnresolvedSlotError):
        slot = _slot_at(candidate.slots, error.path)
        text = slot.get("text", "?") if isinstance(slot, Mapping) else "?"
        why = "context resolution is off" if not use_context else "the context resolver left it unresolved"
        return Diagnostic("error", "ir", "E401", f'"{text}" is not a known variable or text, because {why}')
    return Diagnostic("error", "ir", "E401", f"this sentence does not form a valid statement ({error})")


def _slot_at(slots: Mapping[str, Any], path: str) -> Any:
    """The slot at a dotted IR path (``value.left``, ``then.value``), or None."""
    current: Any = {"slots": slots, "kind": "statement"}
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        container = current["slots"] if current.get("kind") == "statement" else current
        current = container.get(key) if isinstance(container, Mapping) else None
    return current
