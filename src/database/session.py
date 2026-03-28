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
    Safe to call multiple times (CREATE TABLE IF NOT EXISTS semantics).
    """
    engine = get_engine(db_path)
    metadata.create_all(engine)
    return engine


# Module-level engine & session factory, used by main.py and migrate.py.
engine       = get_engine()
SessionLocal = sessionmaker(bind=engine)
