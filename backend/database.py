from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    # Railway/PostgreSQL — fix legacy "postgres://" scheme
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
else:
    # Local development — SQLite
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mybloomberg.db")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Enable WAL on SQLite — multiple writers (web requests + APScheduler cron
    # + Telegram bots) need WAL to avoid "database is locked" under contention.
    if not DATABASE_URL:
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.commit()
