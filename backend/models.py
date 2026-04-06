from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, Enum as SqlEnum
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
