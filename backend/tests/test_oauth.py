from fastapi.testclient import TestClient

from app.main import app

# No `with`: lifespan (background WHOOP sync, Telegram polling) must not start in tests.
client = TestClient(app, follow_redirects=False)


def test_callback_rejects_missing_state_and_cookie():
    r = client.get("/auth/callback", params={"code": "x"})
    assert r.status_code == 400


def test_callback_rejects_missing_cookie():
    r = client.get("/auth/callback", params={"code": "x", "state": "abc"})
    assert r.status_code == 400


def test_callback_rejects_mismatched_state():
    client.cookies.set("oauth_state", "expected")
    try:
        r = client.get("/auth/callback", params={"code": "x", "state": "other"})
    finally:
        client.cookies.clear()
    assert r.status_code == 400


def test_error_param_is_url_encoded():
    r = client.get("/auth/callback", params={"error": "a&b=c"})
    assert r.status_code in (302, 307)
    assert r.headers["location"].endswith("?error=a%26b%3Dc")
