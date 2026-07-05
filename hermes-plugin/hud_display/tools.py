"""Handlers: POST to the Jarvis voice server's /api/summon + /api/say broadcasts."""
import json
import os
import urllib.request

# Plain-HTTP loopback port of the voice server (no TLS dance needed locally).
SUMMON_URL = os.environ.get("JARVIS_SUMMON_URL", "http://127.0.0.1:8765/api/summon")
SAY_URL = os.environ.get("JARVIS_SAY_URL", "http://127.0.0.1:8765/api/say")


def _post_to(url: str, payload: dict) -> dict:
    token = os.environ.get("JARVIS_HUD_TOKEN", "")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Jarvis-Token": token},
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def _post(payload: dict) -> str:
    try:
        res = _post_to(SUMMON_URL, payload)
    except Exception as e:
        return json.dumps({"error": f"HUD unreachable: {e}"})
    sent = res.get("sent_to", 0)
    if sent == 0:
        return json.dumps({"warning": "No HUD screens are currently open; nothing was displayed."})
    return json.dumps({"ok": True, "displayed_on_screens": sent,
                       **{k: payload.get(k) for k in ("title", "media") if k in payload}})


def hud_display(args: dict, **kwargs) -> str:
    src = (args.get("src") or "").strip()
    if not src.startswith(("http://", "https://")):
        return json.dumps({"error": "src must be a full http(s) URL"})
    return _post({
        "media": args.get("media", "iframe"),
        "src": src,
        "title": (args.get("title") or "INCOMING FEED")[:48],
        "position": args.get("position", "center"),
    })


def hud_dismiss(args: dict, **kwargs) -> str:
    return _post({"action": "dismiss"})


def hud_chart(args: dict, **kwargs) -> str:
    """Show a live data chart (bar/line) as a holographic panel."""
    data = args.get("data")
    if not isinstance(data, list) or not data:
        return json.dumps({"error": "data must be a non-empty list of numbers or {label,value} objects"})
    return _post({
        "kind": "chart",
        "title": (args.get("title") or "DATA")[:48],
        "data": data,
        "chart_type": args.get("chart_type") if args.get("chart_type") in ("bar", "line") else "bar",
        "position": args.get("position", "center"),
    })


def hud_glance(args: dict, **kwargs) -> str:
    """Show a compact key/value status board (weather, calendar, systems...)."""
    items = args.get("items")
    if not isinstance(items, list) or not items:
        return json.dumps({"error": "items must be a non-empty list of {label,value} objects"})
    kind = args.get("kind") if args.get("kind") in ("glance", "status") else "glance"
    return _post({
        "kind": kind,
        "title": (args.get("title") or "STATUS")[:48],
        "items": items,
        "position": args.get("position", "center"),
    })


def hud_status(args: dict, **kwargs) -> str:
    """Show a LIVE mission-control board (host/worker CPU-GPU + token usage)."""
    return _post({
        "kind": "status",
        "live": True,
        "title": (args.get("title") or "SYSTEMS")[:48],
        "position": args.get("position", "center"),
    })


def jarvis_say(args: dict, **kwargs) -> str:
    """Speak text aloud on the user's HUD, unprompted (out of a voice turn)."""
    text = (args.get("text") or "").strip()
    if not text:
        return json.dumps({"error": "text is required"})
    payload = {"text": text, "priority": "high" if args.get("priority") == "high" else "normal"}
    panel_src = (args.get("panel_src") or "").strip()
    if panel_src:
        if not panel_src.startswith(("http://", "https://")):
            return json.dumps({"error": "panel_src must be a full http(s) URL"})
        payload["panel"] = {
            "media": args.get("panel_media", "iframe"),
            "src": panel_src,
            "title": (args.get("panel_title") or "INCOMING FEED")[:48],
        }
    try:
        res = _post_to(SAY_URL, payload)
    except Exception as e:
        return json.dumps({"error": f"HUD unreachable: {e}"})
    if not res.get("spoke"):
        return json.dumps({"warning": res.get("warning") or res.get("reason") or "nothing spoken"})
    return json.dumps({"ok": True, "spoke": True, "on_screens": res.get("sent_to", 0)})
