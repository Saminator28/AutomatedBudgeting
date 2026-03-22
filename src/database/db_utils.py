"""
SQLite DB helpers: seed functions, hash utilities, and direct DataFrame writers.

Design notes
------------
* The DB is the sole authoritative store for all transaction data.
  Users import statements via the UI; there is no CSV migration path.
* A stable `tx_hash` is built from
      SHA256(report_month | tx_date_norm | PLACE_UPPER | amount_cents | tx_type | statement)
  truncated to 24 hex chars.  This lets us INSERT OR IGNORE on full
  re-syncs and UPDATE on individual edits without needing auto-increment
  knowledge from the caller.
* Summary rows injected by aggregate_monthly.py
  (EXPENSE BREAKDOWN, Total:, GRAND TOTAL) are silently skipped.
"""

import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── path helpers ──────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent.parent          # repo root
_CONFIG_ROOT  = _PROJECT_ROOT / 'config'

_SUMMARY_RE = re.compile(
    r'EXPENSE BREAKDOWN|Total:|GRAND TOTAL', re.IGNORECASE
)

# ── hash helper ───────────────────────────────────────────────────────────────

def _make_hash(report_month: str, tx_date: str, place: str,
               amount: float, tx_type: str, statement: str,
               seq: int = 0) -> str:
    """Return a 24-char hex digest that stably identifies a transaction row."""
    amount_cents = int(round(float(amount) * 100))
    raw = (
        f"{report_month}|{str(tx_date).strip()}|"
        f"{str(place).upper().strip()}|{amount_cents}|"
        f"{tx_type}|{str(statement).strip()}|{seq}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _assign_hashes(df: pd.DataFrame, report_month: str, tx_type: str) -> pd.DataFrame:
    """Add a `tx_hash` column to *df*, handling genuine duplicate rows with a seq counter."""
    df = df.copy()
    seen: dict = {}
    hashes = []
    for _, row in df.iterrows():
        base_key = (
            report_month,
            str(row.get('Transaction Date', '')).strip(),
            str(row.get('Place', '')).upper().strip(),
            round(float(row.get('Amount', 0) or 0), 2),
            tx_type,
            str(row.get('Statement', '')).strip(),
        )
        seq = seen.get(base_key, 0)
        seen[base_key] = seq + 1
        hashes.append(_make_hash(*base_key, seq=seq))
    df['tx_hash'] = hashes
    return df


# ── investment-platform metadata ──────────────────────────────────────────────

def _load_investment_keywords_from_db(engine) -> list[str]:
    """Load investment-platform keywords from the DB."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text('SELECT keyword FROM investment_keywords ORDER BY keyword')).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def _normalize_merchant_key(place: str) -> str:
    """Return a normalised merchant key for merchant_metadata lookup."""
    s = str(place).lower()
    s = re.sub(r"['\.\-,#]", '', s)
    s = re.sub(r'\b\d{3,}\b', '', s)
    return ' '.join(s.split())


def _sync_merchant_metadata(engine, keywords: list[str], all_places: list[str]) -> None:
    """
    Upsert merchant_metadata rows for every unique place seen in transactions
    and for every keyword placeholder.  Sets `is_investment_platform=True` for
    any merchant whose normalised key contains one of the investment keywords.
    """
    unique_keys = {_normalize_merchant_key(p) for p in all_places if str(p).strip()}
    rows = []
    for key in unique_keys:
        is_inv = any(kw in key for kw in keywords)
        rows.append({
            'merchant_key':           key,
            'is_investment_platform': is_inv,
            'tags':                   '[]',
            'user_corrected':         False,
        })

    if not rows:
        return

    with engine.connect() as conn:
        for row in rows:
            conn.execute(text(
                """
                INSERT INTO merchant_metadata
                    (merchant_key, is_investment_platform, tags, user_corrected)
                VALUES
                    (:merchant_key, :is_investment_platform, :tags, :user_corrected)
                ON CONFLICT(merchant_key) DO UPDATE SET
                    is_investment_platform = excluded.is_investment_platform
                WHERE merchant_metadata.user_corrected = 0
                """
            ), row)
        conn.commit()


# ── institution cache bootstrap ──────────────────────────────────────────────

def seed_investment_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of keywords from config/investment_platforms.json into the
    investment_keywords DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'investment_platforms.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            keywords = json.load(f).get('keywords', [])
    except Exception as exc:
        logger.warning(f'seed_investment_keywords: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    'INSERT OR IGNORE INTO investment_keywords (keyword) VALUES (:kw)'
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_income_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of keywords from config/income_keywords.json into the
    income_keywords DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'income_keywords.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            keywords = json.load(f).get('income_keywords', [])
    except Exception as exc:
        logger.warning(f'seed_income_keywords: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    'INSERT OR IGNORE INTO income_keywords (keyword) VALUES (:kw)'
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_ignore_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of keywords from config/ignore_transactions.json into the
    ignore_keywords DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'ignore_transactions.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            keywords = json.load(f).get('ignore_keywords', [])
    except Exception as exc:
        logger.warning(f'seed_ignore_keywords: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    'INSERT OR IGNORE INTO ignore_keywords (keyword) VALUES (:kw)'
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_payment_app_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of keywords from config/payment_apps.json into the
    payment_app_keywords DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'payment_apps.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            keywords = json.load(f).get('payment_app_keywords', [])
    except Exception as exc:
        logger.warning(f'seed_payment_app_keywords: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    'INSERT OR IGNORE INTO payment_app_keywords (keyword) VALUES (:kw)'
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_transfer_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of keywords from config/transfer_keywords.json into the
    transfer_keywords DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'transfer_keywords.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            keywords = json.load(f).get('keywords', [])
    except Exception as exc:
        logger.warning(f'seed_transfer_keywords: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    'INSERT OR IGNORE INTO transfer_keywords (keyword) VALUES (:kw)'
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_institution_cache(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    One-time import of any entries in config/institution_cache.json into the
    institution_cache DB table.  Safe to call repeatedly (INSERT OR IGNORE).
    Returns the number of rows inserted.
    """
    json_path = config_root / 'institution_cache.json'
    if not json_path.exists():
        return 0
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning(f'seed_institution_cache: could not read JSON: {exc}')
        return 0

    inserted = 0
    with engine.connect() as conn:
        for fp, name in data.items():
            conn.execute(text(
                'INSERT OR IGNORE INTO institution_cache (header_fp, institution_name) '
                'VALUES (:fp, :name)'
            ), {'fp': str(fp), 'name': str(name)})
            inserted += 1
        conn.commit()
    return inserted


# ── Direct DataFrame writers ──────────────────────────────────────────────────

_COL_MAP = {
    'Transaction Date': 'tx_date',
    'Place':            'place',
    'Amount':           'amount',
    'category':         'category',
    'Label':            'label',
    'Statement':        'statement',
    'user_corrected':   'user_corrected',
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Rename DataFrame columns to DB column names, keeping only the DB columns."""
    df = df.rename(columns=_COL_MAP)
    keep = ['tx_hash', 'report_month', 'tx_type',
            'tx_date', 'place', 'amount', 'category',
            'label', 'statement', 'user_corrected']
    for col in keep:
        if col not in df.columns:
            df[col] = None
    df['user_corrected'] = df['user_corrected'].map(
        lambda v: str(v).strip().lower() in ('true', '1', 'yes')
        if pd.notna(v) else False
    )
    return df[keep]


def write_month_to_db(engine,
                      month: str,
                      expenses_df=None,
                      income_df=None) -> int:
    """
    Write pre-processed DataFrames for a calendar month directly to the DB,
    preserving any rows the user has manually corrected (user_corrected=True).

    Only the tx_types present in the supplied DataFrames are replaced.
    For example, passing only expenses_df=df leaves existing income rows
    for the month untouched.

    Called by aggregate_monthly.py instead of writing monthly_reports CSVs.
    Returns the total number of rows written.
    """
    from .session import init_db
    init_db()

    frames = []
    types_to_replace: list = []
    for df, tx_type in ((expenses_df, 'expense'), (income_df, 'income')):
        if df is None or (hasattr(df, 'empty') and df.empty):
            continue
        df = df.copy()
        # Strip summary rows that aggregate_monthly appends
        if 'Place' in df.columns:
            df = df[~df['Place'].astype(str).str.contains(_SUMMARY_RE, na=False)]
        if df.empty:
            continue
        df = _assign_hashes(df, month, tx_type)
        df['report_month'] = month
        df['tx_type']      = tx_type
        frames.append(df)
        types_to_replace.append(tx_type)

    if not types_to_replace:
        return 0

    combined  = pd.concat(frames, ignore_index=True)
    normalised = _normalise(combined)

    # Save user-corrected rows (only the tx_types we are about to replace)
    type_placeholders = ','.join(f"'{t}'" for t in types_to_replace)
    with engine.connect() as conn:
        uc_rows = conn.execute(text(
            f"SELECT tx_hash, category, label, place FROM transactions "
            f"WHERE report_month=:m AND user_corrected=1 AND tx_type IN ({type_placeholders})"
        ), {'m': month}).fetchall()
        uc_map = {r[0]: {'category': r[1], 'label': r[2], 'place': r[3]} for r in uc_rows}

        for tx_type in types_to_replace:
            conn.execute(text(
                "DELETE FROM transactions WHERE report_month=:m AND tx_type=:t"
            ), {'m': month, 't': tx_type})
        conn.commit()

    normalised.to_sql('transactions', engine, if_exists='append', index=False)

    # Re-apply user corrections that survived the wipe
    if uc_map:
        with engine.connect() as conn:
            for tx_hash, corr in uc_map.items():
                conn.execute(text(
                    "UPDATE transactions SET "
                    "  category=COALESCE(:cat, category), "
                    "  label=COALESCE(:lbl, label), "
                    "  place=COALESCE(:pl, place), "
                    "  user_corrected=1 "
                    "WHERE tx_hash=:h"
                ), {'cat': corr['category'], 'lbl': corr['label'],
                    'pl': corr['place'],     'h': tx_hash})
            conn.commit()

    keywords = _load_investment_keywords_from_db(engine)
    _sync_merchant_metadata(engine, keywords, normalised['place'].dropna().tolist())

    logger.info(f"migrate: wrote {len(normalised)} rows for {month} ({', '.join(types_to_replace)}) directly to DB")
    return len(normalised)


def write_transfers_to_db(engine, month: str, rows: list) -> int:
    """
    Write a list of transfer dicts for a calendar month to the transfers table.
    Each dict must have: tx_date, place, amount, direction, statement.
    Existing transfers for the month are replaced.

    Called by _rebuild_transfers_in_db() in main.py.
    Returns the number of rows written.
    """
    from .session import init_db
    init_db()

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM transfers WHERE report_month=:m"), {'m': month})
        conn.commit()

    if not rows:
        return 0

    df = pd.DataFrame(rows)
    df['report_month'] = month

    # Compute stable tx_hash for transfers using the same approach as transactions
    seen: dict = {}
    hashes = []
    for _, row in df.iterrows():
        base = (
            month,
            str(row.get('tx_date', '')).strip(),
            str(row.get('place', '')).upper().strip(),
            round(float(row.get('amount', 0) or 0), 2),
            str(row.get('direction', '')).strip(),
            str(row.get('statement', '')).strip(),
        )
        seq = seen.get(base, 0)
        seen[base] = seq + 1
        hashes.append(_make_hash(*base[:6], seq=seq))
    df['tx_hash'] = hashes

    keep = ['tx_hash', 'report_month', 'tx_date', 'place', 'amount',
            'direction', 'statement', 'label']
    for col in keep:
        if col not in df.columns:
            df[col] = None

    df[keep].to_sql('transfers', engine, if_exists='append', index=False)
    logger.info(f"migrate: wrote {len(df)} transfer row(s) for {month}")
    return len(df)
