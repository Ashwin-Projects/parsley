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

Only the semantic analyzer changes the session. Every ``ok`` result carries a
``Verification`` (N3): V1 back-translation, V2 round-trip and V3 execution equivalence.
V2 and V3 call the teammates' modules ``parsley.verify.roundtrip``, ``ast_eval`` and
``interpreter`` through the interface in ARCHITECTURE.md 2.6; a layer whose module is
not implemented yet is reported as skipped, and a verification layer never makes the
pipeline fail or raise.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from parsley.compiler import codegen, semantic
from parsley.compiler.ast_nodes import Program, Stmt
from parsley.compiler.ir_builder import IRBuildError, UnresolvedSlotError, build
from parsley.diagnostics import Diagnostic, has_errors
from parsley.nlp.ambiguity import Clarification, apply_answer, gate, slot_at
from parsley.nlp.candidates import Candidate, Reason, generate
from parsley.nlp.context import Resolution, resolve
from parsley.nlp import suggest
from parsley.nlp.normalizer import normalize
from parsley.session import Session
from parsley.verify import STEP_LIMIT_ERROR, Verification, ast_eval, interpreter, roundtrip
from parsley.verify.backtranslate import backtranslate

logger = logging.getLogger(__name__)

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
    verification: Verification | None = None


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
    clarification: Clarification | None = None  # the open question, for ``answer``
    verification: Verification | None = None  # set only for "ok"
    suggestion: str | None = None  # N4 "Try: ..." phrasing; only for "unsupported"


Confirm = Callable[[str], bool]


def run(
    text: str, session: Session, *, use_context: bool = True, confirm: Confirm | None = None,
) -> PipelineResult:
    """Compile one sentence; ``use_context=False`` skips N1 (the ablation switch).

    ``confirm`` (strict mode, ``--confirm``) gets the back-translation of an error-free
    statement and returns whether the user agrees; the statement is recorded only if so.
    """
    normalized = normalize(text).text if isinstance(text, str) else ""
    nlp = generate(text)
    candidates = tuple(nlp.candidates)
    if nlp.status == "unsupported":
        trace = Trace(str(text), normalized, (), (), "REJECT")
        return PipelineResult(
            "unsupported", trace, diagnostics=(_unsupported(nlp.notes, str(text)),), notes=tuple(nlp.notes),
            suggestion=_suggestion(str(text), nlp.notes),
        )
    resolutions = _resolve(candidates, session, use_context, frozenset())
    base = Trace(text, normalized, candidates, (), "ACCEPT")
    return _decide(base, resolutions, session, use_context, confirm, frozenset())


def answer(
    result: PipelineResult, reply: str, session: Session, *,
    use_context: bool = True, confirm: Confirm | None = None,
) -> PipelineResult:
    """Merge the user's reply to ``result``'s question and re-run the candidate.

    An answer that does not fit the question returns ``result`` unchanged (ask again).
    Raises ValueError if ``result`` has no open question.
    """
    if result.status != "needs_clarification" or result.clarification is None:
        raise ValueError("this result has no open question to answer")
    merged = apply_answer(result.clarification, reply)
    if merged is None:
        return result
    resolutions = _resolve((merged.candidate,), session, use_context, merged.accepted)
    return _decide(result.trace, resolutions, session, use_context, confirm, merged.accepted)


def _resolve(
    candidates: Sequence[Candidate], session: Session, use_context: bool, accepted: frozenset[str],
) -> list[Resolution]:
    if use_context:
        return resolve(candidates, session, accepted=accepted)
    return [Resolution(c, source=c) for c in candidates]


