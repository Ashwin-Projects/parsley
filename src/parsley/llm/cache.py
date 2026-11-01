"""Batch runs against a real model: a response cache, pacing and rate-limit backoff.

``MeteredProvider`` wraps any provider for the evaluation. Responses are stored on disk under
a key of (model, prompt hash, input), where the input is the exact user message, plus the
endpoint, so a re-run is free and reproducible, and neither a prompt change nor another server
with the same model name can reuse an old answer. A cached response keeps the latency of the
call that produced it, so a re-run reports the same numbers. Failures are not saved, but an
input that failed stays failed for the rest of the run, so conditions compare the same answers.
Only model text is stored; nothing here sees a key.

``write_fixture`` saves the responses of this run in the format ``FakeProvider`` replays.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from parsley.llm.prompt import PROMPT_SHA256, LLMContext, user_message
from parsley.llm.provider import Provider, ProviderError, ProviderRateLimited, RawProposal, context_json

DEFAULT_BACKOFFS: tuple[float, ...] = (5, 10, 20, 40, 60)  # seconds, after each 429


def cache_key(model: str, sentence: str, context: LLMContext, endpoint: str = "") -> str:
    """The cache key of one request: (model, prompt hash, input), on one endpoint."""
    fields = json.dumps([model, PROMPT_SHA256, user_message(sentence, context), endpoint], ensure_ascii=False)
    return hashlib.sha256(fields.encode("utf-8")).hexdigest()


class MeteredProvider:
    """A provider with a disk cache, paced calls, 429 backoff and call statistics."""

    def __init__(
        self, inner: Provider, model: str, directory: Path, *, delay: float = 0.0,
        backoffs: Sequence[float] = DEFAULT_BACKOFFS,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._directory = Path(directory)
        self._delay = delay
        self._backoffs = tuple(backoffs)
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self._entries: dict[str, dict[str, Any]] = {}
        self._failed: dict[str, ProviderError] = {}
        self.endpoint = f"{inner.name} {getattr(inner, 'base_url', '')}".strip()
        self.model = model
        self.network_calls = 0
        self.cache_hits = 0
        self.failures = 0
        self.rate_limited = 0
        self.last_latency: float | None = None

    @property
    def name(self) -> str:
        return self._inner.name

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        self.last_latency = None
        key = cache_key(self.model, sentence, context, self.endpoint)
        if key in self._failed:
            raise self._failed[key]
        entry = self._read(key)
        if entry is None:
            try:
                entry = self._call(key, sentence, context)
            except ProviderError as error:
                self._failed[key] = error
                raise
        else:
            self.cache_hits += 1
        self._entries[key] = entry
        self.last_latency = entry["latency"]
        return [RawProposal(text, self.name) for text in entry["texts"]]

    def write_fixture(self, path: Path) -> None:
        """Save this run's responses as a ``FakeProvider`` fixtures file."""
        responses = [
            {"sentence": entry["sentence"], "context": entry["context"], "raw": entry["texts"][0]}
            for _, entry in sorted(self._entries.items())
        ]
        data = {
            "version": 1, "model": self.model, "prompt_sha256": PROMPT_SHA256,
            "note": f"Responses of {self.model}, recorded by run_eval --record.", "responses": responses,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}.json"

    def _read(self, key: str) -> dict[str, Any] | None:
        try:
            entry = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # not cached yet, or a damaged file: ask again
        if not isinstance(entry, dict) or not {"texts", "latency", "sentence", "context"} <= entry.keys():
            return None
        texts = entry["texts"]
        return entry if isinstance(texts, list) and texts and all(isinstance(t, str) for t in texts) else None

    def _call(self, key: str, sentence: str, context: LLMContext) -> dict[str, Any]:
        self._pace()
        started = self._clock()
        raws = self._with_backoff(sentence, context)
        latency = self._clock() - started
        entry = {
            "model": self.model, "prompt_sha256": PROMPT_SHA256, "sentence": sentence,
            "context": context_json(context), "texts": [raw.text for raw in raws], "latency": latency,
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._path(key).with_suffix(".tmp")
        temporary.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8", newline="\n")
        temporary.replace(self._path(key))
        return entry

    def _pace(self) -> None:
        if self._last_call is not None:
            wait = self._delay - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _with_backoff(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        waits = list(self._backoffs)
        while True:
            self.network_calls += 1
            try:
                return self._inner.propose(sentence, context)
            except ProviderRateLimited:
                self.rate_limited += 1
                if not waits:
                    self.failures += 1
                    raise
                self._sleep(waits.pop(0))
            except ProviderError:
                self.failures += 1
                raise
