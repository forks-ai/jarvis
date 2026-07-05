# Jarvis test suite

Fast, offline tests for the voice/HUD server. Heavy runtime deps
(RealtimeSTT/whisper, anthropic, uvicorn) are **stubbed** in
[`conftest.py`](conftest.py), so the suite needs no GPU, no cloud keys, and
never touches the network.

## Run

```bash
python3 -m venv .venv && . .venv/bin/activate     # or use the repo .venv
pip3 install -r tests/requirements-test.txt
pytest                                            # from the repo root
```

The suite loads `server/config/server.yaml` (the same file the server loads).
It is git-ignored; if you don't have one, copy the example first:

```bash
cp server/config/server.example.yaml server/config/server.yaml
```

## Layout

| File | Kind | What it covers |
|------|------|----------------|
| `test_unit_security.py`     | unit        | secret-redaction filter, proxy allow-list, HTTP/WS auth decision helpers, sentence splitting |
| `test_integration_api.py`   | integration | real FastAPI stack via TestClient: auth middleware, `/api/chat` validation, Hermes proxy allow-list, `/api/summon`, dashboard-proxy auth gate |
| `test_e2e_ws.py`            | e2e         | full `/ws` turn protocol (start → audio → stop → transcript → agent_status → audio → done) with a fake pipeline |
| `test_security_exploits.py` | security PoC | **executable proof** of the audit findings (HUD XSS, WS token bypass, default-open posture) |
| `test_backdoor_scan.py`     | security    | static scan: no code-exec sinks, argv-list subprocess, no unexpected outbound hosts |

## Notes on the PoC tests

`test_security_exploits.py` is written to **pass against the current
(vulnerable) code** so it documents real behaviour. Each finding has an inline
`FIX:` note — after remediation, flip the relevant assertion so the test becomes
a regression guard. See [`docs/SECURITY_REVIEW.md`](../docs/SECURITY_REVIEW.md)
for the full write-up.
