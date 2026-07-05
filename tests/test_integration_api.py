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
# /api/say — proactive speech                                                  #
# --------------------------------------------------------------------------- #
def test_say_requires_token_when_configured(with_token, client):
    r = client.post("/api/say", json={"text": "hello"})
    assert r.status_code == 401


def test_say_rejects_empty_text(no_token, client):
    r = client.post("/api/say", json={"text": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "empty text"


def test_say_rejects_too_long_text(no_token, client):
    r = client.post("/api/say", json={"text": "x" * 1300})
    assert r.status_code == 400


def test_say_no_clients_not_spoken(no_token, client):
    # No HUD connected -> Jarvis does not synthesize (no TTS spend), reports so.
    r = client.post("/api/say", json={"text": "nobody home"})
    assert r.status_code == 200
    j = r.json()
    assert j["spoke"] is False
    assert j["sent_to"] == 0


def test_notify_alias_reaches_same_handler(no_token, client):
    r = client.post("/api/notify", json={"text": "  "})
    assert r.status_code == 400  # same empty-text validation as /api/say


# --------------------------------------------------------------------------- #
# Rich data panels via /api/summon (kind = chart/glance)                       #
# --------------------------------------------------------------------------- #
class _FakeHud:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


def test_summon_chart_broadcasts_data(no_token, server_mod, client):
    hud = _FakeHud()
    server_mod.WS_CLIENTS.add(hud)
    try:
        r = client.post("/api/summon", json={"kind": "chart", "title": "T", "data": [1, 2, 3]})
    finally:
        server_mod.WS_CLIENTS.discard(hud)
    assert r.json()["sent_to"] == 1
    p = hud.sent[0]
    assert p["type"] == "summon_panel" and p["kind"] == "chart" and p["data"] == [1, 2, 3]


def test_summon_glance_broadcasts_items(no_token, server_mod, client):
    hud = _FakeHud()
    server_mod.WS_CLIENTS.add(hud)
    try:
        r = client.post("/api/summon", json={
            "kind": "glance", "title": "WX", "items": [{"label": "Temp", "value": "21C"}]})
    finally:
        server_mod.WS_CLIENTS.discard(hud)
    assert r.json()["sent_to"] == 1
    assert hud.sent[0]["items"] == [{"label": "Temp", "value": "21C"}]


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
