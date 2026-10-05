import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


@pytest.fixture
def laptop(user_id, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.trycloudflare.com")
    c = TestClient(app, follow_redirects=False)
    c.headers["Authorization"] = "Bearer tok-test"
    return c


def _code(laptop) -> str:
    r = laptop.post("/api/device-link")
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("https://abc.trycloudflare.com/auth/device?code=")
    return parse_qs(urlparse(url).query)["code"][0]


def test_code_logs_phone_in_once(laptop):
    code = _code(laptop)
    phone = TestClient(app, follow_redirects=False)
    r = phone.get("/auth/device", params={"code": code})
    assert r.headers["location"] == "/"
    assert "fp_token=tok-test" in r.headers["set-cookie"]

    again = TestClient(app, follow_redirects=False).get("/auth/device", params={"code": code})
    assert "error=device_link_expired" in again.headers["location"]
    assert "set-cookie" not in again.headers


def test_expired_code_is_rejected(laptop):
    code = _code(laptop)
    db.execute("UPDATE device_links SET expires_at=?", (time.time() - 1,))
    r = TestClient(app, follow_redirects=False).get("/auth/device", params={"code": code})
    assert "error=device_link_expired" in r.headers["location"]


def test_unknown_or_empty_code_is_rejected():
    for params in ({"code": "nope"}, {}):
        r = TestClient(app, follow_redirects=False).get("/auth/device", params=params)
        assert "error=device_link_expired" in r.headers["location"]
        assert "set-cookie" not in r.headers


def test_code_is_not_stored_in_plaintext(laptop):
    code = _code(laptop)
    stored = [r["code_hash"] for r in db.rows("SELECT code_hash FROM device_links")]
    assert code not in stored


def test_link_requires_login(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.trycloudflare.com")
    assert TestClient(app).post("/api/device-link").status_code == 401


def test_no_public_url_means_no_link(laptop, monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLIC_URL")
    monkeypatch.setattr(config, "PUBLIC_URL_FILE", tmp_path / "missing")
    assert laptop.post("/api/device-link").status_code == 409
