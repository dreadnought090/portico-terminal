"""Briefing bot runtime state — persisted to JSON file."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

VALID_MODES = {"off", "header_only", "full"}
STATE_PATH = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "briefing_state.json"


def _default_state() -> dict:
    return {
        "mode": "off",
        "last_run_at": None,
        "last_run_status": None,
        "last_run_messages_sent": 0,
        "last_run_cost_usd": 0.0,
        "last_run_error": None,
        # intraday alerts (separate toggle from daily mode)
        "intraday_enabled": False,
        "last_intraday_at": None,
        "intraday_seen_ids": [],
    }


def get_state() -> dict:
    if not STATE_PATH.exists():
        return _default_state()
    try:
        return {**_default_state(), **json.loads(STATE_PATH.read_text())}
    except Exception:
        return _default_state()


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def set_mode(mode: str) -> dict:
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; choose from {sorted(VALID_MODES)}")
    state = get_state()
    state["mode"] = mode
    _write_state(state)
    return state


def update_last_run(*, status: str, messages_sent: int = 0, cost_usd: float = 0.0, error: str | None = None) -> None:
    state = get_state()
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    state["last_run_status"] = status
    state["last_run_messages_sent"] = messages_sent
    state["last_run_cost_usd"] = cost_usd
    state["last_run_error"] = error
    _write_state(state)


def set_intraday_enabled(enabled: bool) -> dict:
    state = get_state()
    state["intraday_enabled"] = bool(enabled)
    _write_state(state)
    return state


def set_intraday_state(*, last_at: str | None = None, seen_ids: list[str] | None = None) -> None:
    state = get_state()
    if last_at is not None:
        state["last_intraday_at"] = last_at
    if seen_ids is not None:
        state["intraday_seen_ids"] = seen_ids
    _write_state(state)
