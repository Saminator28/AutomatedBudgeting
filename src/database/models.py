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
    Integer, String, Float, Boolean, Text, Index, UniqueConstraint,
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
    Column('statement',        String(256)),
    Column('user_corrected',   Boolean, default=False),
    Column('source_statement', String(7)),   # YYYY-MM folder month that produced this row
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
    Column('source',  String(16),  nullable=False, server_default='default'),
)

# ── income_keywords ───────────────────────────────────────────────────────────
# Substring keywords that identify incoming credits (payroll, deposits, etc).
# Replaces config/income_keywords.json.
income_keywords = Table(
    'income_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
    Column('source',  String(16),  nullable=False, server_default='default'),
)

# ── ignore_keywords ───────────────────────────────────────────────────────────
# Transactions whose description contains one of these are silently dropped
# before any processing (bank rewards, cashback lines, etc).
# Replaces config/ignore_transactions.json.
ignore_keywords = Table(
    'ignore_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
    Column('source',  String(16),  nullable=False, server_default='default'),
)

# ── payment_app_keywords ──────────────────────────────────────────────────────
# Keywords that flag a transaction as coming from a peer-to-peer payment app
# (Venmo, Zelle, Cash App, etc.) — these are separated for manual review.
# Replaces config/payment_apps.json.
payment_app_keywords = Table(
    'payment_app_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
    Column('source',  String(16),  nullable=False, server_default='default'),
)

# ── transfer_keywords ─────────────────────────────────────────────────────────
# Keywords that identify internal account-to-account transfers so they can be
# excluded from expense/income totals.
# Replaces config/transfer_keywords.json.
transfer_keywords = Table(
    'transfer_keywords', metadata,
    Column('id',      Integer, primary_key=True, autoincrement=True),
    Column('keyword', String(128), unique=True, nullable=False, index=True),
    Column('source',  String(16),  nullable=False, server_default='default'),
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

# ── auto_deleted_transactions ─────────────────────────────────────────────────
# Records every transaction that was automatically removed during processing
# (e.g. flagged as an inter-account transfer or matched a transfer keyword).
# Rows with whitelisted=True are kept on the next reprocess instead of deleted.
# `place_normalized` is the canonical lookup key; `place_display` is what the
# user sees.  `occurrence_count` tracks how many times this pattern was auto-
# removed across all processing runs.
auto_deleted_transactions = Table(
    'auto_deleted_transactions', metadata,
    Column('id',               Integer, primary_key=True, autoincrement=True),
    Column('place_normalized', String(256), nullable=False, index=True),
    Column('place_display',    String(512)),
    Column('amount',           Float),
    Column('tx_date',          String(10)),
    Column('report_month',     String(7), index=True),
    Column('reason',           String(64)),   # 'transfer_keyword' | 'cross_account' | 'bank_transfer' | 'place_filter'
    Column('first_seen',       String(20)),   # ISO timestamp
    Column('last_seen',        String(20)),   # ISO timestamp
    Column('occurrence_count', Integer, default=1),
    Column('whitelisted',      Boolean, default=False),
    Column('seen_months',      String(512), default='[]'),  # JSON list of report_months seen
    Column('keyword_matched',  String(128)),
    Column('tx_type',          String(16)),    # original tx_type at time of manual delete
    Column('category',         String(128)),   # original category at time of manual delete
    Column('original_statement', String(256)), # original statement name at time of manual delete
)

# ── merchant_rules ────────────────────────────────────────────────────────────
# One rule per normalized merchant key.  After each import,
# db_utils._apply_merchant_rules() overrides the parser's auto-classification
# for any transaction whose normalized merchant name matches a stored rule.
# Rules are created by the user from the Transactions tab ("Yes, always" prompt).
#
# action: 'income'  → force tx_type = 'income'
#         'expense' → force tx_type = 'expense', optionally override category
#         'ignore'  → delete the transaction (silently skip it)
merchant_rules = Table(
    'merchant_rules', metadata,
    Column('id',           Integer, primary_key=True, autoincrement=True),
    Column('merchant_key', String(256), unique=True, nullable=False, index=True),
    Column('display_name', String(256)),       # original merchant name shown in UI
    Column('action',       String(16),  nullable=False),  # 'income'|'expense'|'ignore'
    Column('category',     String(128)),       # used when action='expense'
)

# ── budget_goals ──────────────────────────────────────────────────────────────
# One row per category.  Single source of truth for what the user wants to
# spend each month.  Replaces config/budgets.json entirely.
budget_goals = Table(
    'budget_goals', metadata,
    Column('id',             Integer, primary_key=True, autoincrement=True),
    Column('category',       Text, unique=True, nullable=False, index=True),
    Column('goal_amount',    Float),           # user's saved goal (null = no goal set)
    Column('ai_cap',         Float),           # income-anchored 50/30/20 ceiling
    Column('historical_avg', Float),           # 3-month rolling avg at last AI run
    Column('bucket',         Text),            # 'Need' | 'Want' | 'Saving'
    Column('bucket_override', Boolean, default=False),  # true = user set bucket manually
    Column('updated_at',     Text),            # ISO timestamp of last save
)

# ── budget_settings ───────────────────────────────────────────────────────────
# Global budget settings — always a single row (id=1), updated in-place.
budget_settings = Table(
    'budget_settings', metadata,
    Column('id',                      Integer, primary_key=True, autoincrement=True),
    Column('savings_target_amount',   Float),
    Column('savings_target_pct',      Float),
    Column('strategy',                Text, server_default='50/30/20'),
    Column('avg_monthly_income_used', Float),
    Column('updated_at',              Text),
)

# ── budget_history ────────────────────────────────────────────────────────────
# One row per (report_month, category).  Populated automatically each time
# aggregate_monthly.py runs.  Used for the Month Report Card and trend charts.
budget_history = Table(
    'budget_history', metadata,
    Column('id',            Integer, primary_key=True, autoincrement=True),
    Column('report_month',  Text, nullable=False, index=True),  # YYYY-MM
    Column('category',      Text, nullable=False),
    Column('goal',          Float),
    Column('actual',        Float),
    Column('variance',      Float),            # actual − goal (negative = under budget ✓)
    Column('variance_pct',  Float),
    Column('coaching_note', Text),
    Column('created_at',    Text),
    UniqueConstraint('report_month', 'category', name='uq_budget_history_month_cat'),
)

# ── budget_goals_monthly ──────────────────────────────────────────────────────
# Per-month budget goal amounts.  Each month the user saves goals, they land
# here as (month, category) rows.  The global budget_goals table stays as the
# category-level template (bucket, ai_cap, historical_avg, bucket_override).
budget_goals_monthly = Table(
    'budget_goals_monthly', metadata,
    Column('id',          Integer, primary_key=True, autoincrement=True),
    Column('month',       Text, nullable=False, index=True),  # YYYY-MM
    Column('category',    Text, nullable=False, index=True),
    Column('goal_amount', Float),
    Column('updated_at',  Text),
    UniqueConstraint('month', 'category', name='uq_budget_goals_monthly'),
)
