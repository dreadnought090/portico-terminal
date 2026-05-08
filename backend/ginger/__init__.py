"""Ginger — conversational assistant bot for Portico.

Persona: witch/sage Caerleon, friend Merriot. Calm, knowledgeable,
warm-but-practical. Uses light mystical metaphors (scry/divine/conjure)
without overdoing it. Indonesian casual register, NO lu/gw.

v1: Read-only — query portfolio, thesis, alerts, holdings via Claude
function calling. Env-gated (GINGER_BOT_TOKEN). Graceful no-op if not set.
"""
from backend.ginger.bot import start_bot, stop_bot

__all__ = ["start_bot", "stop_bot"]
