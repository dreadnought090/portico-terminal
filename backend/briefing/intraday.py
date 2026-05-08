"""Intraday IDX disclosure alerts — header-only push every 5 min during market hours.

Schedule (Mon–Fri WIB):
  09:00      — catch-up: disclosures from 08:00 to 09:00 (post-daily-briefing gap)
  09:05–15:55 every 5 min — incremental alerts since last poll
  16:00–16:15 — closing window (post-market disclosures)

State tracked in briefing_state.json:
  intraday_enabled: bool (admin toggle)
  last_intraday_at: ISO timestamp of last successful poll
  last_intraday_id: hash of last seen disclosure title+ticker (dedup)
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from backend.briefing import classifier, sender, state
from backend.briefing.classifier import CATEGORY_LABELS, PRIORITY_CATEGORIES
from backend.stock_service import fetch_idx_disclosure

logger = logging.getLogger("mybloomberg.intraday")

WIB = timezone(timedelta(hours=7))
FETCH_PAGE_SIZE = 200       # 200 covers ~24h on quiet days, ~6-12h on busy days
MAX_CATCHUP_HOURS = 12      # safety: never replay more than 12h on first poll


def _disclosure_id(d: dict) -> str:
    """Stable id for dedup — IDX feed doesn't expose its own id consistently."""
    raw = f"{d.get('ticker','')}|{d.get('title','')}|{d.get('date','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _format_intraday_batch(items: list[dict], window_label: str) -> list[str]:
    """Compact intraday format: one line per category, tickers inline.

    Example output:
        🔔 IDX Live · 6 baru @ 11:05
        📊 LK · [BMAS](url) 17:39 · [ULTJ](url) 17:38 · [TALF](url) 17:35
        💰 Dividen · [TLKM](url) 09:14
    """
    if not items:
        return []
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        key, prio = classifier.classify(it.get("title", ""))
        if prio == "skip":
            continue
        if key not in PRIORITY_CATEGORIES:
            continue
        by_cat.setdefault(key, []).append(it)
    if not by_cat:
        return []

    total = sum(len(v) for v in by_cat.values())
    # window_label is "5min @ HH:MM WIB" — strip prefix/suffix for header
    time_label = window_label.replace("5min @ ", "").replace(" WIB", "").strip()
    lines = [f"🔔 *IDX Live · {total} baru @ {time_label}*"]

    for cat_key, cat_items in by_cat.items():
        emoji, label = CATEGORY_LABELS.get(cat_key, ("📄", cat_key))
        parts = []
        for it in cat_items:
            ticker = it.get("ticker") or "?"
            link = it.get("link") or ""
            t = it.get("date", "")
            wib_time = "—"
            try:
                ts = datetime.fromisoformat(t.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=WIB)
                wib_time = ts.astimezone(WIB).strftime("%H:%M")
            except Exception:
                pass
            ticker_md = f"[{ticker}]({link})" if link else ticker
            parts.append(f"{ticker_md} {wib_time}")
        lines.append(f"{emoji} {label} · " + " · ".join(parts))
    return ["\n".join(lines)]


async def _poll_window(window_start: datetime, window_label: str) -> dict:
    """Fetch disclosures since `window_start`, filter, batch-send."""
    s = state.get_state()
    if not s.get("intraday_enabled", False):
        return {"status": "disabled", "sent": 0}

    raw = await fetch_idx_disclosure(ticker="", page=0, page_size=FETCH_PAGE_SIZE, include_nonstock=False)
    seen_ids = set(s.get("intraday_seen_ids", []) or [])
    new_items: list[dict] = []
    for d in raw:
        try:
            ts = datetime.fromisoformat((d.get("date") or "").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                # IDX TglPengumuman is naive ISO but values are WIB local.
                ts = ts.replace(tzinfo=WIB)
        except Exception:
            continue
        if ts < window_start:
            continue
        did = _disclosure_id(d)
        if did in seen_ids:
            continue
        new_items.append(d)
        seen_ids.add(did)

    if not new_items:
        # Update last_intraday_at even on empty poll so window advances
        state.set_intraday_state(last_at=datetime.now(timezone.utc).isoformat(), seen_ids=list(seen_ids)[-500:])
        return {"status": "ok", "sent": 0, "new": 0}

    messages = _format_intraday_batch(new_items, window_label)
    if not messages:
        # Items existed but all noise (non-priority) — still update state
        state.set_intraday_state(last_at=datetime.now(timezone.utc).isoformat(), seen_ids=list(seen_ids)[-500:])
        return {"status": "ok", "sent": 0, "new": len(new_items), "filtered_out": len(new_items)}

    sent = 0
    try:
        sent = sender.send_messages(messages, with_disclaimer=False)
    except Exception:
        logger.exception("intraday send failed")

    # Cap seen_ids growth (keep last 500 to avoid unbounded state)
    state.set_intraday_state(last_at=datetime.now(timezone.utc).isoformat(), seen_ids=list(seen_ids)[-500:])
    return {"status": "ok", "sent": sent, "new": len(new_items), "messages": len(messages)}


async def intraday_catchup_0900() -> dict:
    """09:00 WIB cron — catches anything posted between 08:00 and 09:00 WIB."""
    now_wib = datetime.now(WIB)
    eight_am = now_wib.replace(hour=8, minute=0, second=0, microsecond=0)
    return await _poll_window(eight_am.astimezone(timezone.utc), window_label="08:00–09:00 catch-up")


async def intraday_poll() -> dict:
    """Every-5-min cron during market hours."""
    s = state.get_state()
    last_at_str = s.get("last_intraday_at")
    if last_at_str:
        try:
            last_at = datetime.fromisoformat(last_at_str)
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
        except Exception:
            last_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    else:
        # First-ever poll: look back 10 min, but cap at MAX_CATCHUP_HOURS
        last_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    # Safety: never replay >12h
    cap = datetime.now(timezone.utc) - timedelta(hours=MAX_CATCHUP_HOURS)
    if last_at < cap:
        last_at = cap

    # Pretty label for the message
    now_wib = datetime.now(WIB)
    label = f"5min @ {now_wib.strftime('%H:%M')} WIB"
    return await _poll_window(last_at, window_label=label)


def register_intraday_cron(scheduler) -> None:
    """Wire intraday cron jobs. Mon-Fri WIB only.

    Starts at 08:05 (5 min after the daily 08:00 batch) so disclosures filed
    in the 08:00–09:00 window get caught quickly. The daily batch sets
    last_intraday_at = its run time, so this 08:05 poll won't re-send anything
    already in the batch.
    """
    # 08:05–15:55 every 5 min
    scheduler.add_job(
        intraday_poll, "cron",
        hour="8-15", minute="5,10,15,20,25,30,35,40,45,50,55",
        day_of_week="mon-fri",
        id="intraday_5min_main",
    )
    # 16:00–16:15 closing window (catches post-close institutional filings)
    scheduler.add_job(
        intraday_poll, "cron",
        hour=16, minute="0,5,10,15",
        day_of_week="mon-fri",
        id="intraday_5min_close",
    )
