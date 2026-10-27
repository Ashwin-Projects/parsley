"""Load the held-out evaluation data and the development fixtures (Phase 8, N5).

Read-only: nothing here writes to a data directory, and a file with a ``.sha256`` freeze
must match it byte for byte (``DatasetError`` otherwise). There is no tuning hook: the
loader only turns each file into ``Item``s that ``run_eval`` feeds to the real pipeline.

Held-out files (``tests/eval_data/*.json``), chosen by their ``category``:

* ``held_out_paraphrases``: ``groups`` of ``paraphrases`` with ``setup`` English, its
  ``setup_minilang`` and one ``expected_minilang`` (``tests/eval_data/README.md``).
* ``held_out_ambiguous`` / ``held_out_unsupported``: ``cases``, each with ``setup``,
  ``setup_minilang`` and ``input``; expected ``needs_clarification`` / ``unsupported``.
* ``held_out_sessions``: ``sessions`` of ``sentences`` whose ``expected_minilang`` has one
  line per sentence. Sentence *k* becomes one item, run after sentences 1..k-1.
* ``human_blind`` (optional ``human_blind.json``): ``cases`` written by a person who has not
  seen the code; each has ``setup``, ``setup_minilang``, ``input``, ``expected_status``
  (``ok``, ``needs_clarification``, ``unsupported`` or ``error``) and ``expected_minilang``
  (required for ``ok``). Reported in its own section (TESTING.md).
* ``synthetic_blind`` (optional ``synthetic_blind.json``): the same schema, for a set that
  was not written by a person; reported in its own section with its ``provenance``.
* ``valid`` / ``invalid`` / ``ambiguous`` / ``semantic``: the development-fixture format
  (TESTING.md), with ``given`` symbols as setup.

An unknown ``category`` is an error, never silently skipped.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_CATEGORIES = ("valid", "invalid", "ambiguous", "semantic")


class DatasetError(ValueError):
    """A data file is missing a field, has an unknown category, or broke its freeze."""


@dataclass(frozen=True)
class Item:
    """One sentence to evaluate, in a fresh session after its ``setup`` sentences."""

    id: str
    source: str  # "held_out" or "development"
    subset: str  # "paraphrase", "valid", "invalid", "ambiguous", "semantic", "session"
    group: str | None  # paraphrase group id, or session id
    input: str
    setup: tuple[str, ...]
    setup_minilang: tuple[str, ...]  # gold output of each setup sentence
    expected_status: str  # "ok", "ambiguous", "unsupported" or "error"
    expected_minilang: str | None
    expected_suggestion: str | None
    expected_codes: tuple[str, ...]
    context: str | None  # e.g. "pronoun", from session data

    @property
    def context_dependent(self) -> bool:
        """Needs the session (names, pronouns, implicit declaration) to be read correctly."""
        return bool(self.setup) or self.context is not None


def load_held_out(directory: Path) -> list[Item]:
    """Every ``*.json`` in ``directory`` (sorted by name), as held-out items."""
    return [item for path in sorted(Path(directory).glob("*.json")) for item in _load(path, "held_out")]


def load_development(directory: Path) -> list[Item]:
    """The development fixtures; the system was built against these, so they are not evidence."""
    paths = [Path(directory) / f"{name}.json" for name in FIXTURE_CATEGORIES]
    return [item for path in paths if path.exists() for item in _load(path, "development")]


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path, source: str) -> list[Item]:
    raw = path.read_bytes()
    frozen = path.with_suffix(".sha256")
    if frozen.exists():
        expected = frozen.read_text(encoding="utf-8").split()[0]
        if hashlib.sha256(raw).hexdigest() != expected:
            raise DatasetError(f"{path.name}: digest does not match {frozen.name}; the data changed")
    try:
        data = json.loads(raw.decode("utf-8"))
        category = data["category"]
        if category == "held_out_paraphrases":
            return list(_paraphrases(data, source))
        if category in FIXTURE_CATEGORIES:
            return [_fixture(category, f, source) for f in data["fixtures"]]
        if category == "held_out_ambiguous":
            return [_case("ambiguous", "ambiguous", c, source) for c in data["cases"]]
        if category == "held_out_unsupported":
            return [_case("unsupported", "unsupported", c, source) for c in data["cases"]]
        if category == "held_out_sessions":
            return list(_sessions(data, source))
        if category in ("human_blind", "synthetic_blind"):
            return [_blind(category, path.name, c, source) for c in data["cases"]]
    except (KeyError, TypeError, ValueError) as error:
        raise DatasetError(f"{path.name}: malformed data ({error!r})") from error
    raise DatasetError(f"{path.name}: unknown category {category!r}")


def _paraphrases(data: Mapping[str, Any], source: str) -> Iterator[Item]:
    for group in data["groups"]:
        setup_minilang = _lines(group["setup_minilang"])
        for member in group["paraphrases"]:
            yield Item(
                id=member["id"], source=source, subset="paraphrase", group=group["id"],
                input=member["input"], setup=tuple(group["setup"]), setup_minilang=setup_minilang,
                expected_status="ok", expected_minilang=group["expected_minilang"],
                expected_suggestion=None, expected_codes=(), context=None,
            )


def _fixture(category: str, fixture: Mapping[str, Any], source: str) -> Item:
    setup, setup_minilang = _given(fixture["given"])
    codes = tuple(fixture.get("expected_diagnostic_codes", ()))
    status = {
        "valid": "ok", "invalid": "unsupported", "ambiguous": "ambiguous",
        # A semantic fixture expects an error when any code is an error; warnings still give code.
        "semantic": "error" if any(code.startswith("E") for code in codes) else "ok",
    }[category]
    return Item(
        id=fixture["id"], source=source, subset=category, group=None, input=fixture["input"],
        setup=setup, setup_minilang=setup_minilang, expected_status=status,
        expected_minilang=fixture.get("expected_minilang"),
        expected_suggestion=fixture.get("expected_suggestion"), expected_codes=codes,
        context=fixture.get("context"),
    )


def _given(given: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Declarations that recreate ``given`` symbols, in their insertion order."""
    setup, minilang = [], []
    for name, kind in given["symbols"].items():
        if kind not in ("number", "string"):
            raise ValueError(f"unknown symbol type {kind!r}")
        value = "0" if kind == "number" else '"text"'
        setup.append(f"let {name} be {value}")
        minilang.append(f"LET {name} = {value};")
    return tuple(setup), tuple(minilang)


