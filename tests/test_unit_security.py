"""Unit tests for the security-relevant pure helpers in server.py.

Covers:
  * _clean_for_tts secret-redaction filter (privacy: secrets never reach TTS)
  * _proxy_allowed  allow-list (SSRF / method / path-traversal containment)
  * _request_authed HTTP auth decision
  * _ws_allowed     WebSocket origin + token decision
  * _extract_complete_sentences (streaming correctness)
"""

from __future__ import annotations

import types

import pytest


# --------------------------------------------------------------------------- #
# Tiny request/ws doubles (avoid pulling real Starlette request machinery)     #
# --------------------------------------------------------------------------- #
class _Dict:
    def __init__(self, d=None):
        self._d = {k.lower(): v for k, v in (d or {}).items()}

    def get(self, k, default=None):
        return self._d.get(k.lower(), default)


def make_request(headers=None, cookies=None, path="/api/usage"):
    return types.SimpleNamespace(
        headers=_Dict(headers),
        cookies=_Dict(cookies),
        url=types.SimpleNamespace(path=path),
    )


def make_ws(headers=None, cookies=None, query=None):
    return types.SimpleNamespace(
        headers=_Dict(headers),
        cookies=_Dict(cookies),
        query_params=_Dict(query),
    )


# --------------------------------------------------------------------------- #
# _clean_for_tts — secret redaction                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "the api_key = sk-abcdef0123456789ABCDEF",
        "password: hunter2hunter2hunter2",
        "authorization = Bearer abcdefabcdefabcdef",
        "sk-1234567890abcdefghij",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----",
        "here is a token AKIAIOSFODNN7EXAMPLEEXAMPLEEXAMPLE1234",
    ],
)
def test_clean_for_tts_redacts_secrets(server_mod, text):
    out = server_mod.VoicePipelineServer._clean_for_tts(text)
    assert "redacted" in out
    # the secret material itself must not survive verbatim
    for tok in ("sk-abcdef0123456789ABCDEF", "hunter2hunter2hunter2",
                "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", "MIIabc"):
        assert tok not in out


def test_clean_for_tts_keeps_normal_speech(server_mod):
    out = server_mod.VoicePipelineServer._clean_for_tts("Turn the kettle on please.")
    assert out == "Turn the kettle on please."


def test_clean_for_tts_strips_code_and_markdown(server_mod):
    out = server_mod.VoicePipelineServer._clean_for_tts("Run ```rm -rf /``` now")
    assert "rm -rf" not in out
    assert "code omitted" in out


# --------------------------------------------------------------------------- #
# _proxy_allowed — Hermes proxy allow-list                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", sorted({
    "/health", "/health/detailed", "/v1/capabilities",
    "/v1/skills", "/v1/toolsets", "/api/jobs", "/api/sessions",
    "/api/sessions/abc/messages",
}))
def test_proxy_allows_known_get_paths(server_mod, path):
    assert server_mod._proxy_allowed("GET", path) is True


@pytest.mark.parametrize("path", [
    "/v1/responses",                      # only POST is whitelisted
    "/admin",
    "/api/sessions/abc/delete",
    "/api/sessions/../secrets",
    "/health/../admin",
    "/",
])
def test_proxy_blocks_unknown_get_paths(server_mod, path):
    assert server_mod._proxy_allowed("GET", path) is False


# --------------------------------------------------------------------------- #
# _panel_payload — panel spec normalisation / clamping                         #
# --------------------------------------------------------------------------- #
def test_panel_payload_media_defaults(server_mod):
    out = server_mod._panel_payload({"media": "image", "src": "http://x", "title": "t", "position": "left"})
    assert out["media"] == "image" and out["position"] == "left"
    assert "kind" not in out


def test_panel_payload_clamps_bad_media_and_position(server_mod):
    out = server_mod._panel_payload({"media": "evil", "position": "up", "title": "x"})
    assert out["media"] == "iframe" and out["position"] == "center"


def test_panel_payload_chart_passthrough_and_bounds(server_mod):
    out = server_mod._panel_payload({"kind": "chart", "title": "T",
                                     "data": list(range(100)), "chart_type": "line"})
    assert out["kind"] == "chart" and out["chart_type"] == "line"
    assert len(out["data"]) == 60  # payload size bounded


