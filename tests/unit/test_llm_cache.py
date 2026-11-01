"""MeteredProvider: a disk cache keyed by (model, prompt, input), pacing and rate-limit backoff."""

import hashlib
import json
from pathlib import Path

import pytest

from parsley.llm import cache as cache_module
from parsley.llm.cache import MeteredProvider, cache_key
from parsley.llm.prompt import PROMPT_SHA256, SYSTEM_PROMPT, LLMContext
from parsley.llm.provider import (
    FakeProvider,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    RawProposal,
)

EMPTY = LLMContext()
CONTEXT = LLMContext(symbols=(("x", "number"),), ref_stack=("x",))


class Inner:
    name = "inner"

    def __init__(self, *steps):
        self.steps = list(steps) or ['{"readings": []}']
        self.calls = 0

    def propose(self, sentence, context):
        self.calls += 1
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return [RawProposal(step, self.name)]


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def metered(inner, tmp_path, **kwargs):
    clock = kwargs.pop("clock", Clock())
    return MeteredProvider(inner, "m", tmp_path, sleep=clock.sleep, clock=clock.time, **kwargs)


def test_the_prompt_hash_is_of_the_system_prompt():
    assert PROMPT_SHA256 == hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def test_the_key_depends_on_model_prompt_and_input(monkeypatch):
    base = cache_key("m", "print x", EMPTY)
    assert cache_key("m", "print x", EMPTY) == base
    assert cache_key("other", "print x", EMPTY) != base
    assert cache_key("m", "print y", EMPTY) != base
    assert cache_key("m", "print x", CONTEXT) != base
    monkeypatch.setattr(cache_module, "PROMPT_SHA256", "changed")
    assert cache_key("m", "print x", EMPTY) != base


def test_the_second_identical_call_is_free(tmp_path):
    inner = Inner()
    provider = metered(inner, tmp_path)
    first = provider.propose("print x", EMPTY)
    assert provider.propose("print x", EMPTY) == first
    assert inner.calls == 1
    assert (provider.network_calls, provider.cache_hits) == (1, 1)


def test_the_cache_survives_a_new_process(tmp_path):
    metered(Inner('{"readings": [1]}'), tmp_path).propose("print x", EMPTY)
    dead = Inner(ProviderError("no network"))
    [raw] = metered(dead, tmp_path).propose("print x", EMPTY)
    assert raw.text == '{"readings": [1]}'
    assert dead.calls == 0


def test_a_cached_call_replays_its_original_latency(tmp_path):
    clock = Clock()

    class Slow(Inner):
        def propose(self, sentence, context):
            clock.now += 1.5
            return super().propose(sentence, context)

    first = metered(Slow(), tmp_path, clock=clock)
    first.propose("print x", EMPTY)
    assert first.last_latency == pytest.approx(1.5)
    second = metered(Inner(), tmp_path, clock=clock)
    second.propose("print x", EMPTY)
    assert second.last_latency == pytest.approx(1.5)


def test_a_failed_call_is_not_cached(tmp_path):
    inner = Inner(ProviderError("down"), '{"readings": []}')
    provider = metered(inner, tmp_path)
    with pytest.raises(ProviderError):
        provider.propose("print x", EMPTY)
    assert provider.failures == 1 and provider.last_latency is None
    assert provider.propose("print x", EMPTY)[0].text == '{"readings": []}'


def test_a_timeout_passes_through(tmp_path):
    with pytest.raises(ProviderTimeout):
        metered(Inner(ProviderTimeout("late")), tmp_path).propose("print x", EMPTY)


def test_a_corrupt_cache_file_is_a_miss(tmp_path):
    (tmp_path / f"{cache_key('m', 'print x', EMPTY)}.json").write_text("{broken", encoding="utf-8")
    inner = Inner()
    metered(inner, tmp_path).propose("print x", EMPTY)
    assert inner.calls == 1


def test_real_calls_are_paced(tmp_path):
    clock = Clock()
    provider = metered(Inner(), tmp_path, clock=clock, delay=2.0)
    provider.propose("a", EMPTY)
    provider.propose("b", EMPTY)
    assert clock.sleeps == [pytest.approx(2.0)]


def test_cached_calls_are_not_paced(tmp_path):
    clock = Clock()
    provider = metered(Inner(), tmp_path, clock=clock, delay=2.0)
    provider.propose("a", EMPTY)
    provider.propose("a", EMPTY)
    assert clock.sleeps == []


def test_rate_limits_back_off_and_recover(tmp_path):
    clock = Clock()
    limited = ProviderRateLimited("slow down")
    provider = metered(Inner(limited, limited, '{"readings": []}'), tmp_path, clock=clock, backoffs=(5, 10, 20))
    assert len(provider.propose("a", EMPTY)) == 1
    assert clock.sleeps == [5, 10]
    assert provider.rate_limited == 2


def test_rate_limits_give_up_after_the_last_backoff(tmp_path):
    clock = Clock()
    provider = metered(Inner(ProviderRateLimited("no")), tmp_path, clock=clock, backoffs=(5, 10))
    with pytest.raises(ProviderRateLimited):
        provider.propose("a", EMPTY)
    assert clock.sleeps == [5, 10]
    assert provider.failures == 1


def test_a_fixture_replays_through_the_fake_provider(tmp_path):
    inner = Inner('{"readings": []}')
    provider = metered(inner, tmp_path / "cache")
    provider.propose("print x", EMPTY)
    provider.propose("print x", CONTEXT)
    path = tmp_path / "recorded.json"
    provider.write_fixture(path)
    fake = FakeProvider(path)
    assert fake.model == "m"
    assert fake.propose("print x", CONTEXT)[0].text == '{"readings": []}'
    assert fake.propose("print x", EMPTY)[0].text == '{"readings": []}'


def test_the_fake_provider_tells_contexts_apart(tmp_path):
    path = tmp_path / "recorded.json"
    path.write_text(json.dumps({"responses": [
        {"sentence": "s", "raw": "no context"},
        {"sentence": "s", "raw": "with x", "context": {"symbols": [["x", "number"]], "reference_stack": ["x"]}},
    ]}), encoding="utf-8")
    fake = FakeProvider(path)
    assert fake.propose("s", CONTEXT)[0].text == "with x"
    assert fake.propose("s", EMPTY)[0].text == "no context"


def test_a_cache_file_holds_no_secret(tmp_path):
    inner = Inner()
    inner.api_key = "sk-SECRET"
    provider = metered(inner, tmp_path / "cache")
    provider.propose("print x", EMPTY)
    fixture = tmp_path / "recorded.json"
    provider.write_fixture(fixture)
    for path in [*Path(tmp_path / "cache").iterdir(), fixture]:
        assert "sk-SECRET" not in path.read_text(encoding="utf-8")
