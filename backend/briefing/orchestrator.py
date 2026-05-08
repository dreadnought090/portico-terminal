"""Top-level briefing pipeline: fetch → classify → (extract+summarize) → format → send."""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone

from backend.briefing import classifier, extractor, formatter, sender, state, summarizer
from backend.stock_service import fetch_idx_disclosure, fetch_stock_data

# LK titles that indicate "no actual financial data in this disclosure":
#   - "rencana penyampaian"        — bot notification, nothing filed yet
#   - "informasi LK Tahunan"        — bukti iklan (press-release announcement)
#   - "penyampaian bukti iklan LK"  — ad-submission notice
# We short-circuit these before hitting the LLM. Saves ~30-50% LK cost.
_RENCANA_PATTERN = re.compile(
    r"\b(rencana penyampaian|akan menyampaikan|akan dipublikasikan"
    r"|informasi\s+(?:lk|laporan keuangan)"
    r"|bukti iklan.*(?:lk|laporan keuangan))\b",
    re.IGNORECASE,
)

logger = logging.getLogger("mybloomberg.briefing")

FETCH_PAGE_SIZE = 2000      # pull 6-12 day window in one shot. IDX peaks at ~700/day
                            # (year-end / earnings season), so 2000 = headroom 3-12x.
                            # Cannot paginate-and-merge because IDX page boundaries skip days.
PAGE_SIZE_WARNING = 1500    # log warning if we approach the cap
WINDOW_HOURS = 24
MAX_RUN_COST_USD = 1.50     # hard ceiling per run. Earnings season (Apr/May) can hit
                            # ~$1.20 with 30+ LK items; $1.50 gives headroom + still
                            # safety brake against runaway. Adjust if peak runs cap out.


def _within_window(date_str: str, cutoff: datetime) -> bool:
    if not date_str:
        return False
    try:
        ts = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts >= cutoff
    except Exception:
        return False


async def _fetch_24h_disclosures() -> list[dict]:
    raw = await fetch_idx_disclosure(ticker="", page=0, page_size=FETCH_PAGE_SIZE, include_nonstock=False)
    if len(raw) >= PAGE_SIZE_WARNING:
        logger.warning(
            "fetched %d disclosures (cap=%d). If this nears the cap, oldest items may "
            "fall outside 24h window; bump FETCH_PAGE_SIZE.",
            len(raw), FETCH_PAGE_SIZE,
        )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    return [d for d in raw if _within_window(d.get("date", ""), cutoff)]


MULTI_ATTACHMENT_CATEGORIES = {"insider_trade", "dividen", "lap_keuangan"}
MAX_ATTACHMENTS_PER_ITEM = 3   # concat up to N attachments per item to stay within token budget


def _download_and_extract(item: dict, cat_key: str) -> str:
    """Download + extract disclosure body text.

    For some categories (insider, dividen, LK) IDX publishes the substantive
    content split across multiple attachments (form + supporting tables +
    signatories). Single-attachment fetch returns only the cover. We concat
    text from up to MAX_ATTACHMENTS_PER_ITEM attachments for those categories.

    Also handles .xlsx LK files via fetch_body_text (auto-routes by extension).

    Returns empty string on total failure. Sets item['_extract_status'].
    """
    ticker = item.get("ticker", "?")
    title = item.get("title", "")
    all_links = item.get("all_links") or ([item["link"]] if item.get("link") else [])
    if not all_links:
        item["_extract_status"] = "no_link"
        return ""

    # For LK, if .xlsx is present: use ONLY xlsx (skip PDF cover letters which
    # just add noise and eat the token budget). XBRL spreadsheets contain the
    # full financial statement with precise scale + currency metadata — PDFs
    # for LK are usually just cover letters or supplementary notes.
    if cat_key == "lap_keuangan":
        xlsx_links = [l for l in all_links if l.lower().endswith((".xlsx", ".xlsm", ".xls"))]
        if xlsx_links:
            all_links = xlsx_links  # xlsx-only: drop all PDF/other attachments

    # Single-attachment categories just fetch the primary link.
    if cat_key not in MULTI_ATTACHMENT_CATEGORIES:
        text = extractor.fetch_body_text(all_links[0], f"{ticker}_{cat_key}_{title[:30]}")
        if not text:
            item["_extract_status"] = "extract_failed"
            return ""
        item["_extract_status"] = "ok"
        return text

    # Multi-attachment categories: concat up to N attachments.
    parts: list[str] = []
    used = 0
    for i, link in enumerate(all_links[:MAX_ATTACHMENTS_PER_ITEM]):
        t = extractor.fetch_body_text(link, f"{ticker}_{cat_key}_{i}_{title[:25]}")
        if t:
            parts.append(f"=== Attachment {i+1} ===\n{t}")
            used += 1
    if not parts:
        item["_extract_status"] = "extract_failed"
        return ""
    item["_extract_status"] = f"ok ({used}/{len(all_links)} attachments)"
    return "\n\n".join(parts)


