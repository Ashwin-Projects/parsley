"""The deployment files: what they promise, read as text (no PyYAML, no Docker needed)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_image_listens_on_the_platforms_port():
    dockerfile = text("Dockerfile")
    assert "${PORT:-8000}" in dockerfile
    assert "parsley.web.app:app" in dockerfile
    assert re.search(r"pip install '\.\[web\]'", dockerfile)


def test_the_image_builds_the_frontend_for_the_same_origin():
    dockerfile = text("Dockerfile")
    assert "VITE_USE_MOCK=false" in dockerfile
    assert 'VITE_API_URL=""' in dockerfile
    assert "PARSLEY_WEB_DIST=" in dockerfile


def test_the_image_does_not_run_as_root():
    assert re.search(r"^USER \w+", text("Dockerfile"), re.M)


def test_the_image_writes_no_access_log():
    assert "--no-access-log" in text("Dockerfile")  # /api/program carries the session id in its URL


def test_the_build_context_is_an_allow_list():
    lines = text(".dockerignore").split()
    assert lines[0] == "*"
    assert not any(line.startswith("!") and ".env" in line for line in lines)


def test_no_blueprint_value_is_committed_for_a_model_setting():
    blueprint = text("render.yaml")
    blocks = re.findall(r"- key: (PARSLEY_LLM_\w+)\n((?:\s+\w+:.*\n)*)", blueprint)
    assert {name for name, _ in blocks} >= {
        "PARSLEY_LLM_PROVIDER", "PARSLEY_LLM_BASE_URL", "PARSLEY_LLM_MODEL", "PARSLEY_LLM_API_KEY",
    }
    for name, block in blocks:
        assert "sync: false" in block, name
        assert "value:" not in block, name


def test_the_blueprint_uses_the_docker_free_plan():
    blueprint = text("render.yaml")
    assert "runtime: docker" in blueprint
    assert "plan: free" in blueprint
    assert "healthCheckPath: /api/health" in blueprint


def test_compose_counts_visitors_and_not_nginx():
    assert "PARSLEY_CLIENT_IP_HEADER: X-Real-IP" in text("docker-compose.yml")
    assert "proxy_set_header X-Real-IP $remote_addr" in text("docker/nginx.conf")


def test_the_guide_covers_both_hosts_and_every_limit():
    guide = text("docs/DEPLOY.md")
    assert "Render" in guide and "Hugging Face" in guide
    for name in (
        "PARSLEY_RATE_LIMIT_PER_MINUTE", "PARSLEY_HARD_RATE_LIMIT_PER_MINUTE", "PARSLEY_LLM_DAILY_CAP",
        "PARSLEY_LLM_SESSION_CAP", "PARSLEY_MAX_SESSIONS", "PARSLEY_SESSION_TTL", "PARSLEY_ALLOWED_ORIGINS",
        "PARSLEY_CLIENT_IP_HEADER", "PARSLEY_FRAME_ANCESTORS",
    ):
        assert name in guide, name
