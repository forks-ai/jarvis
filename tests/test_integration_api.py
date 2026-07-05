"""Integration tests: exercise the real FastAPI apps through Starlette's
TestClient (full middleware + routing stack, no network to Hermes/ElevenLabs).
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# HTTP auth middleware (/api/*)                                                #
# --------------------------------------------------------------------------- #
def test_api_open_when_no_token(no_token, client):
    r = client.get("/api/usage")
    assert r.status_code == 200
    assert "llm" in r.json()


def test_api_401_without_token(with_token, client):
    r = client.get("/api/usage")
    assert r.status_code == 401
    assert "auth required" in r.text


def test_api_200_with_header_token(with_token, client):
    r = client.get("/api/usage", headers={"X-Jarvis-Token": "s3cr3t-token"})
    assert r.status_code == 200


def test_api_200_with_cookie_token(with_token, client):
    client.cookies.set("jarvis_token", "s3cr3t-token")
    r = client.get("/api/usage")
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# /api/chat input validation                                                   #
# --------------------------------------------------------------------------- #
def test_chat_rejects_empty_input(no_token, client):
    r = client.post("/api/chat", json={"input": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "empty input"


def test_chat_backend_unreachable_is_graceful_502(no_token, client):
    # Hermes is not running in tests -> endpoint must fail closed with 502,
    # never a 500 stack trace or a hang.
    r = client.post("/api/chat", json={"input": "hello"})
    assert r.status_code == 502
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# Hermes reverse-proxy allow-list                                             #
# --------------------------------------------------------------------------- #
def test_hermes_proxy_blocks_unlisted_path(no_token, client):
    r = client.get("/api/hermes/admin")
    assert r.status_code == 403
    assert "not allowed" in r.text


def test_hermes_proxy_blocks_post_to_sessions(no_token, client):
    r = client.post("/api/hermes/api/sessions", json={})
    assert r.status_code == 403


def test_hermes_proxy_blocks_traversal(no_token, client):
    r = client.get("/api/hermes/health/../admin")
    # Either the app rejects it (403) or the client normalises the dot-segments
    # away before sending; in neither case may "/admin" be proxied through.
    assert r.status_code in (403, 404)


# --------------------------------------------------------------------------- #
# /api/summon                                                                  #
# --------------------------------------------------------------------------- #
def test_summon_requires_token_when_configured(with_token, client):
    r = client.post("/api/summon", json={"media": "iframe", "src": "http://x", "title": "t"})
    assert r.status_code == 401


def test_summon_no_clients_reports_zero(no_token, client):
    r = client.post("/api/summon", json={"media": "iframe", "src": "http://x", "title": "t"})
    assert r.status_code == 200
    assert r.json() == {"sent_to": 0}


# --------------------------------------------------------------------------- #
# Dashboard TLS reverse-proxy auth gate                                        #
# --------------------------------------------------------------------------- #
def test_dashboard_proxy_401_without_token(with_token, dash_client):
    r = dash_client.get("/", follow_redirects=False)
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Static HUD                                                                   #
# --------------------------------------------------------------------------- #
def test_root_redirects_to_hud(no_token, client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/hud/"