def _enrich_with_summaries(buckets: dict) -> float:
    """For 'full' mode: download PDFs, extract, summarize via LLM.

    insider_trade is special — instead of N per-item LLM calls, do ONE aggregate
    call that produces a Beli/Jual summary across all insider disclosures.
    Other priority categories use per-item summarization.

    Hard cost cap: aborts further LLM calls once cumulative cost exceeds
    MAX_RUN_COST_USD. Items past the cap fall back to title-only display.
    """
    total_cost = 0.0
    cost_capped = False
    for cat_key, bucket in buckets.items():
        if bucket["priority"] != "priority":
            continue

        if cat_key == "insider_trade":
            # Download + extract all insider PDFs first.
            for item in bucket["items"]:
                item["_body_text"] = _download_and_extract(item, cat_key)
            extracted = [it for it in bucket["items"] if it.get("_body_text")]
            if extracted and not cost_capped:
                summary, cost = summarizer.summarize_insider_aggregate(extracted)
                # Post-process: Haiku emits tickers as `CYBR` in backticks. Replace
                # with Markdown links to the disclosure PDF so they're clickable in
                # Telegram. Build a ticker → first-link map from bucket items.
                link_map: dict[str, str] = {}
                for it in bucket["items"]:
                    t = (it.get("ticker") or "").strip().upper()
                    if t and t not in link_map and it.get("link"):
                        link_map[t] = it["link"]
                if link_map:
                    pattern = re.compile(r"`([A-Z]{4})`")
                    def _replace(m: re.Match) -> str:
                        t = m.group(1)
                        return f"[{t}]({link_map[t]})" if t in link_map else m.group(0)
                    summary = pattern.sub(_replace, summary)
                bucket["_aggregate_summary"] = summary
                total_cost += cost
                if total_cost > MAX_RUN_COST_USD:
                    cost_capped = True
                    logger.warning("cost cap hit at $%.4f, skipping further LLM calls", total_cost)
            elif cost_capped:
                bucket["_aggregate_summary"] = "(skipped: cost cap)"
            else:
                bucket["_aggregate_summary"] = "(semua PDF gagal di-extract)"
            continue

        # Per-item path for other priority categories
        for item in bucket["items"]:
            ticker = item.get("ticker", "?")
            title = item.get("title", "")
            if cost_capped:
                item["_summary"] = "(skipped: cost cap)"
                continue
            # Short-circuit "akan menyampaikan" / "rencana penyampaian" LK —
            # these are just heads-up that a filing is coming, no data yet.
            # Skip LLM call, write canned "delay" message. Saves cost.
            if cat_key == "lap_keuangan" and _RENCANA_PATTERN.search(title):
                item["_summary"] = "_Belum ada data — baru pemberitahuan rencana penyampaian._"
                continue
            text = _download_and_extract(item, cat_key)
            if not text:
                item["_summary"] = f"({item.get('_extract_status', 'extract failed')})"
                continue
            summary, cost = summarizer.summarize(cat_key, ticker, title, text)
            item["_summary"] = summary
            total_cost += cost
            # For LK items, also enrich with current market cap so user can
            # quickly see size context. fetch_stock_data hits yfinance which
            # may rate-limit on busy days — wrap in try.
            if cat_key == "lap_keuangan":
                try:
                    sd = fetch_stock_data(ticker)
                    if isinstance(sd, dict) and not sd.get("error"):
                        item["_market_cap"] = sd.get("market_cap", 0)
                        item["_last_price"] = sd.get("last_price", 0)
                except Exception:
                    pass  # graceful — formatter just skips the cap line
            if total_cost > MAX_RUN_COST_USD:
                cost_capped = True
                logger.warning("cost cap hit at $%.4f, skipping further LLM calls", total_cost)
    return total_cost


async def run_briefing(force_mode: str | None = None) -> dict:
    """Execute one briefing run. Returns summary dict for caller (manual trigger or cron)."""
    s = state.get_state()
    mode = force_mode if force_mode in {"header_only", "full"} else s["mode"]
    if mode == "off":
        result = {"status": "skipped", "reason": "mode=off", "mode": mode}
        state.update_last_run(status="skipped")
        return result

    logger.info("briefing run starting (mode=%s)", mode)
    removed = extractor.cleanup_old_pdfs(keep_days=1)
    if removed:
        logger.info("cleaned %d old pdf dir(s)", removed)

    try:
        disclosures = await _fetch_24h_disclosures()
    except Exception as e:
        logger.exception("fetch failed")
        state.update_last_run(status="error", error=f"fetch: {e}")
        return {"status": "error", "step": "fetch", "error": str(e)}

    buckets = classifier.bucket_disclosures(disclosures)
    cost_usd = 0.0
    if mode == "full":
        cost_usd = _enrich_with_summaries(buckets)

    messages = formatter.build_messages(date.today(), len(disclosures), buckets, mode)

    try:
        # Pin first message to channel for the daily 24h recap (the most useful
        # message of the day). Skip pin for header_only manual triggers.
        pin = (mode == "full")
        sent = sender.send_messages(messages, pin_first_in_channel=pin)
    except Exception as e:
        logger.exception("send failed")
        state.update_last_run(status="error", cost_usd=cost_usd, error=f"send: {e}")
        return {"status": "error", "step": "send", "error": str(e), "cost_usd": cost_usd}

    state.update_last_run(status="ok", messages_sent=sent, cost_usd=cost_usd)
    # Mark intraday watermark = now, so subsequent intraday polls don't re-send
    # disclosures already included in this batch.
    state.set_intraday_state(last_at=datetime.now(timezone.utc).isoformat())
    return {
        "status": "ok",
        "mode": mode,
        "disclosures_in_window": len(disclosures),
        "categories": {k: len(v["items"]) for k, v in buckets.items()},
        "messages_sent": sent,
        "cost_usd": round(cost_usd, 4),
    }


def run_briefing_sync():
    """Wrapper for APScheduler (sync context)."""
    try:
        asyncio.run(run_briefing())
    except Exception:
        logger.exception("briefing cron failed")
