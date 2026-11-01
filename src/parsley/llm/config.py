"""LLM configuration from environment variables and ``.env``.

Read only when the CLI's mode is ``llm`` or ``hybrid``. Real environment variables win over
``.env``, and neither is copied into ``os.environ``. A configuration problem never stops
the compiler: ``load_provider`` returns a provider that reports it when called, so the
pipeline falls back to the rule result with a warning (W514).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from parsley.llm.prompt import LLMContext
from parsley.llm.provider import (
    ANTHROPIC_BASE_URL,
    DEFAULT_TIMEOUT,
    AnthropicProvider,
    ConfigError,
    FakeProvider,
    OpenAICompatibleProvider,
    Provider,
    RawProposal,
)

__all__ = ["ConfigError", "UnavailableProvider", "load_dotenv", "load_provider", "provider_from_env"]

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_KEY_NAMES = ("PARSLEY_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


class UnavailableProvider:
    """Stands in for a provider that could not be configured; ``propose`` says why."""

    name: ClassVar[str] = "unavailable"

    def __init__(self, error: ConfigError) -> None:
        self._error = error

    def propose(self, sentence: str, context: LLMContext) -> list[RawProposal]:
        raise self._error


def load_dotenv(path: Path) -> dict[str, str]:
    """``KEY=value`` lines of ``path``; {} if it cannot be read. Comments are whole lines."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    values: dict[str, str] = {}
    for line in lines:
        line = line.strip().removeprefix("export ")
        key, separator, value = line.partition("=")
        if not separator or line.startswith("#"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_provider(dotenv: Path = Path(".env")) -> Provider:
    """The configured provider; any problem is reported when it is first called."""
    file_values = load_dotenv(dotenv)
    try:
        provider = provider_from_env({**file_values, **os.environ})
        if "PARSLEY_LLM_BASE_URL" in file_values and "PARSLEY_LLM_BASE_URL" not in os.environ:
            _refuse_redirect(provider)
        return provider
    except ConfigError as error:
        return UnavailableProvider(error)


def _refuse_redirect(provider: Provider) -> None:
    """A ``.env`` (it may come with a cloned repo) cannot send a real environment key elsewhere."""
    key = getattr(provider, "api_key", None)
    if key and key in {os.environ.get(name, "").strip() for name in _KEY_NAMES}:
        raise ConfigError("PARSLEY_LLM_BASE_URL in .env cannot be used with an API key from the environment")


def provider_from_env(environ: Mapping[str, str]) -> Provider:
    """Build the provider named by ``PARSLEY_LLM_PROVIDER``; ConfigError if it cannot be."""
    kind = environ.get("PARSLEY_LLM_PROVIDER", "").strip().lower()
    if kind == "anthropic":
        return _anthropic(environ)
    if kind == "openai":
        return _openai(environ)
    if kind == "fake":
        return _fake(environ)
    if not kind:
        raise ConfigError("set PARSLEY_LLM_PROVIDER to anthropic, openai or fake")
    raise ConfigError(f"unknown PARSLEY_LLM_PROVIDER {kind!r}; use anthropic, openai or fake")


def _anthropic(environ: Mapping[str, str]) -> Provider:
    key = _key(environ, "PARSLEY_LLM_API_KEY", "ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError("set ANTHROPIC_API_KEY or PARSLEY_LLM_API_KEY")
    return AnthropicProvider(
        model=environ.get("PARSLEY_LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL,
        api_key=key,
        base_url=_base_url(environ.get("PARSLEY_LLM_BASE_URL") or ANTHROPIC_BASE_URL, key),
        timeout=_timeout(environ),
    )


def _openai(environ: Mapping[str, str]) -> Provider:
    model = environ.get("PARSLEY_LLM_MODEL")
    if not model:
        raise ConfigError("set PARSLEY_LLM_MODEL to a model of your OpenAI-compatible server")
    key = _key(environ, "PARSLEY_LLM_API_KEY", "OPENAI_API_KEY")
    return OpenAICompatibleProvider(
        model=model,
        base_url=_base_url(environ.get("PARSLEY_LLM_BASE_URL") or DEFAULT_OPENAI_BASE_URL, key),
        api_key=key,
        timeout=_timeout(environ),
    )


def _fake(environ: Mapping[str, str]) -> Provider:
    path = environ.get("PARSLEY_LLM_FIXTURES")
    if not path:
        raise ConfigError("set PARSLEY_LLM_FIXTURES to a file of recorded responses")
    try:
        return FakeProvider(path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ConfigError(f"could not read PARSLEY_LLM_FIXTURES: {type(error).__name__}") from error


def _key(environ: Mapping[str, str], *names: str) -> str | None:
    """The first key set among ``names``, trimmed; never quoted in an error."""
    for name in names:
        key = environ.get(name, "").strip()
        if key:
            if not key.isprintable():
                raise ConfigError(f"{name} contains a control character")
            return key
    return None


def _base_url(url: str, key: str | None) -> str:
    """``url`` without a trailing slash; only http(s), and a key only over https or loopback."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("PARSLEY_LLM_BASE_URL must be an http or https URL")
    if key and parts.scheme == "http" and parts.hostname not in _LOOPBACK:
        raise ConfigError("PARSLEY_LLM_BASE_URL must use https when an API key is set")
    return url.rstrip("/")


def _timeout(environ: Mapping[str, str]) -> float:
    text = environ.get("PARSLEY_LLM_TIMEOUT")
    if not text:
        return DEFAULT_TIMEOUT
    try:
        timeout = float(text)
    except ValueError:
        timeout = 0.0
    if not 0 < timeout < float("inf"):
        raise ConfigError("PARSLEY_LLM_TIMEOUT must be a positive number of seconds")
    return timeout
