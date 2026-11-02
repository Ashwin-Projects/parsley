"""Limits of a public deployment: rate, LLM budget, CORS, headers. FakeProvider, no network."""

import datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from parsley.llm.config import ConfigError  # noqa: E402
from parsley.llm.provider import FakeProvider, ProviderError, RawProposal  # noqa: E402
from parsley.web.app import create_app  # noqa: E402
from parsley.web.limits import (  # noqa: E402
    DEFAULT_ORIGINS,
    DailyBudget,
    RateLimiter,
    WebLimits,
    client_ip,
)
from parsley.web.sessions import DEFAULT_CAPACITY, DEFAULT_TTL  # noqa: E402

RECORDED = Path(__file__).resolve().parents[1] / "fixtures_llm" / "recorded.json"
SENTENCE = "store 50 in bonus"  # no rule reads it, and recorded.json holds the model's reading
GENEROUS = {"soft_rate": 1000, "hard_rate": 1000, "daily_llm_calls": 1000, "session_llm_calls": 1000}


class Counting(FakeProvider):
    def propose(self, sentence, context):
        self.count = getattr(self, "count", 0) + 1
        return super().propose(sentence, context)


def app_with(provider=None, **limits):
    source = provider or Counting(RECORDED)
    return TestClient(create_app(provider=source, limits=WebLimits(**{**GENEROUS, **limits}))), source


def new_session(client):
    return client.post("/api/session").json()["session_id"]


def compile_(client, sid, sentence=SENTENCE, mode="hybrid"):
    return client.post("/api/compile", json={"session_id": sid, "sentence": sentence, "mode": mode})


def codes(response):
    return [d["code"] for d in response.json()["diagnostics"]]


# Configuration


def test_the_defaults():
    limits = WebLimits.from_env({})
    assert (limits.soft_rate, limits.hard_rate) == (20, 120)
    assert (limits.daily_llm_calls, limits.session_llm_calls) == (500, 50)
    assert (limits.max_sessions, limits.session_ttl) == (DEFAULT_CAPACITY, DEFAULT_TTL)
    assert limits.allowed_origins == DEFAULT_ORIGINS
    assert limits.client_ip_header is None


def test_every_limit_comes_from_the_environment():
    limits = WebLimits.from_env({
        "PARSLEY_RATE_LIMIT_PER_MINUTE": "5", "PARSLEY_HARD_RATE_LIMIT_PER_MINUTE": "9",
        "PARSLEY_LLM_DAILY_CAP": "7", "PARSLEY_LLM_SESSION_CAP": "3", "PARSLEY_MAX_SESSIONS": "11",
        "PARSLEY_SESSION_TTL": "60", "PARSLEY_ALLOWED_ORIGINS": "https://a.example, https://b.example",
        "PARSLEY_CLIENT_IP_HEADER": "CF-Connecting-IP", "PARSLEY_FRAME_ANCESTORS": "https://huggingface.co",
    })
    assert (limits.soft_rate, limits.hard_rate, limits.daily_llm_calls, limits.session_llm_calls) == (5, 9, 7, 3)
    assert (limits.max_sessions, limits.session_ttl) == (11, 60)
    assert limits.allowed_origins == ("https://a.example", "https://b.example")
    assert limits.client_ip_header == "CF-Connecting-IP"
    assert limits.frame_ancestors == "https://huggingface.co"


@pytest.mark.parametrize("name, value", [
    ("PARSLEY_LLM_DAILY_CAP", "lots"), ("PARSLEY_LLM_DAILY_CAP", "-1"), ("PARSLEY_MAX_SESSIONS", "0"),
    ("PARSLEY_ALLOWED_ORIGINS", "*"), ("PARSLEY_ALLOWED_ORIGINS", "example.com"),
])
def test_a_bad_limit_stops_the_server_instead_of_being_ignored(name, value):
    with pytest.raises(ValueError, match=name):
        WebLimits.from_env({name: value})