def _decide(
    base: Trace, resolutions: list[Resolution], session: Session, use_context: bool,
    confirm: Confirm | None, accepted: frozenset[str],
) -> PipelineResult:
    """Gate -> IR -> semantic check -> (confirm) -> record -> codegen + back-translation."""
    ranked = tuple(r.candidate for r in resolutions)
    decision = gate(resolutions, accepted)
    if decision.clarification is not None:
        clarification = decision.clarification
        trace = replace(base, ranked=ranked, decision="CLARIFY", chosen=resolutions[0].candidate)
        return PipelineResult(
            "needs_clarification", trace, question=clarification.question,
            options=clarification.options, clarification=clarification,
        )
    best = decision.resolution
    assert best is not None
    diagnostics = list(best.diagnostics)
    try:
        stmt = build(best.candidate)
    except IRBuildError as error:
        diagnostics.append(_ir_error(error, best.candidate, use_context))
        trace = replace(base, ranked=ranked, decision="ACCEPT", chosen=best.candidate)
        return PipelineResult("error", trace, diagnostics=tuple(diagnostics))

    trace = replace(base, ranked=ranked, decision="ACCEPT", chosen=best.candidate, ast=stmt)
    checked = semantic.analyze(stmt, session, record=False)
    if has_errors(checked):
        return PipelineResult("error", trace, diagnostics=tuple(diagnostics + checked))
    back_translation = backtranslate(stmt)
    if confirm is not None and not confirm(back_translation):
        diagnostics.append(Diagnostic(
            "error", "ambiguity", "E103", "the interpretation was not confirmed, so nothing was recorded",
        ))
        return PipelineResult("error", trace, diagnostics=tuple(diagnostics))
    diagnostics.extend(semantic.analyze(stmt, session))
    minilang = codegen.generate(stmt)
    verification = _verify(stmt, minilang, back_translation, session)
    return PipelineResult(
        "ok", replace(trace, verification=verification), minilang, back_translation,
        tuple(diagnostics), verification=verification,
    )


# Verification (N3)


MAX_DETAIL_CHARS = 200  # longer layer results are cut in the details


class _Unavailable(Exception):
    """A verification layer's module does not provide its function yet."""


class _Skipped(Exception):
    """A verification layer ran but cannot give a verdict (e.g. the V3 work budget ran out)."""


def _verify(stmt: Stmt, minilang: str, back_translation: str, session: Session) -> Verification:
    """V2 on this statement; V3 on the whole session program (plan Phase 7)."""
    details = [f"V1: {back_translation}"]
    v2 = _layer("V2", details, lambda: _round_trip(minilang, Program((stmt,))))
    v3 = _layer("V3", details, lambda: _equivalence(Program(tuple(session.history))))
    return Verification(back_translation, v2, v3, tuple(details))


def _layer(name: str, details: list[str], check: Callable[[], tuple[bool, str]]) -> bool | None:
    """Run one layer: True/False with a detail line, or None when it is not available.

    A layer's own failure, even ``SystemExit``, is reported and never raised; only a
    KeyboardInterrupt (the user's Ctrl-C) goes through.
    """
    try:
        passed, detail = check()
    except (_Unavailable, NotImplementedError) as missing:
        what = _text(missing)
        details.append(f"{name} skipped: not available" + (f" ({what})" if what else ""))
        return None
    except _Skipped as skipped:
        details.append(f"{name} skipped: {skipped}")
        return None
    except (Exception, SystemExit) as error:
        details.append(f"{name} failed: {type(error).__name__}: {_text(error)}")
        return False
    details.append(f"{name} {'ok' if passed else 'failed'}: {detail}")
    return passed


def _text(value: object, *, as_repr: bool = False) -> str:
    """``str``/``repr`` of a layer's value, cut to MAX_DETAIL_CHARS; never raises."""
    try:
        text = repr(value) if as_repr else str(value)
    except Exception:
        text = f"<{type(value).__name__} that cannot be shown>"
    return text if len(text) <= MAX_DETAIL_CHARS else text[:MAX_DETAIL_CHARS] + "..."


def _function(module: object, name: str) -> Callable[..., object]:
    function = getattr(module, name, None)
    if not callable(function):
        raise _Unavailable(f"{getattr(module, '__name__', module)}.{name}")
    return function


def _round_trip(source: str, expected: Program) -> tuple[bool, str]:
    difference = _function(roundtrip, "check")(source, expected)
    if difference is None:
        return True, "the re-parsed MiniLang gives the same AST"
    if not isinstance(difference, str):
        return False, f"roundtrip.check returned {_text(difference, as_repr=True)}, expected str or None"
    return False, _text(difference) or "the re-parsed AST differs"


_V3_PARTS = ("variables", "output", "errors")


