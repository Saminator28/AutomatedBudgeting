"""
Database package for AutomatedBudgeting.

Provides SQLite-backed storage for all transaction data.
The database is the sole authoritative store — there is no CSV fallback.

Usage:
    from src.database.session import get_engine, init_db
    from src.database.db_utils import write_month_to_db, write_transfers_to_db
"""
