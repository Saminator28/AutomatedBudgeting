"""
SQLAlchemy engine and session factory.

The database file lives at:
    <project_root>/src/ui/data/budget.db

This module is safe to import from any script in the project because the path
is computed from this file's location, not the caller's cwd.
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import metadata

# Absolute path so any calling script finds the same DB file.
_DATA_ROOT = Path(__file__).parent.parent / 'ui' / 'data'
_DB_PATH   = _DATA_ROOT / 'budget.db'


def get_engine(db_path: Path = _DB_PATH):
    """Return a SQLAlchemy engine for the given SQLite path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f'sqlite:///{db_path}',
        connect_args={'check_same_thread': False},
    )


def init_db(db_path: Path = _DB_PATH):
    """
    Create all tables if they do not already exist.
    Also applies lightweight migrations for columns added after initial creation.
    Safe to call multiple times (CREATE TABLE IF NOT EXISTS semantics).
    """
    from sqlalchemy import text
    engine = get_engine(db_path)
    metadata.create_all(engine)

    # ── Seed default categories if config_categories table is empty ───────────
    try:
        from src.database.db_utils import seed_categories_if_empty
        seed_categories_if_empty(engine)
    except Exception:
        pass  # non-fatal; categories can be seeded later via the UI

    # ── Lightweight column migrations ─────────────────────────────────────────
    # These ALTER TABLE statements are idempotent — they fail silently if the
    # column already exists (SQLite raises OperationalError for duplicate column).
    _migrations = [
        "ALTER TABLE auto_deleted_transactions ADD COLUMN keyword_matched TEXT",
        "ALTER TABLE auto_deleted_transactions ADD COLUMN seen_months TEXT DEFAULT '[]'",
        "ALTER TABLE auto_deleted_transactions ADD COLUMN tx_type TEXT",
        "ALTER TABLE auto_deleted_transactions ADD COLUMN category TEXT",
        "ALTER TABLE auto_deleted_transactions ADD COLUMN original_statement TEXT",
        # keyword source tracking (default/user/learned)
        "ALTER TABLE investment_keywords ADD COLUMN source TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE income_keywords ADD COLUMN source TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE ignore_keywords ADD COLUMN source TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE payment_app_keywords ADD COLUMN source TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE transfer_keywords ADD COLUMN source TEXT NOT NULL DEFAULT 'default'",
        # source_statement: tracks which statement folder each transaction came from
        # so reprocessing month M cleans ALL its rows regardless of report_month.
        "ALTER TABLE transactions ADD COLUMN source_statement TEXT",
        # locked: user-pinned goal — carries the same amount into every new month
        "ALTER TABLE budget_goals ADD COLUMN locked BOOLEAN DEFAULT 0",
        # Backfill: approximate existing rows as coming from their current report_month.
        # Cross-month rows will be corrected on the next reprocess of the source statement.
        "UPDATE transactions SET source_statement = report_month WHERE source_statement IS NULL",
        # chat_sessions: Hermes-managed persistent chatbot sessions.
        # CREATE TABLE IF NOT EXISTS is handled by metadata.create_all() above;
        # these ALTER statements guard columns added after the initial schema.
        "ALTER TABLE chat_sessions ADD COLUMN summary TEXT",
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists — ignore
    return engine


# Module-level engine & session factory, used by main.py and migrate.py.
engine       = get_engine()
SessionLocal = sessionmaker(bind=engine)
