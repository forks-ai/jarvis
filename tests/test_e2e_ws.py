"""End-to-end WebSocket protocol tests.

Drives the real ``/ws`` endpoint (accept, event dispatch, barge-in cancel,
per-turn task lifecycle) with a lightweight fake pipeline swapped in for the
GPU/cloud-bound one, so a full turn (start -> audio -> stop -> transcript ->
agent_status -> audio -> done) can be exercised deterministically and offline.
"""

from __future__ import annotations

import contextlib

import pytest


class FakePipeline:
    """Implements exactly the surface that _run_turn / websocket_endpoint call."""

    def __init__(self):
        self._n = 0
        self.hermes = self  # stop_run lives here

    def next_turn_id(self) -> int:
        self._n += 1
        return self._n

    async def transcribe(self, audio, timing=None) -> str:
        if timing is not None:
            import time
            timing.stt_final_monotonic = time.perf_counter()
        return "confirmed"

    async def stream_response_audio(self, ws, transcript, timing, conn) -> None:
        await ws.send_json({"type": "agent_status", "state": "thinking"})
        await ws.send_json({"type": "agent_status", "state": "speaking"})
        await ws.send_bytes(b"\x11\x11\x22\x22")  # fake 16-bit PCM
        timing.response_text = f"echo:{transcript}"

    def log_turn(self, timing) -> None:
        return None

    def stop_run(self, run_id):  # hermes.stop_run
        return {"status_code": 200, "body": "ok"}


@pytest.fixture()
def fake_pipeline_client(no_token, server_mod, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server_mod, "get_pipeline", lambda: FakePipeline())
    return TestClient(server_mod.app)


@contextlib.contextmanager
def ws_session(client, **kwargs):
    cm = client.websocket_connect("/ws", **kwargs)
    ws = cm.__enter__()
    try:
        yield ws
    finally:
        with contextlib.suppress(RuntimeError):
            cm.__exit__(None, None, None)


def _drain(ws, want_type, max_msgs=40):
    """Pull messages (json or binary) until a json event of `want_type`."""
    events, audio_frames = [], 0
    for _ in range(max_msgs):
        msg = ws.receive()
        if msg.get("bytes") is not None:
            audio_frames += 1
            continue
        if msg.get("text") is None:
            break
        import json
        ev = json.loads(msg["text"])
        events.append(ev)
        if ev.get("type") == want_type:
            break
    return events, audio_frames


def test_full_turn_happy_path(fake_pipeline_client):
    with ws_session(fake_pipeline_client) as ws:
        assert ws.receive_json()["type"] == "status"  # connected banner
        ws.send_json({"type": "start", "sample_rate": 16000,
                      "format": "pcm_s16le", "channels": 1})
        assert ws.receive_json()["message"].startswith("Turn 1 recording")
        ws.send_bytes(b"\x00\x01" * 1600)  # ~0.1s of audio while recording
        ws.send_json({"type": "stop"})

        events, audio = _drain(ws, "done")
        types = [e["type"] for e in events]
        assert "transcript" in types
        assert "done" in types
        assert audio >= 1  # TTS audio bytes were streamed
        transcript = next(e for e in events if e["type"] == "transcript")
        assert transcript["text"] == "confirmed"
        done = next(e for e in events if e["type"] == "done")
        assert done["turn_id"] == 1
        assert "timing" in done


def test_stop_before_start_is_rejected(fake_pipeline_client):
    with ws_session(fake_pipeline_client) as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "stop"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "stop before start" in err["message"]


def test_unknown_event_type_errors(fake_pipeline_client):
    with ws_session(fake_pipeline_client) as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "nonsense"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "Unknown event type" in err["message"]


def test_approval_without_run_errors(fake_pipeline_client):
    with ws_session(fake_pipeline_client) as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "approval_decision", "decision": "allow"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "No run for approval" in err["message"]
