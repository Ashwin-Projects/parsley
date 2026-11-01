"""LLM configuration: environment variables and .env, loaded only when a mode asks for them."""

from pathlib import Path

import pytest

from parsley.llm.config import ConfigError, load_dotenv, load_provider, provider_from_env
from parsley.llm.prompt import LLMContext
from parsley.llm.provider import AnthropicProvider, FakeProvider, OpenAICompatibleProvider

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures_llm" / "recorded.json"


def test_load_dotenv_reads_keys_and_ignores_comments(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        '# a comment\n\nPARSLEY_LLM_PROVIDER=anthropic\nexport A="quoted value"\nB=\'single\'\nnot a pair\n',
        encoding="utf-8",
    )
    assert load_dotenv(path) == {"PARSLEY_LLM_PROVIDER": "anthropic", "A": "quoted value", "B": "single"}


def test_a_missing_dotenv_is_empty(tmp_path):
    assert load_dotenv(tmp_path / ".env") == {}


def test_anthropic_defaults():
    built = provider_from_env({"PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"})
    assert isinstance(built, AnthropicProvider)
    assert (built.model, built.api_key, built.base_url) == ("claude-opus-5-5", "k", "https://api.anthropic.com")


def test_openai_compatible_with_a_custom_base_url_and_no_key():
    built = provider_from_env({
        "PARSLEY_LLM_PROVIDER": "openai", "PARSLEY_LLM_MODEL": "llama3.3",
        "PARSLEY_LLM_BASE_URL": "http://localhost:11434/v1/",
    })
    assert isinstance(built, OpenAICompatibleProvider)
    assert (built.model, built.base_url, built.api_key) == ("llama3.3", "http://localhost:11434/v1", None)


def test_the_generic_key_wins_over_the_vendor_key():
    built = provider_from_env({
        "PARSLEY_LLM_PROVIDER": "openai", "PARSLEY_LLM_MODEL": "m",
        "PARSLEY_LLM_BASE_URL": "https://api.groq.com/openai/v1",
        "OPENAI_API_KEY": "vendor", "PARSLEY_LLM_API_KEY": "generic",
    })
    assert built.api_key == "generic"


def test_a_key_with_surrounding_whitespace_is_trimmed():
    built = provider_from_env({"PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": " k\r\n"})
    assert built.api_key == "k"


def test_a_key_with_a_control_character_is_refused_without_quoting_it():
    with pytest.raises(ConfigError) as caught:
        provider_from_env({"PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-SECRET\nabc"})
    assert "sk-SECRET" not in str(caught.value)


def test_dotenv_cannot_redirect_a_key_from_the_real_environment(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PARSLEY_LLM_PROVIDER=anthropic\nPARSLEY_LLM_BASE_URL=https://evil.example\n", encoding="utf-8",
    )
    monkeypatch.delenv("PARSLEY_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PARSLEY_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-key")
    with pytest.raises(ConfigError, match="PARSLEY_LLM_BASE_URL"):
        load_provider(tmp_path / ".env").propose("print x", LLMContext())


def test_dotenv_may_set_a_base_url_for_its_own_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PARSLEY_LLM_PROVIDER=openai\nPARSLEY_LLM_MODEL=m\nPARSLEY_LLM_BASE_URL=https://api.groq.com/openai/v1\n"
        "PARSLEY_LLM_API_KEY=file-key\n", encoding="utf-8",
    )
    monkeypatch.delenv("PARSLEY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PARSLEY_LLM_MODEL", raising=False)
    monkeypatch.delenv("PARSLEY_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PARSLEY_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "other")
    built = load_provider(tmp_path / ".env")
    assert (built.base_url, built.api_key) == ("https://api.groq.com/openai/v1", "file-key")


def test_timeout_setting():
    built = provider_from_env({
        "PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k", "PARSLEY_LLM_TIMEOUT": "7.5",
    })
    assert built.timeout == 7.5


def test_fake_provider_from_env():
    built = provider_from_env({"PARSLEY_LLM_PROVIDER": "fake", "PARSLEY_LLM_FIXTURES": str(FIXTURES)})
    assert isinstance(built, FakeProvider)


@pytest.mark.parametrize(("environ", "message"), [
    ({}, "PARSLEY_LLM_PROVIDER"),
    ({"PARSLEY_LLM_PROVIDER": "mystery"}, "mystery"),
    ({"PARSLEY_LLM_PROVIDER": "anthropic"}, "ANTHROPIC_API_KEY"),
    ({"PARSLEY_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "k"}, "PARSLEY_LLM_MODEL"),
    ({"PARSLEY_LLM_PROVIDER": "fake"}, "PARSLEY_LLM_FIXTURES"),
    ({"PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k", "PARSLEY_LLM_TIMEOUT": "soon"}, "TIMEOUT"),
    ({"PARSLEY_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k", "PARSLEY_LLM_TIMEOUT": "0"}, "TIMEOUT"),
    ({"PARSLEY_LLM_PROVIDER": "openai", "PARSLEY_LLM_MODEL": "m",
      "PARSLEY_LLM_BASE_URL": "file:///etc/passwd"}, "http"),
])
def test_bad_configuration_is_a_config_error(environ, message):
    with pytest.raises(ConfigError, match=message):
        provider_from_env(environ)


@pytest.mark.parametrize("url", ["http://api.example.com/v1", "http://localhost.example.com/v1"])
def test_a_key_is_never_sent_over_plain_http_to_a_remote_host(url):
    with pytest.raises(ConfigError, match="https"):
        provider_from_env({
            "PARSLEY_LLM_PROVIDER": "openai", "PARSLEY_LLM_MODEL": "m",
            "PARSLEY_LLM_BASE_URL": url, "OPENAI_API_KEY": "k",
        })


def test_real_environment_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "PARSLEY_LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=from-file\nPARSLEY_LLM_MODEL=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PARSLEY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PARSLEY_LLM_API_KEY", raising=False)
    monkeypatch.setenv("PARSLEY_LLM_MODEL", "from-env")
    built = load_provider(tmp_path / ".env")
    assert (built.model, built.api_key) == ("from-env", "from-file")


def test_load_provider_defers_a_config_error_to_the_call(tmp_path, monkeypatch):
    monkeypatch.delenv("PARSLEY_LLM_PROVIDER", raising=False)
    built = load_provider(tmp_path / ".env")
    with pytest.raises(ConfigError, match="PARSLEY_LLM_PROVIDER"):
        built.propose("print x", LLMContext())


def test_dotenv_is_git_ignored_and_the_example_is_not():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored
    assert (ROOT / ".env.example").is_file()
