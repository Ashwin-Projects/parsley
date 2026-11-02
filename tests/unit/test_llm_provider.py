"""LLM providers: request shape, one retry, timeouts, FakeProvider. No network in any test."""

import json
import socket
import threading
import urllib.error
from pathlib import Path

import pytest

from parsley.llm import provider as llm
from parsley.llm.prompt import LLMContext, SYSTEM_PROMPT
from parsley.llm.provider import (
    AnthropicProvider,
    DeadlineProvider,
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    RawProposal,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures_llm" / "recorded.json"
CONTEXT = LLMContext(symbols=(("score", "number"),), ref_stack=("score",))
ANTHROPIC_OK = json.dumps({"stop_reason": "end_turn", "content": [
    {"type": "thinking", "thinking": ""}, {"type": "text", "text": '{"readings": []}'},
]}).encode()
OPENAI_OK = json.dumps({"choices": [{"message": {"content": '{"readings": []}'}}]}).encode()


class Wire:
    """A scripted transport; each step is a (status, body) reply or an exception to raise."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body), timeout))
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a real socket")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def anthropic(wire, **kwargs):
    return AnthropicProvider(model="m", api_key="secret-key", transport=wire, retry_delay=0, **kwargs)


def openai(wire, **kwargs):
    return OpenAICompatibleProvider(
        model="m", base_url="http://localhost:11434/v1", api_key="secret-key",
        transport=wire, retry_delay=0, **kwargs,
    )


def test_anthropic_request_and_text_extraction():
    wire = Wire((200, ANTHROPIC_OK))
    assert anthropic(wire).propose("print x", CONTEXT) == [RawProposal('{"readings": []}', "anthropic")]
    url, headers, body, _ = wire.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "secret-key"
    assert headers["anthropic-version"] == "2026-10-21"
    assert body["model"] == "m"
    assert body["system"] == SYSTEM_PROMPT
    assert "print x" in body["messages"][0]["content"]
    assert not {"temperature", "top_p", "top_k"} & set(body)


def test_anthropic_refusal_is_a_failure_not_empty_text():
    wire = Wire((200, json.dumps({"stop_reason": "refusal", "content": []}).encode()))
    with pytest.raises(ProviderError, match="declined"):
        anthropic(wire).propose("print x", CONTEXT)


def test_openai_compatible_uses_the_configured_base_url():
    wire = Wire((200, OPENAI_OK))
    assert openai(wire).propose("print x", CONTEXT) == [RawProposal('{"readings": []}', "openai")]
    url, headers, body, _ = wire.calls[0]
    assert url == "http://localhost:11434/v1/chat/completions"
    assert headers["authorization"] == "Bearer secret-key"
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert body["response_format"] == {"type": "json_object"}


def test_openai_compatible_sends_no_key_when_there_is_none():
    wire = Wire((200, OPENAI_OK))
    OpenAICompatibleProvider(model="m", base_url="http://localhost:1/v1", transport=wire).propose("x", CONTEXT)
    assert "authorization" not in wire.calls[0][1]


@pytest.mark.parametrize("build, reply", [(anthropic, ANTHROPIC_OK), (openai, OPENAI_OK)])
def test_requests_name_parsley_so_a_firewall_does_not_block_urllibs_default_agent(build, reply):
    wire = Wire((200, reply))
    build(wire).propose("print x", CONTEXT)
    assert wire.calls[0][1]["user-agent"] == llm.USER_AGENT
    assert "urllib" not in llm.USER_AGENT.lower()


def test_one_retry_after_a_timeout_then_success():
    wire = Wire(TimeoutError(), (200, ANTHROPIC_OK))
    assert len(anthropic(wire).propose("print x", CONTEXT)) == 1
    assert len(wire.calls) == 2


def test_two_timeouts_raise_provider_timeout():
    wire = Wire(TimeoutError(), socket.timeout())
    with pytest.raises(ProviderTimeout):
        anthropic(wire).propose("print x", CONTEXT)
    assert len(wire.calls) == 2


def test_url_error_wrapping_a_timeout_counts_as_a_timeout():
    wire = Wire(urllib.error.URLError(TimeoutError()), urllib.error.URLError(TimeoutError()))
    with pytest.raises(ProviderTimeout):
        openai(wire).propose("print x", CONTEXT)


def test_retries_a_server_error_once():
    wire = Wire((503, b""), (200, OPENAI_OK))
    assert len(openai(wire).propose("print x", CONTEXT)) == 1
    assert len(wire.calls) == 2


def test_a_rate_limit_after_the_retry_is_its_own_error():
    wire = Wire((429, b""), (429, b""))
    with pytest.raises(ProviderRateLimited):
        openai(wire).propose("print x", CONTEXT)
    assert len(wire.calls) == 2


def test_does_not_retry_a_client_error():
    wire = Wire((401, b"bad key"))
    with pytest.raises(ProviderError, match="401"):
        openai(wire).propose("print x", CONTEXT)
    assert len(wire.calls) == 1


def test_connection_failure_after_the_retry_is_a_provider_error():
    wire = Wire(urllib.error.URLError("refused"), urllib.error.URLError("refused"))
    with pytest.raises(ProviderError) as caught:
        openai(wire).propose("print x", CONTEXT)
    assert not isinstance(caught.value, ProviderTimeout)


@pytest.mark.parametrize("body", [b"<html>", b"[]", b'{"choices": []}', b'{"choices": [{"message": {}}]}'])
def test_unusable_openai_envelope_is_a_provider_error(body):
    with pytest.raises(ProviderError):
        openai(Wire((200, body))).propose("print x", CONTEXT)


def test_errors_never_contain_the_api_key():
    wire = Wire((403, b"secret-key rejected"))
    with pytest.raises(ProviderError) as caught:
        openai(wire).propose("print x", CONTEXT)
    assert "secret-key" not in str(caught.value)
    assert "secret-key" not in repr(anthropic(Wire()))


def test_a_connection_error_names_no_address_or_system_detail():
    refused = urllib.error.URLError(OSError("[WinError 10061] refused by 10.0.0.5:8443"))
    with pytest.raises(ProviderError) as caught:
        openai(Wire(refused, refused)).propose("print x", CONTEXT)
    assert "10.0.0.5" not in str(caught.value) and "WinError" not in str(caught.value)


def test_oversized_response_is_refused():
    wire = Wire((200, b"x" * (llm.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(ProviderError, match="too large"):
        openai(wire).propose("print x", CONTEXT)


def test_the_timeout_reaches_the_transport():
    wire = Wire((200, OPENAI_OK))
    openai(wire, timeout=3.5).propose("print x", CONTEXT)
    assert wire.calls[0][3] == 3.5


def test_redirects_are_not_followed():
    handlers = [type(h).__name__ for h in llm._OPENER.handlers]
    assert "_NoRedirect" in handlers
    assert "HTTPRedirectHandler" not in handlers


# FakeProvider


def test_a_deadline_stops_a_call_however_slowly_the_server_answers():
    release = threading.Event()

    def dripping(url, headers, body, timeout):
        release.wait(5)  # stands in for bytes that each arrive inside the socket timeout
        return 200, OPENAI_OK

    provider = DeadlineProvider(openai(dripping), 0.05)
    try:
        with pytest.raises(ProviderTimeout, match="0.05 seconds"):
            provider.propose("print x", CONTEXT)
    finally:
        release.set()


def test_a_deadline_covers_the_retry_too():
    release = threading.Event()
    attempts = []

    def failing_then_slow(url, headers, body, timeout):
        attempts.append(timeout)
        if len(attempts) > 1:
            release.wait(5)
        raise TimeoutError

    provider = DeadlineProvider(openai(failing_then_slow), 0.05)
    try:
        with pytest.raises(ProviderTimeout):
            provider.propose("print x", CONTEXT)
    finally:
        release.set()
    assert len(attempts) == 2


def test_a_deadline_passes_an_answer_through():
    provider = DeadlineProvider(openai(Wire((200, OPENAI_OK))), 5)
    assert provider.propose("print x", CONTEXT) == [RawProposal('{"readings": []}', "openai")]


def test_a_deadline_passes_a_failure_through():
    provider = DeadlineProvider(openai(Wire((401, b""))), 5)
    with pytest.raises(ProviderError, match="401"):
        provider.propose("print x", CONTEXT)


def test_a_deadline_passes_an_unexpected_error_through_at_once():
    def broken(url, headers, body, timeout):
        raise ValueError("a bug, not a slow server")

    with pytest.raises(ValueError, match="a bug"):
        DeadlineProvider(openai(broken), 5).propose("print x", CONTEXT)


def test_a_deadline_keeps_the_name_and_model_of_the_provider():
    provider = DeadlineProvider(openai(Wire()), 5)
    assert (provider.name, provider.model) == ("openai", "m")


def test_fake_replays_a_recorded_reading_as_raw_json():
    fake = FakeProvider(FIXTURES)
    [raw] = fake.propose("bump visits up by 3", CONTEXT)
    assert json.loads(raw.text)["readings"][0]["intent"] == "increment"
    assert fake.calls == ["bump visits up by 3"]


def test_fake_replays_raw_text_unchanged():
    [raw] = FakeProvider(FIXTURES).propose("make everything nice", CONTEXT)
    assert raw.text == "not json at all"


def test_fake_replays_a_timeout_and_a_failure():
    fake = FakeProvider(FIXTURES)
    with pytest.raises(ProviderTimeout):
        fake.propose("slow sentence", CONTEXT)
    with pytest.raises(ProviderError):
        fake.propose("broken sentence", CONTEXT)


def test_fake_has_no_answer_for_an_unrecorded_sentence():
    with pytest.raises(ProviderError, match="no recorded response"):
        FakeProvider(FIXTURES).propose("never recorded", CONTEXT)
