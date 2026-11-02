"""LLM providers: send one sentence, return the model's raw text (never parsed here).

``Provider.propose(sentence, context)`` returns ``RawProposal``s holding unparsed model text;
``validate.py`` decides whether any of it is usable. Providers use only ``urllib``. One retry
covers timeouts, connection failures, 429 and 5xx; other statuses fail at once. Redirects are
not followed, so an API key cannot travel to another host. Errors name the status or the
reason and never quote a response body or a key. Requests carry their own ``User-Agent``:
Cloudflare, in front of Groq among others, answers urllib's default with HTTP 403.

``FakeProvider`` replays a fixtures file; every test and CI run uses it, with no network.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from parsley.llm.prompt import SYSTEM_PROMPT, LLMContext, user_message

MAX_ATTEMPTS = 2  # the first call and one retry
RETRY_DELAY = 0.5  # seconds
DEFAULT_TIMEOUT = 20.0  # seconds, per attempt
MAX_RESPONSE_BYTES = 256 * 1024
MAX_OUTPUT_TOKENS = 16000  # room for thinking on models that always think
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2026-10-21"
USER_AGENT = "parsley"

Transport = Callable[[str, Mapping[str, str], bytes, float], tuple[int, bytes]]


class ProviderError(Exception):
    """The provider gave no usable response."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time, after the retry."""


class ProviderRateLimited(ProviderError):
    """The provider answered 429, after the retry; a batch run may wait and try again."""


class ConfigError(ProviderError):
    """The provider is not configured; the message names what to set."""


@dataclass(frozen=True)
class RawProposal:
    """One unparsed model response. Untrusted until ``validate`` has read it."""

    text: str
    provider: str


class Provider(Protocol):
    """A source of raw model text."""

    name: ClassVar[str]

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # urllib would resend the API key to the new host


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, b""


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _post_json(
    url: str, headers: Mapping[str, str], payload: Mapping[str, Any],
    timeout: float, transport: Transport, retry_delay: float,
) -> dict[str, Any]:
    """POST ``payload``; the decoded JSON object, or ProviderError after one retry."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"user-agent": USER_AGENT, **headers}
    failure = ProviderError("the provider was not called")
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(retry_delay)
        try:
            status, reply = transport(url, headers, body, timeout)
        except TimeoutError:
            failure = ProviderTimeout(f"no answer within {timeout:g} seconds")
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                failure = ProviderTimeout(f"no answer within {timeout:g} seconds")
            else:
                failure = ProviderError(f"could not reach the provider: {error.reason}")
        except (OSError, http.client.HTTPException) as error:
            failure = ProviderError(f"could not reach the provider: {type(error).__name__}")
        else:
            if status == 200:
                return _decode(reply)
            kind = ProviderRateLimited if status == 429 else ProviderError
            failure = kind(f"the provider answered HTTP {status}")
            if not _retryable(status):
                raise failure
    raise failure


def _decode(reply: bytes) -> dict[str, Any]:
    if len(reply) > MAX_RESPONSE_BYTES:
        raise ProviderError("the provider's response is too large")
    try:
        decoded = json.loads(reply)
    except ValueError as error:
        raise ProviderError("the provider's response is not JSON") from error
    if not isinstance(decoded, dict):
        raise ProviderError("the provider's response is not a JSON object")
    return decoded


@dataclass(frozen=True)
class AnthropicProvider:
    """The Claude Messages API."""

    name: ClassVar[str] = "anthropic"

    model: str
    api_key: str = field(repr=False)
    base_url: str = ANTHROPIC_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    transport: Transport = _urllib_transport
    retry_delay: float = RETRY_DELAY

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        payload = {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message(sentence, context)}],
        }
        reply = _post_json(
            f"{self.base_url}/v1/messages", headers, payload, self.timeout, self.transport, self.retry_delay,
        )
        if reply.get("stop_reason") == "refusal":
            raise ProviderError("the model declined this request")
        content = reply.get("content")
        if not isinstance(content, list):
            raise ProviderError("the provider's response has no content")
        text = "".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )
        return [RawProposal(text, self.name)]


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    """Any server with a ``/chat/completions`` endpoint: OpenAI, Groq, Ollama and others."""

    name: ClassVar[str] = "openai"

    model: str
    base_url: str
    api_key: str | None = field(default=None, repr=False)
    timeout: float = DEFAULT_TIMEOUT
    transport: Transport = _urllib_transport
    retry_delay: float = RETRY_DELAY

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message(sentence, context)},
            ],
            "response_format": {"type": "json_object"},
        }
        reply = _post_json(
            f"{self.base_url}/chat/completions", headers, payload, self.timeout, self.transport, self.retry_delay,
        )
        try:
            text = reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("the provider's response has no message") from error
        if not isinstance(text, str):
            raise ProviderError("the provider's response has no message")
        return [RawProposal(text, self.name)]


def context_json(context: LLMContext) -> dict[str, list[Any]]:
    """``context`` as plain JSON data, for fixtures and the response cache."""
    return {"symbols": [list(symbol) for symbol in context.symbols], "reference_stack": list(context.ref_stack)}


class FakeProvider:
    """Replays recorded responses from a JSON file, keyed by the exact sentence.

    Each entry has ``sentence`` and one of ``readings`` (serialized as the model's JSON),
    ``raw`` (the model's text, unchanged) or ``error`` (``timeout`` or any other word, which
    fails like a provider error). An optional ``context`` (``symbols`` and ``reference_stack``,
    as ``context_json`` writes them) limits an entry to that session state; it wins over an
    entry without one. The file's ``model`` names the model that produced it. Never used
    unless configured.
    """

    name: ClassVar[str] = "fake"

    def __init__(self, path: Path | str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.model: str = data.get("model", self.name)
        self._responses: dict[tuple[str, str], dict[str, Any]] = {
            (entry["sentence"], json.dumps(entry.get("context"), sort_keys=True)): entry
            for entry in data["responses"]
        }
        self.calls: list[str] = []

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        self.calls.append(sentence)
        exact = (sentence, json.dumps(context_json(context), sort_keys=True))
        entry = self._responses.get(exact) or self._responses.get((sentence, "null"))
        if entry is None:
            raise ProviderError("no recorded response for this sentence")
        if "error" in entry:
            kind = ProviderTimeout if entry["error"] == "timeout" else ProviderError
            raise kind(f"recorded {entry['error']}")
        text = entry["raw"] if "raw" in entry else json.dumps({"readings": entry["readings"]})
        return [RawProposal(text, self.name)]
