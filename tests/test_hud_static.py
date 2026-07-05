"""Static assertions over the HUD (server/hud/index.html): earcon sound cues
are defined and wired to the right events. Pure text checks — no browser."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = (REPO_ROOT / "server" / "hud" / "index.html").read_text(encoding="utf-8")


def test_earcon_defined():
    assert "function earcon(" in INDEX_HTML
    assert "const EARCONS=" in INDEX_HTML
    # WebAudio-only (no external asset fetch)
    assert "createOscillator" in INDEX_HTML


def test_earcon_wired_to_events():
    assert 'earcon("listen")' in INDEX_HTML   # start talking
    assert 'earcon("alert")' in INDEX_HTML     # approval required
    assert 'earcon("error")' in INDEX_HTML     # error event
    assert 'earcon("chime")' in INDEX_HTML     # proactive speech incoming


def test_earcon_gated_on_running_context():
    # Must not throw / must stay silent until the audio context is unlocked.
    assert 'audioCtx.state!=="running"' in INDEX_HTML


def test_audio_nudge_present_and_wired():
    assert "function audioNudge(" in INDEX_HTML
    assert "audioNudge()" in INDEX_HTML                # called from speak_start
    assert "Click anywhere to enable" in INDEX_HTML


def test_live_status_panel_present_and_composes_endpoints():
    assert "function fillLiveStatus(" in INDEX_HTML
    assert "/api/machines" in INDEX_HTML and "/api/usage" in INDEX_HTML
    assert 'data-live="1"' in INDEX_HTML              # live placeholder marker
    # values are escaped before innerHTML
    assert "escHtml(String(r.value" in INDEX_HTML
