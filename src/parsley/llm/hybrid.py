"""When to ask the LLM, and how its readings become ordinary candidates.

The LLM only proposes. ``consult`` turns validated readings into ``Candidate``s with
``rule_id="LLM"`` and scores below every rule match; the pipeline then sends them through
the context resolver, the gate, the IR builder, the semantic analyzer and the verifier like
any rule candidate. It never raises for a provider problem: the pipeline falls back to the
rule result, and the warning says why (LANGUAGE_SPEC.md 7.5).

The numbers are derived, not tuned, and were set without looking at any evaluation data:

- A rule score is ``0.5 + 0.5 * share of command words``, so every rule match is above 0.5.
  LLM scores map confidence onto ``[LLM_SCORE_MIN, LLM_SCORE_MAX]``, which ends at 0.5.
- The range is narrow on purpose: two readings stay within ``CLARIFY_MARGIN`` until their
  confidences differ by a third, so uncalibrated model confidence leads to a question.
- ``CONSULT_THRESHOLD`` is ``LLM_SCORE_MAX + CLARIFY_MARGIN``: at or above it no LLM reading
  could come within the margin of the rule reading, so a call could change nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from parsley.diagnostics import Diagnostic
from parsley.llm.config import ConfigError
from parsley.llm.prompt import LLMContext
from parsley.llm.provider import Provider, ProviderTimeout
from parsley.llm.validate import Discard, Reading, validate
from parsley.nlp.ambiguity import CLARIFY_MARGIN
from parsley.nlp.candidates import LLM_RULE_ID, Candidate, Reason
from parsley.session import Session

logger = logging.getLogger(__name__)

LLM_SCORE_MIN = 0.35
LLM_SCORE_MAX = 0.50
CONSULT_THRESHOLD = round(LLM_SCORE_MAX + CLARIFY_MARGIN, 4)
MAX_ERROR_CHARS = 200
STAGE = "llm"
_FALLBACK = "so this uses the rule result"


@dataclass(frozen=True)
class Consultation:
    """One call to the LLM: what it proposed, what was dropped, and any fallback warning."""

    trigger: str  # why the LLM was asked
    provider: str = ""
    candidates: tuple[Candidate, ...] = ()  # best first
    discarded: tuple[Discard, ...] = ()
    warnings: tuple[Diagnostic, ...] = ()


def score_of(confidence: float) -> float:
    """Map a model confidence in [0, 1] onto the LLM score range."""
    return round(LLM_SCORE_MIN + (LLM_SCORE_MAX - LLM_SCORE_MIN) * confidence, 4)


def trigger(mode: str, reasons: Sequence[str], top_score: float | None) -> str | None:
    """Why this sentence goes to the LLM, or None if it does not.

    A rejection with a reason of its own (malformed input, ``and`` continuation, too many
    readings) stands in every mode: the LLM must not turn it into a statement.
    """
    if reasons and list(reasons) != [Reason.NO_MATCH]:
        return None
    if mode == "llm":
        return "mode llm"
    if top_score is None:
        return "no rule matched"
    if top_score < CONSULT_THRESHOLD:
        return f"top rule score {top_score:.4g} is below {CONSULT_THRESHOLD:g}"
    return None


def consult(sentence: str, session: Session, provider: Provider | None, why: str) -> Consultation:
    """Ask ``provider`` and validate the answer; failures become warnings, never exceptions."""
    if provider is None:
        return Consultation(why, warnings=(_unconfigured("no provider was given"),))
    readings: list[Reading] = []
    discarded: list[Discard] = []
    try:
        for raw in provider.propose(sentence, _context(session)):
            result = validate(raw.text, sentence)
            readings.extend(result.readings)
            discarded.extend(result.discarded)
    except ConfigError as error:
        return Consultation(why, provider.name, warnings=(_unconfigured(_cut(error)),))
    except ProviderTimeout as error:
        return Consultation(why, provider.name, warnings=(_warning(
            "W511", f"the LLM did not answer in time ({_cut(error)}), {_FALLBACK}"),))
    except (Exception, SystemExit) as error:
        logger.debug("LLM call failed: %s: %s", type(error).__name__, _cut(error))
        return Consultation(why, provider.name, warnings=(_warning(
            "W510", f"the LLM call failed ({type(error).__name__}: {_cut(error)}), {_FALLBACK}"),))
    readings.sort(key=lambda reading: reading.confidence, reverse=True)
    candidates = tuple(_candidate(reading) for reading in readings)
    warnings = ()
    if discarded and not candidates:
        reasons = ", ".join(sorted({str(d.reason) for d in discarded}))
        warnings = (_warning("W512", f"no LLM reading was usable ({reasons}), {_FALLBACK}"),)
    return Consultation(why, provider.name, candidates, tuple(discarded), warnings)


def accepted_warning() -> Diagnostic:
    """W513: the accepted reading came from the model, so a person should read V1."""
    return _warning("W513", "this reading came from the LLM, not a rule; check the back-translation")


def _context(session: Session) -> LLMContext:
    symbols = sorted(session.symbols.values(), key=lambda symbol: symbol.declared_at)
    return LLMContext(tuple((s.name, s.type) for s in symbols), tuple(session.ref_stack))


def _candidate(reading: Reading) -> Candidate:
    # "declare" is exempt from the typo check (D-12) and may replace a variable (W208). That
    # is for a user who said so, not a model's guess, so N1 decides: new name or near miss.
    intent = "assign" if reading.intent == "declare" else reading.intent
    return Candidate(
        intent, reading.slots, score_of(reading.confidence), LLM_RULE_ID,
        [f"LLM reading, confidence {reading.confidence:g}"],
    )


def _warning(code: str, message: str) -> Diagnostic:
    return Diagnostic("warning", STAGE, code, message)


def _unconfigured(reason: str) -> Diagnostic:
    return _warning("W514", f"the LLM is not configured ({reason}), {_FALLBACK}")


def _cut(error: BaseException) -> str:
    return str(error)[:MAX_ERROR_CHARS]
