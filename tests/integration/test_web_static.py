"""The API serving the built frontend, so the whole site can be one service."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from parsley.web.app import _inside, create_app  # noqa: E402

INDEX = "<!doctype html><title>Parsley</title>"


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "parsley.svg").write_text("<svg/>", encoding="utf-8")
    (root / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return root


@pytest.fixture
def client(dist):
    return TestClient(create_app(web_dist=dist), raise_server_exceptions=False)


def test_the_root_serves_the_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")


def test_a_built_file_is_served_with_its_type(client):
    response = client.get("/assets/index-abc.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_a_file_at_the_root_of_the_build_is_served(client):
    assert client.get("/parsley.svg").text == "<svg/>"


def test_a_client_side_route_falls_back_to_the_page(client):
    response = client.get("/some/client/route")
    assert response.status_code == 200
    assert response.text == INDEX


def test_a_missing_asset_is_a_404_and_not_the_page(client):
    assert client.get("/assets/gone.js").status_code == 404


def test_a_missing_api_route_stays_a_json_404(client):
    response = client.get("/api/missing")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert client.get("/api").status_code == 404


def test_the_api_still_works_beside_the_page(client):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/session").status_code == 200


@pytest.mark.parametrize("path", [
    "/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt",
    "/assets/%2e%2e/%2e%2e/secret.txt",
])
def test_nothing_outside_the_build_can_be_read(client, path):
    assert "outside" not in client.get(path).text


@pytest.mark.parametrize("path", ["//attacker/share/x", "\\\\attacker\\share", "C:\\Windows\\win.ini", "a:b"])
def test_a_network_or_drive_path_never_reaches_the_filesystem(dist, path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise AssertionError("the path reached the filesystem")

    monkeypatch.setattr(type(dist), "resolve", refuse)
    assert _inside(dist, path) is False


def test_a_nul_byte_in_a_path_gives_no_trace(client):
    response = client.get("/%00")
    assert "Traceback" not in response.text
    assert response.status_code in (200, 404)


def test_hashed_assets_are_cached_and_the_page_is_not(client):
    assert "immutable" in client.get("/assets/index-abc.js").headers["cache-control"]
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/some/route").headers["cache-control"] == "no-cache"


def test_pages_carry_the_security_headers(client):
    headers = client.get("/").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in headers["content-security-policy"]


def test_a_head_request_works_for_a_platform_probe(client):
    assert client.head("/").status_code == 200


def test_the_directory_comes_from_the_environment(dist, monkeypatch):
    monkeypatch.setenv("PARSLEY_WEB_DIST", str(dist))
    assert TestClient(create_app()).get("/").text == INDEX


def test_without_a_build_there_are_no_pages():
    assert TestClient(create_app()).get("/").status_code == 404


def test_a_build_without_a_page_stops_the_server(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(web_dist=tmp_path)