def test_panel_payload_glance_items_bounded(server_mod):
    items = [{"label": str(i), "value": i} for i in range(50)]
    out = server_mod._panel_payload({"kind": "glance", "title": "S", "items": items})
    assert len(out["items"]) == 30


def test_panel_payload_rejects_unknown_kind(server_mod):
    out = server_mod._panel_payload({"kind": "evil", "title": "T"})
    assert "kind" not in out


def test_panel_payload_status_live_flag(server_mod):
    assert server_mod._panel_payload({"kind": "status", "title": "S", "live": True}).get("live") is True
    # live is a status-only affordance
    assert "live" not in server_mod._panel_payload({"kind": "glance", "title": "S", "live": True})


# --------------------------------------------------------------------------- #
# _rate_ok — proactive-speech sliding-window limiter                            #
# --------------------------------------------------------------------------- #
def test_rate_ok_disabled_when_zero(server_mod):
    server_mod._SAY_TIMES.clear()
    assert server_mod._rate_ok(0, 100.0) is True
    assert server_mod._rate_ok(-5, 100.0) is True


def test_rate_ok_enforces_window(server_mod):
    server_mod._SAY_TIMES.clear()
    assert server_mod._rate_ok(2, 100.0) is True
    assert server_mod._rate_ok(2, 100.5) is True
    assert server_mod._rate_ok(2, 101.0) is False   # 3rd within the 60s window
    assert server_mod._rate_ok(2, 200.0) is True     # window has slid past
    server_mod._SAY_TIMES.clear()


# --------------------------------------------------------------------------- #
# _frame_ancestors_csp — dashboard proxy anti-clickjacking (F4)                #
# --------------------------------------------------------------------------- #
def test_frame_ancestors_scopes_to_hud_origins(server_mod):
    csp = server_mod._frame_ancestors_csp()
    assert csp.startswith("frame-ancestors 'self'")
    assert "https://jarvis.local" in csp
    assert "*" not in csp


# --------------------------------------------------------------------------- #
# _security_startup_check — fail-closed / warn (F3)                            #
# --------------------------------------------------------------------------- #
def test_startup_check_require_token_raises(no_token, server_mod, monkeypatch):
    monkeypatch.setitem(server_mod.CFG, "security",
                        {"require_token": True, "hud_token_env": "JARVIS_HUD_TOKEN"})
    with pytest.raises(SystemExit):
        server_mod._security_startup_check("0.0.0.0")


def test_startup_check_warns_but_starts(no_token, server_mod, monkeypatch, capsys):
    monkeypatch.setitem(server_mod.CFG, "security", {"require_token": False})
    assert server_mod._security_startup_check("0.0.0.0") is None
    assert "SECURITY WARNING" in capsys.readouterr().out


def test_startup_check_silent_on_loopback(no_token, server_mod, monkeypatch):
    monkeypatch.setitem(server_mod.CFG, "security", {"require_token": False})
    assert server_mod._security_startup_check("127.0.0.1") is None


def test_startup_check_silent_with_token(with_token, server_mod, monkeypatch):
    monkeypatch.setitem(server_mod.CFG, "security", {"require_token": True})
    assert server_mod._security_startup_check("0.0.0.0") is None  # token present -> fine


# --------------------------------------------------------------------------- #
# get_tts_pipeline — TTS-only path (no STT recorder)                            #
# --------------------------------------------------------------------------- #
def test_tts_pipeline_has_no_recorder(server_mod):
    saved_p, saved_t = server_mod.PIPELINE, server_mod._TTS_PIPELINE
    server_mod.PIPELINE = None
    server_mod._TTS_PIPELINE = None
    try:
        p = server_mod.get_tts_pipeline()
        assert hasattr(p, "cfg")
        assert not hasattr(p, "recorder")  # decoupled from STT
    finally:
        server_mod.PIPELINE, server_mod._TTS_PIPELINE = saved_p, saved_t


# --------------------------------------------------------------------------- #
# _extract_complete_sentences — streaming correctness                          #
# --------------------------------------------------------------------------- #


