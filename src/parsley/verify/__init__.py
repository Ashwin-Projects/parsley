"""[N3] Layered verifier: back-translation, round-trip, execution equivalence.

``Verification`` is the data contract for one accepted statement's checks
(ARCHITECTURE.md 2.6). The pipeline fills it; the layers live in this package:
``backtranslate`` (V1), ``roundtrip`` (V2), ``ast_eval`` + ``interpreter`` (V3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Verification:
    """V1 sentence, then V2/V3 results: True = pass, False = fail, None = skipped."""

    back_translation: str
    v2_match: bool | None
    v3_match: bool | None
    details: tuple[str, ...] = ()
