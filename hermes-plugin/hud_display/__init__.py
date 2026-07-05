"""Jarvis HUD display plugin - registration."""
from . import schemas, tools


def register(ctx):
    ctx.register_tool(name="hud_display", toolset="hud",
                      schema=schemas.HUD_DISPLAY, handler=tools.hud_display)
    ctx.register_tool(name="hud_dismiss", toolset="hud",
                      schema=schemas.HUD_DISMISS, handler=tools.hud_dismiss)
    ctx.register_tool(name="jarvis_say", toolset="hud",
                      schema=schemas.JARVIS_SAY, handler=tools.jarvis_say)
    ctx.register_tool(name="hud_chart", toolset="hud",
                      schema=schemas.HUD_CHART, handler=tools.hud_chart)
    ctx.register_tool(name="hud_glance", toolset="hud",
                      schema=schemas.HUD_GLANCE, handler=tools.hud_glance)