def _equivalence(program: Program) -> tuple[bool, str]:
    """V3: both evaluators return (variables, output, errors); all three must match."""
    evaluate, interpret = _function(ast_eval, "run"), _function(interpreter, "run")
    results = {"ast_eval.run": evaluate(program), "interpreter.run": interpret(codegen.generate(program))}
    for name, result in results.items():
        if not isinstance(result, (tuple, list)) or len(result) != len(_V3_PARTS):
            return False, f"{name} returned {_text(result, as_repr=True)}, expected (variables, output, errors)"
    from_ast, from_source = results.values()
    if any(_out_of_steps(result[2]) for result in (from_ast, from_source)):
        # A cut-off run says nothing about equivalence, so neither pass nor fail.
        raise _Skipped("execution budget exceeded")
    differing = [part for part, a, b in zip(_V3_PARTS, from_ast, from_source, strict=True) if a != b]
    if not differing:
        return True, "the AST evaluator and the interpreter agree on variables, output and errors"
    return False, (
        f"{' and '.join(differing)} differ: the AST evaluator gave {_text(tuple(from_ast), as_repr=True)} "
        f"but the interpreter gave {_text(tuple(from_source), as_repr=True)}"
    )


def _out_of_steps(errors: object) -> bool:
    try:
        return isinstance(errors, (list, tuple)) and STEP_LIMIT_ERROR in errors
    except Exception:
        return False  # an element whose == raises; the comparison below reports it


# N4 suggestion hook


def _suggestion(text: str, reasons: Sequence[str]) -> str | None:
    """``parsley.nlp.suggest.suggest(text, reason_code)`` (ARCHITECTURE.md 2.10), or None.

    It gets the same primary reason code as the E101 message. ``INTERNAL_ERROR`` is a bug,
    not a phrasing problem, so it gets no suggestion. A missing function, an error inside
    it, or an answer that is not a non-empty string all give None: the suggestion is help,
    never a reason to fail. Errors are logged at debug level only, so the CLI's stderr
    (which has no logging handler) stays clean.
    """
    reason = _primary_reason(reasons)
    if reason == Reason.INTERNAL_ERROR:
        return None
    return _ask_n4("suggest", text, reason)


def _ask_n4(name: str, text: str, *args: str) -> str | None:
    """Call ``suggest.<name>(text, *args)``; any failure or unusable answer gives None."""
    try:
        answer = _function(suggest, name)(text, *args)
    except (Exception, SystemExit) as error:
        if not isinstance(error, (_Unavailable, NotImplementedError)):
            logger.debug("suggest.%s failed for %s: %s", name, _text(text, as_repr=True), _text(error))
        return None
    return answer.strip() if isinstance(answer, str) and answer.strip() else None


def _primary_reason(reasons: Sequence[str]) -> str:
    """The reason code to explain: the first specific one, ``NO_MATCH`` only if alone."""
    specific = [r for r in reasons if r != Reason.NO_MATCH]
    return str(specific[0] if specific else Reason.NO_MATCH)


def _unsupported(reasons: Sequence[str], text: str) -> Diagnostic:
    reason = _primary_reason(reasons)
    message = _UNSUPPORTED_MESSAGES.get(reason, _UNSUPPORTED_MESSAGES[Reason.NO_MATCH])
    codes = ", ".join(reasons) if reasons else Reason.NO_MATCH
    full = f"I could not understand this sentence: {message} ({codes})"
    # N4 guidance on how to split the sentence (LANGUAGE_SPEC.md 8, block_continuation).
    guidance = _ask_n4("split_guidance", text) if reason == Reason.REJECT_AND_CONTINUATION else None
    return Diagnostic("error", "candidates", "E101", f"{full}. {guidance}" if guidance else full)


def _ir_error(error: IRBuildError, candidate: Candidate, use_context: bool) -> Diagnostic:
    if isinstance(error, UnresolvedSlotError):
        slot = slot_at(candidate.slots, error.path)
        text = slot.get("text", "?") if isinstance(slot, Mapping) else "?"
        why = "context resolution is off" if not use_context else "the context resolver left it unresolved"
        return Diagnostic("error", "ir", "E401", f'"{text}" is not a known variable or text, because {why}')
    return Diagnostic("error", "ir", "E401", f"this sentence does not form a valid statement ({error})")

