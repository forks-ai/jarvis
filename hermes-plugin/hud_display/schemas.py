"""Tool schemas for the Jarvis HUD display plugin.

The description is what makes the agent USE the tool — keep it forceful.
Lesson learned: prose in SOUL.md cannot out-compete an attractive tool schema
(the model kept opening pages in its own invisible browser); a real tool with
an explicit description wins immediately.
"""

HUD_DISPLAY = {
    "name": "hud_display",
    "description": (
        "Display a video, webpage, or image ON THE USER'S SCREEN as a "
        "holographic panel on their Jarvis HUD. ALWAYS use this when the user "
        "asks to show, display, pull up, open, or put any media or webpage "
        "'on screen' or 'on my screen'. This is the ONLY way to show them "
        "visual content - browser tools open pages invisibly and do NOT show "
        "the user anything. YouTube watch/short URLs embed automatically as "
        "playable video. Special URLs: the Hermes kanban board is at "
        "https://YOUR_HOST:9443/kanban and the Hermes dashboard at "
        "https://YOUR_HOST:9443/ (use media=iframe)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "media": {
                "type": "string",
                "enum": ["video", "iframe", "image"],
                "description": "video = YouTube or direct video URL; iframe = any webpage; image = image URL",
            },
            "src": {"type": "string", "description": "Full URL of the video, page, or image"},
            "title": {"type": "string", "description": "Short panel title, e.g. 'ARC REACTOR EXPLAINED'"},
            "position": {
                "type": "string",
                "enum": ["center", "left", "right"],
                "description": "center for one large panel; left/right for smaller side panels when showing multiple things",
            },
        },
        "required": ["media", "src", "title"],
    },
}

HUD_DISMISS = {
    "name": "hud_dismiss",
    "description": "Dismiss all holographic media panels from the user's Jarvis HUD screen. Use when they say to close, clear, or dismiss what's on screen.",
    "parameters": {"type": "object", "properties": {}},
}

HUD_CHART = {
    "name": "hud_chart",
    "description": (
        "Display a DATA CHART (bar or line) as a holographic panel on the user's "
        "Jarvis HUD. Use when showing numbers, trends, comparisons, metrics, or "
        "any tabular series 'on screen' — e.g. 'chart my daily token usage', "
        "'show CPU over the last hour'. Renders inline (no external site). Pass "
        "`data` as a list of numbers, or a list of {label, value} objects for "
        "labelled bars."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Panel title, e.g. 'TOKENS / DAY'"},
            "data": {
                "type": "array",
                "items": {},
                "description": "List of numbers, or list of {label, value} objects",
            },
            "chart_type": {"type": "string", "enum": ["bar", "line"], "description": "bar (default) or line"},
            "position": {"type": "string", "enum": ["center", "left", "right"]},
        },
        "required": ["title", "data"],
    },
}

HUD_GLANCE = {
    "name": "hud_glance",
    "description": (
        "Display a compact KEY/VALUE STATUS BOARD as a holographic panel on the "
        "user's Jarvis HUD — weather, calendar, a systems/mission-control glance, "
        "or any set of labelled readings. Use when the user asks to 'show' status/"
        "conditions/agenda on screen. Pass `items` as a list of {label, value}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Panel title, e.g. 'WEATHER' or 'SYSTEMS'"},
            "items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {label, value} rows",
            },
            "kind": {"type": "string", "enum": ["glance", "status"], "description": "visual style; default glance"},
            "position": {"type": "string", "enum": ["center", "left", "right"]},
        },
        "required": ["title", "items"],
    },
}

HUD_STATUS = {
    "name": "hud_status",
    "description": (
        "Show a LIVE mission-control / systems board on the user's Jarvis HUD — "
        "host and worker CPU/GPU/memory plus today's token usage, composed live "
        "from the server's own telemetry. Use when the user asks to 'show system "
        "status / diagnostics / how the machines are doing' on screen. No data "
        "needed; it self-populates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Panel title (default SYSTEMS)"},
            "position": {"type": "string", "enum": ["center", "left", "right"]},
        },
    },
}

JARVIS_SAY = {
    "name": "jarvis_say",
    "description": (
        "SPEAK ALOUD to the user through their Jarvis HUD speakers, UNPROMPTED. "
        "This is the ONLY way to make Jarvis talk when the user is NOT in a voice "
        "turn — use it to proactively notify, remind, alert, or report back (e.g. "
        "'the build finished', a reminder coming due, a background task completing). "
        "Keep it short and spoken-style (no markdown). Set priority='high' to "
        "interrupt any audio currently playing. Optionally attach a panel "
        "(panel_src as a full http(s) URL) to show media while speaking."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to say aloud (plain spoken prose, <= ~1200 chars)"},
            "priority": {
                "type": "string",
                "enum": ["normal", "high"],
                "description": "high interrupts current audio; normal queues after it",
            },
            "panel_src": {"type": "string", "description": "Optional full http(s) URL to show as a panel while speaking"},
            "panel_media": {"type": "string", "enum": ["video", "iframe", "image"], "description": "Panel media type (default iframe)"},
            "panel_title": {"type": "string", "description": "Optional panel title"},
        },
        "required": ["text"],
    },
}
