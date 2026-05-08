"""Daily IDX disclosure briefing bot.

Three modes via state file (data/briefing_state.json):
  off          - cron skips entirely
  header_only  - classify by title, send list, $0/day (no LLM, no PDF)
  full         - PDF parse + Haiku summary for priority categories

Public API used by app.py:
  get_state()      -> dict
  set_mode(mode)   -> dict
  run_briefing()   -> dict (manual trigger or cron)
"""
from backend.briefing.intraday import register_intraday_cron
from backend.briefing.orchestrator import run_briefing
from backend.briefing.state import get_state, set_intraday_enabled, set_mode

__all__ = ["get_state", "set_mode", "run_briefing", "set_intraday_enabled", "register_intraday_cron"]
