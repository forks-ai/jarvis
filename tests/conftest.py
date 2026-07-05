"""Shared pytest fixtures + heavy-dependency stubs for the Jarvis test suite.

The voice server imports several heavyweight, hardware-bound packages
(``RealtimeSTT`` pulls in Whisper/torch, ``anthropic`` the cloud SDK, ``uvicorn``
the ASGI runner). None of them are needed to exercise the HTTP/WebSocket surface
or the pure security-relevant helpers, so we install lightweight stand-ins into
``sys.modules`` *before* importing ``server.py``. This keeps the tests fast,
deterministic and runnable on a machine with no GPU and no cloud keys.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = REPO_ROOT / "server" / "server.py"


# --------------------------------------------------------------------------- #
# Stub the heavy imports before loading server.py                              #
# --------------------------------------------------------------------------- #
def _install_stubs() -> None:
    if "RealtimeSTT" not in sys.modules:
        rt = types.ModuleType("RealtimeSTT")

        class _Recorder:  # minimal stand-in for AudioToTextRecorder
            def __init__(self, *a, **k):
                self._args = a
                self._kwargs = k

            def feed_audio(self, *a, **k):
                return None

            def perform_final_transcription(self, *a, **k):
                return ""

            def clear_audio_queue(self, *a, **k):
                return None

        rt.AudioToTextRecorder = _Recorder
        sys.modules["RealtimeSTT"] = rt

    if "anthropic" not in sys.modules:
        an = types.ModuleType("anthropic")

        class _Anthropic:
            def __init__(self, *a, **k):
                pass

        an.Anthropic = _Anthropic
        sys.modules["anthropic"] = an

    if "uvicorn" not in sys.modules:
        uv = types.ModuleType("uvicorn")
        uv.Server = object
        uv.Config = object
        uv.run = lambda *a, **k: None
        sys.modules["uvicorn"] = uv


@pytest.fixture(scope="session")
def server_mod():
    """Import server.py exactly once with heavy deps stubbed out."""
    _install_stubs()
    spec = importlib.util.spec_from_file_location("jarvis_server", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jarvis_server"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture()
def no_token(monkeypatch, server_mod):
    """Default deployment posture: JARVIS_HUD_TOKEN unset -> auth disabled."""
    monkeypatch.delenv("JARVIS_HUD_TOKEN", raising=False)
    return server_mod


@pytest.fixture()
def with_token(monkeypatch, server_mod):
    """Hardened posture: a HUD token is configured."""
    monkeypatch.setenv("JARVIS_HUD_TOKEN", "s3cr3t-token")
    return server_mod


@pytest.fixture()
def client(server_mod):
    """TestClient for the main voice/HUD app (no lifespan -> no STT warm)."""
    from fastapi.testclient import TestClient

    return TestClient(server_mod.app)


@pytest.fixture()
def dash_client(server_mod):
    """TestClient for the dashboard TLS reverse-proxy app."""
    from fastapi.testclient import TestClient

    return TestClient(server_mod.dash_app)
