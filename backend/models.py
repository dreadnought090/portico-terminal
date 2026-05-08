from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, JSON, Index, Enum as SqlEnum
from datetime import datetime, timezone
from backend.database import Base
import enum


class SecurityType(str, enum.Enum):
    SAHAM = "Saham"
    OBLIGASI = "Obligasi"
    REKSADANA = "Reksadana"
    ETF = "ETF"
    WARRANT = "Warrant"
    RIGHT = "Right"
    LAINNYA = "Lainnya"


class SubSector(str, enum.Enum):
    BANKING = "Banking"
    MINING = "Mining"
    CONSUMER = "Consumer Goods"
    INFRASTRUCTURE = "Infrastructure"
    PROPERTY = "Property & Real Estate"
    TRADE = "Trade & Services"
    FINANCE = "Finance"
    AGRICULTURE = "Agriculture"
    BASIC_INDUSTRY = "Basic Industry & Chemical"
    MISC_INDUSTRY = "Misc Industry"
    TECHNOLOGY = "Technology"
    ENERGY = "Energy"
    HEALTHCARE = "Healthcare"
    TRANSPORTATION = "Transportation & Logistics"
    TELCO = "Telecommunication"
    OTHER = "Other"


class PortfolioItem(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    company_name = Column(String(200), default="")
    security_type = Column(String(50), default=SecurityType.SAHAM.value)
    sub_sector = Column(String(100), default=SubSector.OTHER.value)
    lot = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    avg_price = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    market_value = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_pct = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    broker = Column(String(100), default="")
    account_type = Column(String(50), default="Reguler")
    notes = Column(Text, default="")


class StockCache(Base):
    __tablename__ = "stock_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), unique=True, nullable=False)
    company_name = Column(String(200), default="")
    sector = Column(String(100), default="")
    sub_sector = Column(String(100), default="")
    last_price = Column(Float, default=0.0)
    prev_close = Column(Float, default=0.0)
    open_price = Column(Float, default=0.0)
    high = Column(Float, default=0.0)
    low = Column(Float, default=0.0)
    volume = Column(Integer, default=0)
    market_cap = Column(Float, default=0.0)
    pe_ratio = Column(Float, default=0.0)
    pb_ratio = Column(Float, default=0.0)
    dividend_yield = Column(Float, default=0.0)
    change = Column(Float, default=0.0)
    change_pct = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NewsItem(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), default="")
    title = Column(String(500), nullable=False)
    link = Column(String(1000), default="")
    source = Column(String(200), default="")
    published = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    summary = Column(Text, default="")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), unique=True, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, unique=True, nullable=False)
    total_cost = Column(Float, default=0.0)
    total_market_value = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)
    total_items = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AnalysisRun(Base):
    """One council/research/sentiment run. Stores full input + output as JSON for audit trail."""
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    run_type = Column(String(20), nullable=False)  # 'council' | 'research' | 'sentiment'
    input_thesis = Column(Text, default="")
    output_json = Column(Text, default="{}")  # full result serialized
    synthesis_text = Column(Text, default="")  # extracted synthesis for quick display
    prompt_version = Column(String(50), default="")
    total_tokens_input = Column(Integer, default=0)
    total_tokens_output = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    duration_ms = Column(Integer, default=0)
    status = Column(String(20), default="completed")  # completed | failed | partial
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ThesisMemo(Base):
    """Versioned thesis memo per ticker. User-editable, council/research can append versions."""
    __tablename__ = "thesis_memos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    version = Column(Integer, default=1)
    content_md = Column(Text, default="")
    confidence_score = Column(Float, default=0.0)  # 0-10 from last council run
    last_council_run_id = Column(Integer, default=0)
    tags_json = Column(Text, default="[]")  # list of tags
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Subscription (IDX Pulse Pro) ──────────────────────────────────────