def test_proxy_post_only_v1_responses(server_mod):
    assert server_mod._proxy_allowed("POST", "/v1/responses") is True
    assert server_mod._proxy_allowed("POST", "/api/sessions") is False
    assert server_mod._proxy_allowed("POST", "/v1/responses/../admin") is False


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
def test_proxy_blocks_other_methods(server_mod, method):
    assert server_mod._proxy_allowed(method, "/health") is False


# --------------------------------------------------------------------------- #
# _request_authed — HTTP token gate                                            #
# --------------------------------------------------------------------------- #
def test_request_authed_open_when_no_token(no_token):
    assert no_token._request_authed(make_request()) is True


def test_request_authed_requires_matching_header(with_token):
    assert with_token._request_authed(make_request()) is False
    ok = make_request(headers={"x-jarvis-token": "s3cr3t-token"})
    assert with_token._request_authed(ok) is True


def test_request_authed_accepts_cookie(with_token):
    ok = make_request(cookies={"jarvis_token": "s3cr3t-token"})
    assert with_token._request_authed(ok) is True
    bad = make_request(cookies={"jarvis_token": "wrong"})
    assert with_token._request_authed(bad) is False


# --------------------------------------------------------------------------- #
# _ws_allowed — WebSocket origin + token gate                                  #
# --------------------------------------------------------------------------- #
def test_ws_originless_requires_token_when_set(with_token):
    # F2 fix: native (Origin-less) clients must supply the token when one is set.
    assert with_token._ws_allowed(make_ws()) is False
    assert with_token._ws_allowed(make_ws(query={"token": "s3cr3t-token"})) is True
    assert with_token._ws_allowed(make_ws(cookies={"jarvis_token": "s3cr3t-token"})) is True


def test_ws_originless_open_when_no_token(no_token):
    assert no_token._ws_allowed(make_ws()) is True


def test_ws_browser_origin_must_be_allowlisted(with_token):
    evil = make_ws(headers={"origin": "https://evil.example.com"})
    assert with_token._ws_allowed(evil) is False


def test_ws_browser_allowed_origin_needs_token(with_token):
    no_tok = make_ws(headers={"origin": "https://jarvis.local"})
    assert with_token._ws_allowed(no_tok) is False
    good = make_ws(headers={"origin": "https://jarvis.local"},
                   cookies={"jarvis_token": "s3cr3t-token"})
    assert with_token._ws_allowed(good) is True
    good_q = make_ws(headers={"origin": "https://jarvis.local"},
                     query={"token": "s3cr3t-token"})
    assert with_token._ws_allowed(good_q) is True


# --------------------------------------------------------------------------- #
# _ack_config — "agent is slow" spoken filler wiring                           #
# --------------------------------------------------------------------------- #
def _pipeline_with_cfg(server_mod, cfg):
    p = server_mod.VoicePipelineServer.__new__(server_mod.VoicePipelineServer)
    p.cfg = cfg
    return p


def test_ack_disabled_by_default(server_mod):
    assert _pipeline_with_cfg(server_mod, {"hermes": {}})._ack_config() == (0.0, None)


def test_ack_disabled_when_no_texts(server_mod):
    p = _pipeline_with_cfg(server_mod, {"hermes": {"ack_after_seconds": 6, "ack_texts": []}})
    assert p._ack_config() == (0.0, None)


def test_ack_enabled(server_mod):
    p = _pipeline_with_cfg(server_mod, {"hermes": {"ack_after_seconds": 6, "ack_texts": ["On it, sir."]}})
    assert p._ack_config() == (6.0, "On it, sir.")


def test_ack_filler_is_secret_redacted(server_mod):
    # ack text flows through _clean_for_tts, so a secret in it is still redacted.
    p = _pipeline_with_cfg(server_mod, {"hermes": {"ack_after_seconds": 3,
                                                   "ack_texts": ["key sk-abcdefabcdefabcdef123"]}})
    _, text = p._ack_config()
    assert "redacted" in text


# --------------------------------------------------------------------------- #
# _extract_complete_sentences — streaming correctness                          #
# --------------------------------------------------------------------------- #
def test_extract_complete_sentences(server_mod):
    sents, rest = server_mod.VoicePipelineServer._extract_complete_sentences(
        "Hello there. How are you? I am fine"
    )
    assert sents == ["Hello there.", "How are you?"]
    assert rest.strip() == "I am fine"