def _lines(minilang: str) -> tuple[str, ...]:
    return tuple(line for line in minilang.splitlines() if line.strip())


def _case(subset: str, status: str, case: Mapping[str, Any], source: str) -> Item:
    return Item(
        id=case["id"], source=source, subset=subset, group=None, input=case["input"],
        setup=tuple(case["setup"]), setup_minilang=_lines(case["setup_minilang"]),
        expected_status=status, expected_minilang=case.get("expected_minilang"),
        expected_suggestion=case.get("expected_suggestion"), expected_codes=(), context=None,
    )


_BLIND_STATUSES = {"ok": "ok", "needs_clarification": "ambiguous", "unsupported": "unsupported", "error": "error"}


def _blind(subset: str, file: str, case: Mapping[str, Any], source: str) -> Item:
    status = _BLIND_STATUSES.get(case["expected_status"])
    if status is None:
        raise DatasetError(f"{file}: case {case['id']}: unknown expected_status {case['expected_status']!r}")
    if status == "ok" and not case.get("expected_minilang"):
        raise DatasetError(f"{file}: case {case['id']}: expected_status ok needs expected_minilang")
    return _case(subset, status, case, source)


def _sessions(data: Mapping[str, Any], source: str) -> Iterator[Item]:
    for session in data["sessions"]:
        sentences: Sequence[str] = session["sentences"]
        setup, gold = tuple(session["setup"]), _lines(session["expected_minilang"])
        if len(gold) != len(sentences):
            raise ValueError(f"session {session['id']}: {len(sentences)} sentences but {len(gold)} gold lines")
        coverage = ",".join(session["coverage"]) or "session"
        for index, sentence in enumerate(sentences):
            yield Item(
                id=f"{session['id']}-{index + 1}", source=source, subset="session",
                group=session["id"], input=sentence, setup=setup + tuple(sentences[:index]),
                setup_minilang=_lines(session["setup_minilang"]) + gold[:index],
                expected_status=session["expected_status"], expected_minilang=gold[index],
                expected_suggestion=None, expected_codes=(), context=coverage,
            )
