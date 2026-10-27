"""One-line view of a ``Verification`` for the trace: V1 sentence, V2 and V3 pass/fail."""

from __future__ import annotations

from parsley.verify import Verification


def summarize(verification: Verification) -> str:
    """``V1: <sentence> | V2 pass | V3 fail``; a layer that did not run reads ``skipped``."""
    return (
        f"V1: {verification.back_translation} | V2 {_word(verification.v2_match)} "
        f"| V3 {_word(verification.v3_match)}"
    )


def _word(result: bool | None) -> str:
    if result is None:
        return "skipped"
    return "pass" if result else "fail"