class Subscriber(Base):
    """Paid-channel subscriber. Keyed by Telegram chat_id."""
    __tablename__ = "subscribers"

    chat_id = Column(Integer, primary_key=True)
    username = Column(String(80), default="")          # without '@'
    full_name = Column(String(120), default="")
    plan = Column(String(20), default="monthly")       # matches config.Plan.key
    status = Column(String(20), default="active")      # active / expired / cancelled / grace
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_telegram_charge_id = Column(String(128), default="")
    reminded_days = Column(String(30), default="")     # comma-sep days already DM'd (e.g. "7,3,1")
    invite_link_last = Column(String(200), default="") # last single-use invite issued
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Payment(Base):
    """Every Telegram Stars charge, keyed by Telegram's charge id."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_charge_id = Column(String(128), unique=True, nullable=False, index=True)
    chat_id = Column(Integer, nullable=False, index=True)
    plan = Column(String(20), default="monthly")
    amount_stars = Column(Integer, default=0)
    payload = Column(String(200), default="")          # internal reference from invoice
    status = Column(String(20), default="paid")        # paid / refunded / disputed
    paid_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    """User feedback submitted via /feedback command."""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, nullable=False, index=True)
    username = Column(String(80), default="")
    message = Column(Text, default="")
    status = Column(String(20), default="new")         # new / read / resolved
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Merriot (thesis tracker) ──────────────────────────────────────────

class ThesisNote(Base):
    """Short-form thesis note per ticker, with smart review reminders.

    Captured via Telegram bot (Merriot) or Portico web UI. LLM-extracted
    structure (key_points, tags, suggested_review_date) lives alongside the
    raw user body. Append-only stream — multiple notes per ticker over time.
    Distinct from ThesisMemo (which is a versioned long-form council memo).
    """
    __tablename__ = "thesis_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    body = Column(Text, nullable=False)                   # raw user input
    thesis_type = Column(String(30), default="other")     # earnings_estimate|valuation|catalyst|sentiment|risk_flag|exit|negative_thesis|other
    thesis_direction = Column(String(20), default="neutral")  # bullish|bearish|neutral|exit
    key_points = Column(JSON, default=list)               # list[str], LLM-extracted bullets
    tags = Column(JSON, default=list)                     # list[str], lowercase
    source = Column(String(20), default="web")            # 'telegram' | 'web'
    confidence = Column(Float, default=0.0)               # 0.0–1.0 from LLM
    review_at = Column(Date, nullable=True, index=True)
    review_reasoning = Column(Text, default="")           # LLM's why-this-date
    status = Column(String(20), default="pending", index=True)
                                                          # pending|reviewed|invalid
    reviewed_at = Column(DateTime, nullable=True)
    follow_up = Column(Text, default="")                  # optional note on review
    portfolio_item_id = Column(Integer, nullable=True)    # soft link, no FK
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_thesis_notes_ticker_created", "ticker", "created_at"),
        Index("ix_thesis_notes_status_review", "status", "review_at"),
    )


class ThesisReminderLog(Base):
    """Idempotency log for triple-reminder cron (H-7, H-1, H+0).

    Cron checks this table before sending a reminder kind for a note.
    Unique (note_id, kind) prevents double-sends after misfire/restart.
    """
    __tablename__ = "thesis_reminder_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(10), nullable=False)             # 'H-7' | 'H-1' | 'H+0'
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_reminder_note_kind", "note_id", "kind", unique=True),
    )


# ── Alerts (price-cross alerts) ───────────────────────────────────────

class IdxTicker(Base):
    """IDX ticker registry — refreshed daily from /primary/TradingSummary/GetStockSummary.

    All ~960 active IDX-listed companies + recent inactive (kept 30d after last_seen
    drops out of feed). Used for ticker validation, autocomplete, sector lookup,
    Merriot extractor context.
    """
    __tablename__ = "idx_tickers"

    code = Column(String(10), primary_key=True)         # 4-letter ticker
    name = Column(String(200), default="")              # company name
    sector = Column(String(100), default="")            # sub-sector if known
    last_close = Column(Float, default=0.0)
    market_cap = Column(Float, default=0.0)             # if available
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    is_active = Column(Integer, default=1)              # 1 if in latest feed, 0 if dropped


class EmailTransaction(Base):
    """Email-detected stock transaction. Dedup + audit trail.

    Cron polls broker emails, Claude extracts → row inserted with status='pending'.
    Ginger DMs user for confirmation. On Confirm → status='confirmed' + apply
    to PortfolioItem. On Reject → status='rejected', no portfolio change.

    Unique message_id prevents double-processing same email.
    """
    __tablename__ = "email_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(200), unique=True, nullable=False, index=True)
    email_subject = Column(String(500), default="")
    email_from = Column(String(200), default="")
    email_received_at = Column(DateTime, nullable=True)

    # Claude extraction
    extracted_action = Column(String(20), default="")    # buy | sell | unknown
    extracted_ticker = Column(String(10), default="")
    extracted_lot = Column(Integer, default=0)
    extracted_shares = Column(Integer, default=0)
    extracted_price = Column(Float, default=0.0)
    extracted_total_value = Column(Float, default=0.0)
    extracted_broker = Column(String(100), default="")
    extracted_trade_date = Column(Date, nullable=True)
    extraction_confidence = Column(Float, default=0.0)
    extraction_raw = Column(Text, default="{}")          # full Claude JSON output

    # Confirmation flow
    status = Column(String(20), default="pending", index=True)
                                                          # pending | confirmed | rejected | failed | duplicate
    confirmed_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    error_message = Column(Text, default="")

    # Audit
    raw_body_excerpt = Column(Text, default="")          # first 1000 chars
    portfolio_item_id = Column(Integer, nullable=True)   # link to applied position
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PriceAlert(Base):
    """Price-cross alert. Independent from ThesisNote — loose coupling via
    ticker string only. Cron evaluates armed alerts every 5 min during market
    hours, fires Telegram notification on threshold cross. One-shot (status
    becomes 'triggered' after fire — re-arm = cancel old + create new).
    """
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    direction = Column(String(10), nullable=False)        # 'above' | 'below'
    threshold_price = Column(Float, nullable=False)
    label = Column(String(200), default="")               # optional user note
    status = Column(String(20), default="armed", index=True)
                                                          # armed | triggered | cancelled | expired
    expires_at = Column(DateTime, nullable=True)          # nullable = no expiry

    # Trigger details (populated on fire)
    triggered_at = Column(DateTime, nullable=True)
    triggered_price = Column(Float, nullable=True)
    drift_pct = Column(Float, nullable=True)              # (triggered - threshold) / threshold

    # Cron observability
    last_check_price = Column(Float, default=0.0)
    last_checked_at = Column(DateTime, nullable=True)

    # Notification target
    chat_id = Column(Integer, nullable=True, index=True)  # null = use default admin
    source = Column(String(20), default="telegram")       # 'telegram' | 'web'

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_price_alerts_status_ticker", "status", "ticker"),
        Index("ix_price_alerts_ticker_dir_thr", "ticker", "direction", "threshold_price"),
        Index("ix_price_alerts_status_created", "status", "created_at"),
    )