def test_a_zero_daily_cap_turns_the_llm_off():
    client, source = app_with(daily_llm_calls=0)
    assert "W515" in codes(compile_(client, new_session(client)))
    assert getattr(source, "count", 0) == 0


def test_the_server_reads_its_limits_from_the_environment(monkeypatch):
    monkeypatch.setenv("PARSLEY_LLM_DAILY_CAP", "0")
    client = TestClient(create_app(provider=FakeProvider(RECORDED)))
    assert client.get("/api/health").json()["llm_budget_remaining"] is False


# Per-address rate


def test_over_the_soft_limit_a_sentence_falls_back_to_the_rules():
    client, source = app_with(soft_rate=1)
    sid = new_session(client)  # one request
    response = compile_(client, sid)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"  # the rule result for this sentence
    assert "W515" in codes(response)
    assert getattr(source, "count", 0) == 0


def test_under_the_soft_limit_the_model_is_asked():
    client, source = app_with(soft_rate=5)
    response = compile_(client, new_session(client))
    assert response.json()["status"] == "accepted"
    assert "W515" not in codes(response)
    assert source.count == 1


def test_a_rules_sentence_over_the_soft_limit_is_not_warned_about():
    client, _ = app_with(soft_rate=1)
    response = compile_(client, new_session(client), "print 1", "rules")
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    assert "W515" not in codes(response)


def test_a_sentence_the_rules_solve_does_not_warn_in_hybrid():
    client, _ = app_with(soft_rate=1)
    assert "W515" not in codes(compile_(client, new_session(client), "print 1"))


def test_answers_count_towards_the_limit():
    client, _ = app_with(hard_rate=3)
    sid = new_session(client)
    assert client.post("/api/answer", json={"session_id": sid, "answer": "yes"}).status_code == 200
    assert client.post("/api/answer", json={"session_id": sid, "answer": "yes"}).status_code == 200
    assert client.post("/api/answer", json={"session_id": sid, "answer": "yes"}).status_code == 429


def test_over_the_hard_limit_the_answer_is_a_429_the_frontend_understands():
    client, _ = app_with(hard_rate=2)
    sid = new_session(client)
    assert compile_(client, sid, "print 1", "rules").status_code == 200
    response = compile_(client, sid, "print 1", "rules")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json() == {"detail": "too many requests"}


def test_creating_sessions_and_running_count_towards_the_hard_limit():
    client, _ = app_with(hard_rate=3)
    sid = new_session(client)
    assert client.post("/api/run", json={"session_id": sid}).status_code == 200
    assert client.post("/api/run", json={"session_id": sid}).status_code == 200
    assert client.post("/api/run", json={"session_id": sid}).status_code == 429
    assert client.post("/api/session").status_code == 429


def test_one_address_does_not_use_up_anothers_limit():
    app = create_app(provider=FakeProvider(RECORDED), limits=WebLimits(**{**GENEROUS, "hard_rate": 1}))
    first = TestClient(app, client=("198.51.100.1", 1))
    second = TestClient(app, client=("198.51.100.2", 1))
    first.post("/api/session")
    assert first.post("/api/session").status_code == 429
    assert second.post("/api/session").status_code == 200


