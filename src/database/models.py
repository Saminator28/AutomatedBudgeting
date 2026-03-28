"""
SQLAlchemy table definitions for the AutomatedBudgeting database.

Tables:
  transactions        — one row per transaction (expenses and income).
  merchant_metadata   — per-merchant learned data (investment platform flag, tags).
  transfers           — investment or account-transfer rows (Direction=In/Out).
  investment_keywords — keywords for detecting investment-platform transactions.
  income_keywords     — keywords for detecting income credits.
  ignore_keywords     — keywords for transactions to silently drop.
  payment_app_keywords— keywords for peer-to-peer payment apps (Venmo, Zelle, etc.).
  transfer_keywords   — keywords for inter-account transfers.
  institution_cache   — maps statement header fingerprint → institution name.
"""

from sqlalchemy import (
    MetaData, Table, Column,
    Integer, String, Float, Boolean, Text, Index,
)

metadata = MetaData()

# ── transactions ─────────────────────────────────────────────────────────────
# One row per transaction.  The stable identity key is `tx_hash` which is
# computed from (report_month, tx_date, place_upper, amount_cents, tx_type,
# statement) — see db_utils.py for the exact formula.
#
# tx_type: 'expense' | 'income' | 'transfer'
transactions = Table(
    'transactions', metadata,
    Column('id',             Integer, primary_key=True, autoincrement=True),
    Column('tx_hash',        String(24), unique=True, nullable=False, index=True),
    Column('report_month',   String(7),  nullable=False, index=True),   # YYYY-MM
    Column('tx_date',        String(10)),                                # MM/DD/YYYY
    Column('place',          String(512)),
    Column('amount',         Float),
    Column('category',       String(128), index=True),
    Column('label',          String(32)),   # recurring | one-time | bonus | reimbursement
    Column('tx_type',        String(16), nullable=False, index=True),
    Column('statement',      String(256)),
    Column('user_corrected', Boolean, default=False),
)

# ── merchant_metadata ────────────────────────────────────────────────────────
# Keyed on the normalised merchant name (lower-cased, punctuation stripped).
# `is_investment_platform` replaces the hardcoded _INVESTMENT_PLATFORM_KEYWORDS
# lists in main.py and aggregate_monthly.py.
# `tags` is a JSON array of free-form strings for future extensibility.
merchant_metadata = Table(
    'merchant_metadata', metadata,
    Column('id',                   Integer, primary_key=True, autoincrement=True),
    Column('merchant_key',         String(256), unique=True, nullable=False, index=True),
    Column('is_investment_platform', Boolean, default=False),
    Column('tags',                 Text, default='[]'),   # JSON array
    Column('user_corrected',       Boolean, default=False),
)

# ── transfers ─────────────────────────────────────────────────────────────────
# Investment / account transfers (Direction=In or Out).  Rebuilt from
# statements/*/transfers.csv + investment rows in the transactions table by
# _rebuild_transfers_in_db() in main.py.
transfers = Table(
    'transfers', metadata,
    Column('id',           Integer, primary_key=True, autoincrement=True),
    Column('tx_hash',      String(24), unique=True, nullable=False, index=True),
    Column('report_month', String(7),  nullable=False, index=True),
    Column('tx_date',      String(10)),
    Column('place',        String(512)),
    Column('amount',       Float),
    Column('direction',    String(4)),   # 'In' | 'Out'
    Column('statement',    String(256)),
    Column('label',        String(64)),  # 'Retirement' | 'Personal' | None
)

# ── investment_keywords ────────────────────────────────────────────────────────
# Substring keywords used to detect investment-platform transactions.
# Replaces config/investment_platforms.json so changes are made through the UI
# and reflected immediately without a container rebuild.
investment_keywords = Table(
    'investment_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
)

# ── income_keywords ───────────────────────────────────────────────────────────
# Substring keywords that identify incoming credits (payroll, deposits, etc).
# Replaces config/income_keywords.json.
income_keywords = Table(
    'income_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
)

# ── ignore_keywords ───────────────────────────────────────────────────────────
# Transactions whose description contains one of these are silently dropped
# before any processing (bank rewards, cashback lines, etc).
# Replaces config/ignore_transactions.json.
ignore_keywords = Table(
    'ignore_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
)

# ── payment_app_keywords ──────────────────────────────────────────────────────
# Keywords that flag a transaction as coming from a peer-to-peer payment app
# (Venmo, Zelle, Cash App, etc.) — these are separated for manual review.
# Replaces config/payment_apps.json.
payment_app_keywords = Table(
    'payment_app_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
)

# ── transfer_keywords ─────────────────────────────────────────────────────────
# Keywords that identify internal account-to-account transfers so they can be
# excluded from expense/income totals.
# Replaces config/transfer_keywords.json.
transfer_keywords = Table(
    'transfer_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
)

# ── institution_cache ─────────────────────────────────────────────────────────
# Maps a stable header fingerprint → institution name so the same account
# statement (across months) always gets the same institution name.
# The fingerprint is computed by StatementParser._institution_fingerprint().
institution_cache = Table(
    'institution_cache', metadata,
    Column('id',               Integer, primary_key=True, autoincrement=True),
    Column('header_fp',        String(16), unique=True, nullable=False, index=True),
    Column('institution_name', String(256), nullable=False),
)
