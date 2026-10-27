"""[N3] Layered verifier: back-translation, round-trip, execution equivalence.

``Verification`` is the data contract for one accepted statement's checks
(ARCHITECTURE.md 2.6). The pipeline fills it; the layers live in this package:
``backtranslate`` (V1), ``roundtrip`` (V2), ``ast_eval`` + ``interpreter`` (V3).
"""

from __future__ import annotations

from dataclasses import dataclass

# V3 work budget, shared by both evaluators (ARCHITECTURE.md 2.6). Only these two values
# are shared; ast_eval.py and interpreter.py still share no evaluation code.
STEP_LIMIT = 100_000
STEP_LIMIT_ERROR = "execution step limit exceeded"


@dataclass(frozen=True)
class Verification:
    """V1 sentence, then V2/V3 results: True = pass, False = fail, None = skipped."""

    back_translation: str
    v2_match: bool | None
    v3_match: bool | None
    details: tuple[str, ...] = ()