def test_the_window_slides():
    now = [100.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert [limiter.hit("a") for _ in range(3)] == [1, 2, 3]
    now[0] += 61
    assert limiter.hit("a") == 1


def test_a_flood_of_addresses_does_not_grow_memory_without_bound():
    limiter = RateLimiter(max_addresses=10)
    for n in range(1000):
        limiter.hit(f"a{n}")
    assert len(limiter) <= 10


# Which address


class Peer:
    def __init__(self, host, **headers):
        self.client = None if host is None else type("Address", (), {"host": host})
        self.headers = {key.replace("_", "-").lower(): value for key, value in headers.items()}


def test_without_a_trusted_header_a_forwarded_address_is_ignored():
    assert client_ip(Peer("10.0.0.1", x_forwarded_for="198.51.100.9"), None) == "10.0.0.1"


def test_a_trusted_header_names_the_client():
    assert client_ip(Peer("10.0.0.1", cf_connecting_ip="198.51.100.9"), "CF-Connecting-IP") == "198.51.100.9"


def test_only_the_last_entry_of_a_list_is_believed():
    request = Peer("10.0.0.1", x_forwarded_for="1.2.3.4, 198.51.100.9")
    assert client_ip(request, "X-Forwarded-For") == "198.51.100.9"


@pytest.mark.parametrize("value", ["", "not an address", "1.2.3.4; drop"])
def test_a_bad_header_falls_back_to_the_socket(value):
    assert client_ip(Peer("10.0.0.1", x_real_ip=value), "X-Real-IP") == "10.0.0.1"


def test_no_address_at_all_is_one_shared_bucket():
    assert client_ip(Peer(None), None) == "unknown"


# LLM budget


def test_the_daily_cap_is_shared_by_every_session_and_falls_back():
    client, source = app_with(daily_llm_calls=2)
    for _ in range(2):
        assert compile_(client, new_session(client)).json()["status"] == "accepted"
    response = compile_(client, new_session(client))
    assert response.status_code == 200 and "W515" in codes(response)
    assert source.count == 2


def test_the_daily_cap_resets_at_midnight_utc():
    today = [datetime.date(2026, 11, 2)]
    budget = DailyBudget(1, today=lambda: today[0])
    assert budget.take() is True
    assert budget.take() is False
    assert budget.remaining() is False
    today[0] = datetime.date(2026, 11, 3)
    assert budget.remaining() is True
    assert budget.take() is True


def test_a_sentence_the_rules_solve_spends_nothing():
    client, source = app_with(daily_llm_calls=1)
    compile_(client, new_session(client), "print 1")
    assert getattr(source, "count", 0) == 0
    assert client.get("/api/health").json()["llm_budget_remaining"] is True


def test_the_session_cap_falls_back_and_another_session_still_works():
    client, source = app_with(session_llm_calls=1)
    sid = new_session(client)
    assert compile_(client, sid).json()["status"] == "accepted"
    response = compile_(client, sid, "store 60 in bonus")
    assert response.status_code == 200 and "W515" in codes(response)
    assert compile_(client, new_session(client)).json()["status"] == "accepted"
    assert source.count == 2


def test_a_reset_does_not_refill_a_session():
    client, source = app_with(session_llm_calls=1)
    sid = new_session(client)
    compile_(client, sid)
    client.post("/api/reset", json={"session_id": sid})
    assert "W515" in codes(compile_(client, sid))
    assert source.count == 1


def test_the_warning_gives_no_count():
    client, _ = app_with(daily_llm_calls=0)
    response = compile_(client, new_session(client))
    message = next(d["message"] for d in response.json()["diagnostics"] if d["code"] == "W515")
    assert "uses the rule result" in message
    assert not any(ch.isdigit() for ch in message)


def test_a_capped_session_keeps_working_in_rules():
    client, _ = app_with(daily_llm_calls=0)
    sid = new_session(client)
    assert compile_(client, sid, "print 1", "rules").json()["status"] == "accepted"
    assert client.post("/api/run", json={"session_id": sid}).json()["output"] == ["1"]


def test_a_failed_call_still_spends_budget():
    class Down:
        name = "down"
        count = 0

        def propose(self, sentence, context):
            type(self).count += 1
            raise ProviderError("no")

    client, source = app_with(Down(), daily_llm_calls=1)
    compile_(client, new_session(client))
    assert "W515" in codes(compile_(client, new_session(client)))
    assert source.count == 1


def test_an_unconfigured_provider_spends_nothing_and_has_no_budget():
    class Unavailable:
        name = "unavailable"
        error = ConfigError("set a provider")

        def propose(self, sentence, context):
            raise self.error

    client = TestClient(create_app(provider_factory=Unavailable, limits=WebLimits(**GENEROUS)))
    response = compile_(client, new_session(client))
    assert "W514" in codes(response) and "W515" not in codes(response)
    body = client.get("/api/health").json()
    assert body["llm_configured"] is False and body["llm_budget_remaining"] is False


def test_health_shows_only_whether_budget_remains():
    client, _ = app_with(daily_llm_calls=1)
    assert client.get("/api/health").json()["llm_budget_remaining"] is True
    compile_(client, new_session(client))
    body = client.get("/api/health").json()
    assert body["llm_budget_remaining"] is False
    assert set(body) == {"version", "llm_configured", "provider", "model", "llm_budget_remaining"}


def test_a_provider_returning_nothing_still_spends_one_call():
    class Empty:
        name = "empty"

        def propose(self, sentence, context):
            return [RawProposal('{"readings": []}', self.name)]

    client, _ = app_with(Empty(), daily_llm_calls=1)
    compile_(client, new_session(client))
    assert client.get("/api/health").json()["llm_budget_remaining"] is False


# Sessions and bodies


def test_max_sessions_reaches_the_store():
    client, _ = app_with(max_sessions=2)
    oldest = new_session(client)
    new_session(client)
    new_session(client)
    assert len(client.app.state.store) == 2
    assert compile_(client, oldest, "print 1", "rules").status_code == 404


def test_the_ttl_reaches_the_store():
    client, _ = app_with(session_ttl=-1)
    assert compile_(client, new_session(client), "print 1", "rules").status_code == 404


def test_a_chunked_oversized_body_is_refused():
    client, _ = app_with()

    def chunks():
        yield b'{"session_id": "x", "sentence": "'
        for _ in range(100):
            yield b"x" * 1024
        yield b'"}'

    response = client.post("/api/compile", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert "Traceback" not in response.text


# CORS and headers


def test_only_a_configured_origin_gets_cors():
    client, _ = app_with(allowed_origins=("https://parsley.example",))
    allowed = client.get("/api/health", headers={"origin": "https://parsley.example"})
    other = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "https://parsley.example"
    assert "access-control-allow-origin" not in other.headers


def test_retry_after_is_readable_across_origins():
    client, _ = app_with(hard_rate=1, allowed_origins=("https://parsley.example",))
    headers = {"origin": "https://parsley.example"}
    client.post("/api/session", headers=headers)
    response = client.post("/api/session", headers=headers)
    assert response.status_code == 429
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()


@pytest.mark.parametrize("method, path", [("get", "/api/health"), ("get", "/api/missing"), ("post", "/api/session")])
def test_every_response_has_the_security_headers(method, path):
    client, _ = app_with()
    headers = getattr(client, method)(path).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["strict-transport-security"].startswith("max-age=")
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["permissions-policy"]


def test_a_refused_body_and_a_429_have_the_security_headers_too():
    client, _ = app_with(hard_rate=1)
    client.post("/api/session")
    assert client.post("/api/session").headers["x-content-type-options"] == "nosniff"
    big = client.post("/api/compile", content="x" * 10000, headers={"content-type": "application/json"})
    assert big.status_code == 413 and big.headers["x-content-type-options"] == "nosniff"


def test_an_unexpected_failure_has_the_security_headers_and_no_trace():
    def explode():
        raise RuntimeError("secret detail")

    client = TestClient(
        create_app(provider_factory=explode, limits=WebLimits(**GENEROUS)), raise_server_exceptions=False,
    )
    response = client.get("/api/health")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal error"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_frame_ancestors_can_be_opened_for_an_embedding_host():
    client, _ = app_with(frame_ancestors="https://huggingface.co")
    assert "frame-ancestors https://huggingface.co" in client.get("/api/health").headers["content-security-policy"]


def test_api_responses_are_not_cached():
    client, _ = app_with()
    assert client.post("/api/session").headers["cache-control"] == "no-store"
