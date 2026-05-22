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


def _normalize_whitelist_key(place: str) -> str:
    """Date/time-stripped normalization for cross-month whitelist matching.

    Strips date (M/DD/YY) and time (H:MM) patterns and masked-account tokens
    (xxxxxxNNNN) from the standard normalized key so the same recurring transfer
    description is recognized across different months even when the embedded
    date or time in the description varies.
    """
    s = _normalize_merchant_key(place)
    # Strip date-like patterns: 1/01/25, 12/01/2025, 12/25
    s = re.sub(r'\d{1,2}/\d{2}(?:/\d{2,4})?', '', s)
    # Strip time-like patterns: 4:31, 14:30
    s = re.sub(r'\d{1,2}:\d{2}', '', s)
    # Strip masked-account tokens like xxxxxx5218
    s = re.sub(r'x+\d+', '', s)
    return ' '.join(s.split()).strip()


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

_DEFAULT_INVESTMENT_KEYWORDS = [
    'fidelity', 'vanguard', 'schwab', 'etrade', 'robinhood', 'coinbase',
    'td ameritrade', 'merrill', 'wealthfront', 'betterment', 'sofi invest',
    'webull', 'acorns', 'stash', 'public.com',
]

_DEFAULT_INCOME_KEYWORDS = [
    'payroll', 'direct dep', 'direct deposit', 'salary', 'wages', 'ach deposit',
    'zelle', 'employer', 'state refund', 'tax refund',
    'dividend', 'interest paid',
]

_DEFAULT_IGNORE_KEYWORDS = [
    'balance forward', 'beginning balance', 'ending balance',
    'online transfer to', 'online transfer from', 'payment thank you',
    'automatic payment', 'autopay', 'minimum payment',
]

_DEFAULT_PAYMENT_APP_KEYWORDS = [
    'venmo', 'paypal', 'cashapp', 'cash app', 'zelle', 'apple pay',
    'google pay', 'samsung pay', 'square cash',
]

_DEFAULT_TRANSFER_KEYWORDS = [
    'transfer', 'xfer', 'wire transfer', 'outgoing wire', 'incoming wire',
    'ach transfer', 'internal transfer', 'account transfer', 'funds transfer',
]


def _seed_table(engine, table: str, col: str, keywords: list) -> int:
    """Insert *keywords* into *table*.*col* with INSERT OR IGNORE and source='default'.
    Returns count inserted."""
    inserted = 0
    with engine.connect() as conn:
        for kw in keywords:
            kw = str(kw).strip().lower()
            if kw:
                conn.execute(text(
                    f"INSERT OR IGNORE INTO {table} ({col}, source) VALUES (:kw, 'default')"
                ), {'kw': kw})
                inserted += 1
        conn.commit()
    return inserted


def seed_investment_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Seed investment_keywords from config/investment_platforms.json.
    Falls back to bundled defaults when the file is absent.
    Safe to call repeatedly (INSERT OR IGNORE).
    """
    json_path = config_root / 'investment_platforms.json'
    if json_path.exists():
        try:
            with open(json_path) as f:
                keywords = json.load(f).get('keywords', [])
        except Exception as exc:
            logger.warning(f'seed_investment_keywords: could not read JSON: {exc}')
            keywords = _DEFAULT_INVESTMENT_KEYWORDS
    else:
        keywords = _DEFAULT_INVESTMENT_KEYWORDS
    return _seed_table(engine, 'investment_keywords', 'keyword', keywords)


def seed_income_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Seed income_keywords from config/income_keywords.json.
    Falls back to bundled defaults when the file is absent.
    Safe to call repeatedly (INSERT OR IGNORE).
    """
    json_path = config_root / 'income_keywords.json'
    if json_path.exists():
        try:
            with open(json_path) as f:
                keywords = json.load(f).get('income_keywords', [])
        except Exception as exc:
            logger.warning(f'seed_income_keywords: could not read JSON: {exc}')
            keywords = _DEFAULT_INCOME_KEYWORDS
    else:
        keywords = _DEFAULT_INCOME_KEYWORDS
    return _seed_table(engine, 'income_keywords', 'keyword', keywords)


def seed_ignore_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Seed ignore_keywords from config/ignore_transactions.json.
    Falls back to bundled defaults when the file is absent.
    Safe to call repeatedly (INSERT OR IGNORE).
    """
    json_path = config_root / 'ignore_transactions.json'
    if json_path.exists():
        try:
            with open(json_path) as f:
                keywords = json.load(f).get('ignore_keywords', [])
        except Exception as exc:
            logger.warning(f'seed_ignore_keywords: could not read JSON: {exc}')
            keywords = _DEFAULT_IGNORE_KEYWORDS
    else:
        keywords = _DEFAULT_IGNORE_KEYWORDS
    return _seed_table(engine, 'ignore_keywords', 'keyword', keywords)


def seed_payment_app_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Seed payment_app_keywords from config/payment_apps.json.
    Falls back to bundled defaults when the file is absent.
    Safe to call repeatedly (INSERT OR IGNORE).
    """
    json_path = config_root / 'payment_apps.json'
    if json_path.exists():
        try:
            with open(json_path) as f:
                keywords = json.load(f).get('payment_app_keywords', [])
        except Exception as exc:
            logger.warning(f'seed_payment_app_keywords: could not read JSON: {exc}')
            keywords = _DEFAULT_PAYMENT_APP_KEYWORDS
    else:
        keywords = _DEFAULT_PAYMENT_APP_KEYWORDS
    return _seed_table(engine, 'payment_app_keywords', 'keyword', keywords)


def seed_transfer_keywords(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Seed transfer_keywords from config/transfer_keywords.json.
    Falls back to bundled defaults when the file is absent.
    Safe to call repeatedly (INSERT OR IGNORE).
    """
    json_path = config_root / 'transfer_keywords.json'
    if json_path.exists():
        try:
            with open(json_path) as f:
                keywords = json.load(f).get('keywords', [])
        except Exception as exc:
            logger.warning(f'seed_transfer_keywords: could not read JSON: {exc}')
            keywords = _DEFAULT_TRANSFER_KEYWORDS
    else:
        keywords = _DEFAULT_TRANSFER_KEYWORDS
    return _seed_table(engine, 'transfer_keywords', 'keyword', keywords)


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


# ── Default categories (seeded on first startup) ──────────────────────────────
# Clean built-in defaults for new installs.  On first startup the app checks
# whether config_categories is empty; if so, it seeds from this list.
_DEFAULT_CATEGORIES: list[tuple[str, 'str | None']] = [
    ('Groceries',          None),
    ('Dining',             None),
    ('Transportation',     None),
    ('Gas/Fuel',           'Transportation'),
    ('Auto Maintenance',   'Transportation'),
    ('Parking',            'Transportation'),
    ('Public Transit',     'Transportation'),
    ('Housing',            None),
    ('Rent/Mortgage',      'Housing'),
    ('Home Maintenance',   'Housing'),
    ('Utilities',          None),
    ('Electric',           'Utilities'),
    ('Natural Gas',        'Utilities'),
    ('Water/Sewer',        'Utilities'),
    ('Internet/Cable',     'Utilities'),
    ('Phone',              'Utilities'),
    ('Healthcare',         None),
    ('Medical',            'Healthcare'),
    ('Dental',             'Healthcare'),
    ('Pharmacy',           'Healthcare'),
    ('Health Insurance',   'Healthcare'),
    ('Entertainment',      None),
    ('Streaming',          'Entertainment'),
    ('Hobbies',            'Entertainment'),
    ('Shopping',           None),
    ('Clothing',           'Shopping'),
    ('Electronics',        'Shopping'),
    ('Personal Care',      None),
    ('Fitness & Wellness', None),
    ('Travel',             None),
    ('Pets',               None),
    ('Education',          None),
    ('Gifts & Donations',  None),
    ('Banking Fees',       None),
    ('Investments/Savings', None),
]


def seed_categories_if_empty(engine, config_root: Path = _CONFIG_ROOT) -> int:
    """
    Populate config_categories from built-in defaults only when the table is empty.
    Safe to call on every startup.  Returns the number of rows inserted.
    """
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM config_categories")).scalar()
        if count > 0:
            return 0

        rows_to_insert: list[tuple[str, 'str | None']] | None = None
        if not rows_to_insert:
            rows_to_insert = list(_DEFAULT_CATEGORIES)

        inserted = 0
        for i, (name, parent) in enumerate(rows_to_insert):
            conn.execute(text(
                'INSERT OR IGNORE INTO config_categories (name, parent, sort_order) '
                'VALUES (:n, :p, :s)'
            ), {'n': name, 'p': parent, 's': i})
            inserted += 1
        conn.commit()

    logger.info(f'seed_categories_if_empty: inserted {inserted} categories')
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
            'label', 'statement', 'user_corrected', 'source_statement']
    for col in keep:
        if col not in df.columns:
            df[col] = None
    df['user_corrected'] = df['user_corrected'].map(
        lambda v: str(v).strip().lower() in ('true', '1', 'yes')
        if pd.notna(v) else False
    )
    return df[keep]


def _apply_merchant_rules(engine, month: str) -> int:
    """
    Apply user-defined merchant rules to newly written transactions.
    Skips any row already marked user_corrected=1.
    Returns the number of rows affected.
    """
    try:
        with engine.connect() as conn:
            rules = conn.execute(text(
                'SELECT merchant_key, action, category FROM merchant_rules'
            )).fetchall()
            if not rules:
                return 0
            rule_map = {r[0]: {'action': r[1], 'category': r[2]} for r in rules}

            rows = conn.execute(text(
                'SELECT tx_hash, place FROM transactions '
                'WHERE report_month=:m AND user_corrected=0'
            ), {'m': month}).fetchall()

            to_delete, to_income, to_expense = [], [], []
            for tx_hash, place in rows:
                mk = _normalize_merchant_key(place)
                rule = rule_map.get(mk)
                if rule is None:
                    continue
                action = rule['action']
                if action == 'ignore':
                    to_delete.append(tx_hash)
                elif action == 'income':
                    to_income.append(tx_hash)
                elif action == 'expense':
                    to_expense.append((tx_hash, rule['category']))

            changed = 0
            for h in to_delete:
                conn.execute(text('DELETE FROM transactions WHERE tx_hash=:h'), {'h': h})
                changed += 1
            for h in to_income:
                conn.execute(text(
                    "UPDATE transactions SET tx_type='income' WHERE tx_hash=:h"
                ), {'h': h})
                # Remove any pre-existing income row for the same transaction
                # that survived from a previous parse run (different hash because
                # tx_type was baked into the hash when the row was first written).
                conn.execute(text(
                    "DELETE FROM transactions WHERE tx_type='income' AND tx_hash!=:h "
                    "AND report_month=(SELECT report_month FROM transactions WHERE tx_hash=:h) "
                    "AND tx_date=(SELECT tx_date FROM transactions WHERE tx_hash=:h) "
                    "AND UPPER(place)=(SELECT UPPER(place) FROM transactions WHERE tx_hash=:h) "
                    "AND ROUND(amount,2)=(SELECT ROUND(amount,2) FROM transactions WHERE tx_hash=:h)"
                ), {'h': h})
                changed += 1
            for h, cat in to_expense:
                if cat:
                    conn.execute(text(
                        "UPDATE transactions SET tx_type='expense', category=:cat "
                        'WHERE tx_hash=:h'
                    ), {'cat': cat, 'h': h})
                else:
                    conn.execute(text(
                        "UPDATE transactions SET tx_type='expense' WHERE tx_hash=:h"
                    ), {'h': h})
                changed += 1
            if changed:
                conn.commit()
            return changed
    except Exception as exc:
        logger.warning(f'_apply_merchant_rules: {exc}')
        return 0


def _auto_mark_bank_transfers(engine, month: str) -> int:
    """
    Set tx_type='transfer' for any expense/income row whose normalized merchant
    key matches a transfer keyword (e.g. 'online phone transfer', 'wire').  Rows
    already marked user_corrected=1 and investment-platform rows are skipped.
    Whitelisted places (in auto_deleted_transactions with reason='transfer_keyword')
    are preserved as expenses/income.
    Returns the number of rows updated.
    """
    try:
        with engine.connect() as conn:
            xfer_kws = [r[0].strip().lower()
                        for r in conn.execute(text('SELECT keyword FROM transfer_keywords')).fetchall()]
            inv_kws  = [r[0].strip().lower()
                        for r in conn.execute(text('SELECT keyword FROM investment_keywords')).fetchall()]
            if not xfer_kws:
                return 0

            rows = conn.execute(text(
                "SELECT tx_hash, place, amount, tx_date, tx_type, statement FROM transactions "
                "WHERE report_month=:m AND tx_type IN ('expense','income') "
                "AND user_corrected=0"
            ), {'m': month}).fetchall()

        # Load whitelisted normalized places for transfer_keyword reason
        whitelisted = get_whitelisted_places(engine, reason='transfer_keyword')

        to_transfer = []
        for tx_hash, place, amount, tx_date, orig_tx_type, orig_statement in rows:
            mk = _normalize_merchant_key(place)
            matched_kw = next((kw for kw in xfer_kws if kw in mk), None)
            if matched_kw and not any(kw in mk for kw in inv_kws):
                if mk in whitelisted or _normalize_whitelist_key(mk) in whitelisted:
                    continue  # User whitelisted this — keep as expense/income
                to_transfer.append((tx_hash, place, amount, tx_date, matched_kw))
                log_auto_deleted(
                    engine,
                    place=place,
                    amount=float(amount or 0),
                    tx_date=str(tx_date or ''),
                    report_month=month,
                    reason='transfer_keyword',
                    keyword_matched=matched_kw,
                    tx_type=orig_tx_type or 'expense',
                    original_statement=str(orig_statement or ''),
                )

        if to_transfer:
            with engine.connect() as conn:
                for h, *_ in to_transfer:
                    conn.execute(text(
                        "UPDATE transactions SET tx_type='transfer' WHERE tx_hash=:h"
                    ), {'h': h})
                conn.commit()
        return len(to_transfer)
    except Exception as exc:
        logger.warning(f'_auto_mark_bank_transfers: {exc}')
        return 0


def _auto_categorize_credits(engine, month: str) -> int:
    """
    For income rows in *month* that have no category (or only 'Return/Reimbursement'),
    look up the most recent expense from the same merchant and copy its category.

    This handles credit-card return / reimbursement rows that the parser could not
    categorize at parse time (e.g. a Delta refund matched to the Delta expense).
    Rows already marked user_corrected=1 are never modified.
    Returns the number of rows updated.
    """
    try:
        with engine.connect() as conn:
            creds = conn.execute(text(
                "SELECT tx_hash, place FROM transactions "
                "WHERE report_month=:m AND tx_type='income' AND user_corrected=0 "
                "AND (category IS NULL OR TRIM(category)='' OR category='Return/Reimbursement')"
            ), {'m': month}).fetchall()
            if not creds:
                return 0

            # Build normalised-key → most-recent-category map from ALL expense rows
            exp_rows = conn.execute(text(
                "SELECT place, category FROM transactions "
                "WHERE tx_type='expense' AND category IS NOT NULL AND TRIM(category) != '' "
                "ORDER BY report_month DESC, tx_date DESC"
            )).fetchall()

        cat_map: dict = {}
        for exp_place, cat in exp_rows:
            mk = _normalize_merchant_key(exp_place)
            if mk not in cat_map:
                cat_map[mk] = str(cat).strip()

        updated = 0
        with engine.connect() as conn:
            for tx_hash, place in creds:
                matched = cat_map.get(_normalize_merchant_key(place))
                if matched:
                    conn.execute(text(
                        'UPDATE transactions SET category=:cat WHERE tx_hash=:h'
                    ), {'cat': matched, 'h': tx_hash})
                    updated += 1
            if updated:
                conn.commit()
        return updated
    except Exception as exc:
        logger.warning(f'_auto_categorize_credits: {exc}')
        return 0


def _apply_income_keywords(engine, month: str) -> int:
    """
    Promote expense rows that match an income keyword to income.

    Each keyword in income_keywords is treated as a case-insensitive regex pattern,
    so 'payroll' matches 'John Deere World Payroll', 'direct dep' matches
    'Direct Deposit - ACME Corp', etc.

    Invalid regex patterns are skipped with a warning rather than aborting the
    entire pass — one bad user-entered keyword cannot block all promotions.

    Investment platform transactions are EXCLUDED: if the normalized place also
    matches any investment_keyword, the row stays an expense (investment deposits
    are handled separately by _auto_label_investment_income).

    Rows already marked user_corrected=1 are never touched.
    """
    try:
        with engine.connect() as conn:
            inc_kws_raw = [r[0] for r in conn.execute(text(
                'SELECT keyword FROM income_keywords'
            )).fetchall()]
            inv_kws_raw = [r[0] for r in conn.execute(text(
                'SELECT keyword FROM investment_keywords'
            )).fetchall()]
        if not inc_kws_raw:
            return 0

        # Pre-compile patterns; skip any that are invalid regex.
        def _compile_safe(kws: list, label: str) -> list:
            compiled = []
            for kw in kws:
                try:
                    compiled.append(re.compile(kw, re.IGNORECASE))
                except re.error as _re_exc:
                    logger.warning(
                        f'_apply_income_keywords: skipping invalid {label} pattern '
                        f'"{kw}": {_re_exc}'
                    )
            return compiled

        inc_patterns = _compile_safe(inc_kws_raw, 'income')
        inv_patterns = _compile_safe(inv_kws_raw, 'investment')

        if not inc_patterns:
            return 0

        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT tx_hash, place FROM transactions "
                "WHERE report_month=:m AND tx_type='expense' AND user_corrected=0"
            ), {'m': month}).fetchall()
            promoted = 0
            for tx_hash, place in rows:
                mk = _normalize_merchant_key(place)
                # Investment platform keywords take priority — never promote to income
                if inv_patterns and any(p.search(mk) for p in inv_patterns):
                    continue
                if any(p.search(mk) for p in inc_patterns):
                    conn.execute(text(
                        "UPDATE transactions SET tx_type='income', label='recurring' "
                        "WHERE tx_hash=:h"
                    ), {'h': tx_hash})
                    promoted += 1
            if promoted:
                conn.commit()
        if promoted:
            logger.info(f'_apply_income_keywords: promoted {promoted} row(s) to income for {month}')
        return promoted
    except Exception as exc:
        logger.warning(f'_apply_income_keywords: {exc}')
        return 0


def _auto_label_investment_income(engine, month: str) -> int:
    """
    For income rows in *month* whose place matches an investment platform keyword,
    set label='investment_transfer' and category='Investment' if not user-corrected.
    Prevents investment deposits from being labelled 'recurring' (Regular income).
    """
    try:
        inv_kws = _load_investment_keywords_from_db(engine)
        if not inv_kws:
            return 0
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT tx_hash, place FROM transactions "
                "WHERE report_month=:m AND tx_type='income' AND user_corrected=0"
            ), {'m': month}).fetchall()
            updated = 0
            for tx_hash, place in rows:
                mk = _normalize_merchant_key(place)
                if any(kw in mk for kw in inv_kws):
                    conn.execute(text(
                        "UPDATE transactions SET label='investment_transfer', category='Investment' "
                        "WHERE tx_hash=:h"
                    ), {'h': tx_hash})
                    updated += 1
            if updated:
                conn.commit()
        return updated
    except Exception as exc:
        logger.warning(f'_auto_label_investment_income: {exc}')
        return 0


def log_auto_deleted(engine, place: str, amount: float, tx_date: str,
                     report_month: str, reason: str, keyword_matched: str = '',
                     tx_type: str = '', category: str = '',
                     original_statement: str = '') -> None:
    """Record a transaction that was auto-deleted during processing.

    De-duplication rules:
    - manual_delete: keyed by (place_normalized, amount, report_month, reason) — one row per
      unique deletion instance so each can be individually restored from the Settings tab.
    - all other reasons: keyed by (place_normalized, amount, reason) with occurrence_count.

    For same-month re-process of either type, the existing row is refreshed in-place
    without inflating the counter.

    tx_type, category, original_statement are stored for manual_delete entries so
    the transaction can be fully restored from the Settings tab.
    """
    from datetime import datetime as _dt
    place_norm = _normalize_merchant_key(place)
    place_wl_norm = _normalize_whitelist_key(place)  # date/time-stripped for cross-month dedup
    now = _dt.now().isoformat()[:19]
    try:
        with engine.connect() as conn:
            # manual_delete: each unique (place, amount, month) is its own restorable instance
            if reason == 'manual_delete':
                row = conn.execute(text(
                    'SELECT id, whitelisted, seen_months FROM auto_deleted_transactions '
                    'WHERE place_normalized=:pn AND ROUND(COALESCE(amount,0),2)=ROUND(:amt,2) '
                    'AND report_month=:rm AND reason=:r'
                ), {'pn': place_norm, 'amt': float(amount or 0), 'rm': report_month, 'r': reason}).fetchone()
            else:
                # Try date-stripped key first so recurring transfers with varying date/time
                # in their description aggregate to one record across months.
                row = conn.execute(text(
                    'SELECT id, whitelisted, seen_months FROM auto_deleted_transactions '
                    'WHERE place_normalized=:pn AND ROUND(COALESCE(amount,0),2)=ROUND(:amt,2) AND reason=:r'
                ), {'pn': place_wl_norm, 'amt': float(amount or 0), 'r': reason}).fetchone()
                if not row and place_wl_norm != place_norm:
                    # Fallback: exact key — finds records written before this fix was applied
                    row = conn.execute(text(
                        'SELECT id, whitelisted, seen_months FROM auto_deleted_transactions '
                        'WHERE place_normalized=:pn AND ROUND(COALESCE(amount,0),2)=ROUND(:amt,2) AND reason=:r'
                    ), {'pn': place_norm, 'amt': float(amount or 0), 'r': reason}).fetchone()
                # New records use the stripped key so all months map to the same entry
                place_norm = place_wl_norm

            if row:
                if row[1]:  # whitelisted — never re-record
                    return
                seen = json.loads(row[2] or '[]') if row[2] else []
                if report_month and report_month in seen:
                    # Same month re-process: refresh display fields; update restore data if provided
                    conn.execute(text(
                        'UPDATE auto_deleted_transactions '
                        'SET last_seen=:ls, place_display=:pd, keyword_matched=:km, '
                        '    tx_type=COALESCE(NULLIF(:ttype,""), tx_type), '
                        '    category=COALESCE(NULLIF(:cat,""), category), '
                        '    original_statement=COALESCE(NULLIF(:stmt,""), original_statement) '
                        'WHERE id=:id'
                    ), {'ls': now, 'pd': place, 'km': keyword_matched,
                        'ttype': tx_type, 'cat': category, 'stmt': original_statement,
                        'id': row[0]})
                else:
                    # New month (or no month) — increment count and record month
                    if report_month:
                        seen.append(report_month)
                    conn.execute(text(
                        'UPDATE auto_deleted_transactions '
                        'SET occurrence_count=occurrence_count+1, last_seen=:ls, '
                        '    place_display=:pd, keyword_matched=:km, seen_months=:sm, '
                        '    tx_type=COALESCE(NULLIF(:ttype,""), tx_type), '
                        '    category=COALESCE(NULLIF(:cat,""), category), '
                        '    original_statement=COALESCE(NULLIF(:stmt,""), original_statement) '
                        'WHERE id=:id'
                    ), {'ls': now, 'pd': place, 'km': keyword_matched,
                        'sm': json.dumps(seen), 'ttype': tx_type, 'cat': category,
                        'stmt': original_statement, 'id': row[0]})
            else:
                conn.execute(text(
                    'INSERT INTO auto_deleted_transactions '
                    '(place_normalized, place_display, amount, tx_date, report_month, '
                    'reason, keyword_matched, first_seen, last_seen, occurrence_count, whitelisted, seen_months, '
                    'tx_type, category, original_statement) '
                    'VALUES (:pn, :pd, :amt, :dt, :rm, :r, :km, :fs, :ls, 1, 0, :sm, :ttype, :cat, :stmt)'
                ), {'pn': place_norm, 'pd': place, 'amt': float(amount or 0),
                    'dt': tx_date, 'rm': report_month, 'r': reason, 'km': keyword_matched,
                    'fs': now, 'ls': now, 'sm': json.dumps([report_month] if report_month else []),
                    'ttype': tx_type, 'cat': category, 'stmt': original_statement})
            conn.commit()
    except Exception as exc:
        logger.warning(f'log_auto_deleted: {exc}')


def is_whitelisted(engine, place: str, reason: str = '') -> bool:
    """Return True if the normalized place is whitelisted from auto-deletion for *reason*.
    If *reason* is empty, returns True if whitelisted for ANY reason.
    """
    place_norm = _normalize_merchant_key(place)
    try:
        with engine.connect() as conn:
            if reason:
                row = conn.execute(text(
                    'SELECT whitelisted FROM auto_deleted_transactions '
                    'WHERE place_normalized=:pn AND reason=:r'
                ), {'pn': place_norm, 'r': reason}).fetchone()
            else:
                row = conn.execute(text(
                    'SELECT whitelisted FROM auto_deleted_transactions '
                    'WHERE place_normalized=:pn AND whitelisted=1 LIMIT 1'
                ), {'pn': place_norm}).fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def get_auto_deleted_transactions(engine) -> list:
    """Return all auto_deleted_transactions rows as dicts, newest last_seen first."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                'SELECT id, place_normalized, place_display, amount, tx_date, report_month, '
                'reason, keyword_matched, first_seen, last_seen, occurrence_count, whitelisted, '
                'COALESCE(seen_months, \'[]\'  ) AS seen_months '
                'FROM auto_deleted_transactions ORDER BY last_seen DESC'
            )).fetchall()
        return [
            {
                'id': r[0], 'place_normalized': r[1], 'place_display': r[2],
                'amount': r[3], 'tx_date': r[4], 'report_month': r[5],
                'reason': r[6], 'keyword_matched': r[7], 'first_seen': r[8],
                'last_seen': r[9], 'occurrence_count': r[10], 'whitelisted': bool(r[11]),
                'seen_months': json.loads(r[12]) if r[12] else ([r[5]] if r[5] else []),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning(f'get_auto_deleted_transactions: {exc}')
        return []


def set_auto_deleted_whitelist(engine, record_id: int, whitelisted: bool) -> bool:
    """Toggle the whitelisted flag for a given auto_deleted_transactions row.
    Returns True on success.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(
                'UPDATE auto_deleted_transactions SET whitelisted=:w WHERE id=:id'
            ), {'w': int(whitelisted), 'id': record_id})
            conn.commit()
        return True
    except Exception as exc:
        logger.warning(f'set_auto_deleted_whitelist: {exc}')
        return False


def delete_auto_deleted_record(engine, record_id: int) -> bool:
    """Remove an auto_deleted_transactions row entirely."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                'DELETE FROM auto_deleted_transactions WHERE id=:id'
            ), {'id': record_id})
            conn.commit()
        return True
    except Exception as exc:
        logger.warning(f'delete_auto_deleted_record: {exc}')
        return False


# ── whitelisted places loader (used by process_monthly / parser) ─────────────

def get_whitelisted_places(engine, reason: str = '') -> set:
    """Return the set of normalized place names that are whitelisted.
    Optionally filter by *reason* (e.g. 'transfer_keyword', 'cross_account').

    Returns BOTH the stored keys and their date/time-stripped variants so that
    a whitelist entry created from a January occurrence also protects February's
    transaction even when the description contains a varying date/time stamp.
    """
    try:
        with engine.connect() as conn:
            if reason:
                rows = conn.execute(text(
                    'SELECT place_normalized FROM auto_deleted_transactions '
                    'WHERE whitelisted=1 AND reason=:r'
                ), {'r': reason}).fetchall()
            else:
                rows = conn.execute(text(
                    'SELECT place_normalized FROM auto_deleted_transactions WHERE whitelisted=1'
                )).fetchall()
        raw_keys = {r[0] for r in rows}
        # Include date-stripped variants for cross-month matching
        return raw_keys | {_normalize_whitelist_key(k) for k in raw_keys}
    except Exception:
        return set()


def _clear_auto_filter_for_month(engine, month: str) -> None:
    """Reset auto-filter tracking for *month* before reprocessing it.

    Strips *month* from the seen_months list of every auto_deleted_transactions
    record that includes it, and decrements occurrence_count accordingly:
    - Non-manual_delete records are deleted entirely if seen_months becomes empty.
    - manual_delete records are kept (even with empty seen_months) so that
      _auto_apply_manual_deletes can still propagate them into the fresh run.

    This ensures force-reprocessing a month never inflates occurrence counts —
    the month is re-logged cleanly by the processing pipeline that follows.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, reason, seen_months, occurrence_count, whitelisted "
                "FROM auto_deleted_transactions"
            )).fetchall()
            for row_id, reason, seen_months_json, occ, is_whitelisted_flag in rows:
                seen = json.loads(seen_months_json or '[]') if seen_months_json else []
                if month not in seen:
                    continue
                seen.remove(month)
                new_occ = max(0, (occ or 1) - 1)
                if not seen and reason != 'manual_delete' and not is_whitelisted_flag:
                    # Non-whitelisted, non-manual records with no remaining months are safe to delete
                    conn.execute(text(
                        "DELETE FROM auto_deleted_transactions WHERE id=:id"
                    ), {'id': row_id})
                else:
                    # Whitelisted records are NEVER deleted — they represent a permanent user decision.
                    # manual_delete records are kept even with empty seen_months for future propagation.
                    conn.execute(text(
                        "UPDATE auto_deleted_transactions "
                        "SET seen_months=:sm, occurrence_count=:oc WHERE id=:id"
                    ), {'sm': json.dumps(seen), 'oc': new_occ, 'id': row_id})
            conn.commit()
    except Exception as exc:
        logger.warning(f'_clear_auto_filter_for_month: {exc}')


def _auto_apply_manual_deletes(engine, month: str) -> int:
    """
    For every non-whitelisted 'manual_delete' entry in auto_deleted_transactions,
    find transactions in *month* with the same normalized place name and delete them
    (user_corrected rows are always preserved).

    This propagates a one-time user deletion forward into every future month so
    the user never has to manually delete the same recurring transaction again.
    Deleting or whitelisting the entry in the Settings tab stops the propagation.

    Returns the number of rows deleted.
    """
    try:
        with engine.connect() as conn:
            # Only propagate merchants that have NO whitelisted instance —
            # with per-instance rows, whitelisting any one instance of a merchant
            # signals that the user wants auto-deletion stopped for that merchant.
            entries = conn.execute(text(
                "SELECT DISTINCT place_normalized, place_display "
                "FROM auto_deleted_transactions "
                "WHERE reason='manual_delete' AND whitelisted=0 "
                "AND place_normalized NOT IN ("
                "  SELECT place_normalized FROM auto_deleted_transactions "
                "  WHERE reason='manual_delete' AND whitelisted=1"
                ")"
            )).fetchall()
        if not entries:
            return 0

        manual_places = {row[0]: (row[1] or row[0]) for row in entries}

        with engine.connect() as conn:
            txns = conn.execute(text(
                "SELECT tx_hash, place, amount, tx_date, tx_type, category, statement FROM transactions "
                "WHERE report_month=:m AND user_corrected=0"
            ), {'m': month}).fetchall()

        to_delete = [
            (tx_hash, place, amount, tx_date, tx_type, category, statement)
            for tx_hash, place, amount, tx_date, tx_type, category, statement in txns
            if _normalize_merchant_key(place) in manual_places
        ]

        if to_delete:
            with engine.connect() as conn:
                for tx_hash, *_ in to_delete:
                    conn.execute(text("DELETE FROM transactions WHERE tx_hash=:h"), {'h': tx_hash})
                conn.commit()
            for _, place, amount, tx_date, tx_type, category, statement in to_delete:
                log_auto_deleted(
                    engine, place, float(amount or 0), str(tx_date or ''),
                    month, 'manual_delete', '',
                    tx_type=str(tx_type or ''),
                    category=str(category or ''),
                    original_statement=str(statement or ''),
                )
            logger.info(f"_auto_apply_manual_deletes: removed {len(to_delete)} row(s) for {month}")

        return len(to_delete)
    except Exception as exc:
        logger.warning(f'_auto_apply_manual_deletes: {exc}')
        return 0


def _auto_learn_keywords(engine, current_month: str) -> dict:
    """
    Scan committed transactions from months prior to *current_month* and
    automatically learn new keyword entries so future imports self-classify.

    Rules
    -----
    investment_keywords (source='learned'):
        Any income row with label='investment_transfer' in any prior month whose
        normalised merchant key is not already covered by an existing keyword.
        One confirmed investment labelling is enough (intentional, explicit).

    income_keywords (source='learned'):
        Income rows with label='recurring' that appear in ≥2 distinct prior
        months for the same normalised merchant key, AND are not already covered.
        Requiring ≥2 months avoids locking in one-off deposits as perpetual income.

    transfer/payment_app/ignore keywords are NOT learned — they match raw bank-
    text patterns, not merchant names, so learning them here would be noisy.
    """
    try:
        with engine.connect() as conn:
            inv_kws = [r[0] for r in conn.execute(text(
                'SELECT keyword FROM investment_keywords'
            )).fetchall()]
            inc_kws = [r[0] for r in conn.execute(text(
                'SELECT keyword FROM income_keywords'
            )).fetchall()]

            # All income rows from prior months (exclude current)
            prior_income = conn.execute(text(
                "SELECT place, label, report_month FROM transactions "
                "WHERE tx_type='income' AND report_month < :m AND user_corrected=1 "
                "ORDER BY report_month"
            ), {'m': current_month}).fetchall()

        # ── Investment keywords ──────────────────────────────────────────────
        inv_learned = set()
        for place, label, _ in prior_income:
            if (label or '').lower() == 'investment_transfer':
                mk = _normalize_merchant_key(place)
                if mk and not any(kw in mk for kw in inv_kws):
                    inv_learned.add(mk)

        # ── Income keywords (≥2 months) ──────────────────────────────────────
        from collections import defaultdict
        recurring_months: dict = defaultdict(set)
        for place, label, rmonth in prior_income:
            if (label or '').strip().lower() in ('recurring', ''):
                mk = _normalize_merchant_key(place)
                if mk:
                    recurring_months[mk].add(rmonth)
        # Exclude from income learning: already covered by an income keyword OR
        # matches an investment platform keyword (investment deposits must never
        # be auto-promoted as regular income).
        inc_learned = {
            mk for mk, months in recurring_months.items()
            if len(months) >= 2
            and not any(re.search(kw, mk, re.IGNORECASE) for kw in inc_kws)
            and not any(re.search(kw, mk, re.IGNORECASE) for kw in inv_kws)
        }

        inserted_inv = inserted_inc = 0
        with engine.connect() as conn:
            for kw in inv_learned:
                conn.execute(text(
                    "INSERT OR IGNORE INTO investment_keywords (keyword, source) "
                    "VALUES (:kw, 'learned')"
                ), {'kw': kw})
                inserted_inv += 1
            for kw in inc_learned:
                conn.execute(text(
                    "INSERT OR IGNORE INTO income_keywords (keyword, source) "
                    "VALUES (:kw, 'learned')"
                ), {'kw': kw})
                inserted_inc += 1
            if inserted_inv or inserted_inc:
                conn.commit()

        if inserted_inv:
            logger.info(f'_auto_learn_keywords: learned {inserted_inv} investment keyword(s): {sorted(inv_learned)}')
        if inserted_inc:
            logger.info(f'_auto_learn_keywords: learned {inserted_inc} income keyword(s): {sorted(inc_learned)}')
        return {'investment': inserted_inv, 'income': inserted_inc}
    except Exception as exc:
        logger.warning(f'_auto_learn_keywords: {exc}')
        return {'investment': 0, 'income': 0}


def write_month_to_db(engine,
                      month: str,
                      expenses_df=None,
                      income_df=None,
                      source_statement: str = None) -> int:
    """
    Write pre-processed DataFrames for a calendar month directly to the DB,
    preserving any rows the user has manually corrected (user_corrected=True).

    Only the tx_types present in the supplied DataFrames are replaced.
    For example, passing only expenses_df=df leaves existing income rows
    for the month untouched.

    source_statement: when provided (the statement folder month, e.g. '2024-08'),
    the cleanup deletes ALL existing rows that came from that statement folder
    regardless of which report_month they ended up in.  This is the key to
    preventing cross-month duplicates when an August PDF contains July transactions.

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

    # When expenses are replaced, also clear any stale non-user_corrected income
    # rows for the same month.  Income rows whose merchant rule was deleted would
    # otherwise survive indefinitely because the parser no longer writes income_df.
    # _apply_merchant_rules() (called below) will re-classify the appropriate
    # expense rows back to income after the fresh write.
    if 'expense' in types_to_replace and 'income' not in types_to_replace:
        types_to_replace.append('income')

    combined  = pd.concat(frames, ignore_index=True)
    # Stamp every row with the source_statement if one was supplied.
    # If source_statement is not given (aggregate mode), preserve whatever
    # value is already in the DataFrame (read from the DB).
    if source_statement is not None:
        combined['source_statement'] = source_statement
    normalised = _normalise(combined)

    # ── User-corrected row preservation ──────────────────────────────────────
    # When source_statement is provided, snapshot corrections from the WHOLE
    # statement (across all report_months) so cross-month rows (e.g. July
    # transactions in an August PDF) survive the wider delete below.
    type_placeholders = ','.join(f"'{t}'" for t in types_to_replace)
    _scope_col = 'source_statement' if source_statement else 'report_month'
    _scope_val = source_statement if source_statement else month
    with engine.connect() as conn:
        uc_rows = conn.execute(text(
            f"SELECT tx_hash, category, label, place, amount, tx_date FROM transactions "
            f"WHERE {_scope_col}=:sv AND user_corrected=1 AND tx_type IN ({type_placeholders})"
        ), {'sv': _scope_val}).fetchall()
        uc_map = {r[0]: {'category': r[1], 'label': r[2], 'place': r[3],
                         'amount': r[4], 'tx_date': r[5]} for r in uc_rows}

        if source_statement:
            # Wipe cross-month rows from this statement folder first, then
            # also wipe the target report_month (cleans NULL-source legacy rows).
            for tx_type in types_to_replace:
                conn.execute(text(
                    "DELETE FROM transactions WHERE source_statement=:ss AND tx_type=:t"
                ), {'ss': source_statement, 't': tx_type})
        for tx_type in types_to_replace:
            conn.execute(text(
                "DELETE FROM transactions WHERE report_month=:m AND tx_type=:t"
            ), {'m': month, 't': tx_type})
        conn.commit()

    # Use INSERT OR REPLACE so a re-process run never fails with UNIQUE constraint
    # errors if any stale rows survived the DELETE above (e.g. after a prior
    # aggregate_monthly crash left orphan records in the DB).
    if not normalised.empty:
        cols = list(normalised.columns)
        col_list = ', '.join(cols)
        placeholders = ', '.join(f':{c}' for c in cols)
        sql = f'INSERT OR REPLACE INTO transactions ({col_list}) VALUES ({placeholders})'
        rows = normalised.to_dict(orient='records')
        with engine.connect() as conn:
            conn.execute(text(sql), rows)
            conn.commit()

    # Re-apply user corrections that survived the wipe.
    # Try by tx_hash first; fall back to (tx_date, place, amount) because the
    # hash changes when report_month changes (cross-month transaction moved by
    # aggregate) or when tx_type changes (expense→income reclassification).
    if uc_map:
        with engine.connect() as conn:
            for tx_hash, corr in uc_map.items():
                res = conn.execute(text(
                    "UPDATE transactions SET "
                    "  category=COALESCE(:cat, category), "
                    "  label=COALESCE(:lbl, label), "
                    "  place=COALESCE(:pl, place), "
                    "  amount=COALESCE(:amt, amount), "
                    "  user_corrected=1 "
                    "WHERE tx_hash=:h"
                ), {'cat': corr['category'], 'lbl': corr['label'],
                    'pl': corr['place'], 'amt': corr.get('amount'),
                    'h': tx_hash})
                if res.rowcount == 0:
                    # Hash mismatch — tx moved to a different report_month.
                    # Restore by (tx_date, place, amount) which are immutable.
                    tx_date = corr.get('tx_date')
                    if tx_date:
                        conn.execute(text(
                            "UPDATE transactions SET "
                            "  category=COALESCE(:cat, category), "
                            "  label=COALESCE(:lbl, label), "
                            "  user_corrected=1 "
                            "WHERE tx_date=:d "
                            "  AND UPPER(place)=UPPER(:pl) "
                            "  AND ROUND(amount,2)=ROUND(:amt,2)"
                        ), {'cat': corr['category'], 'lbl': corr['label'],
                            'pl': corr['place'], 'amt': corr.get('amount'),
                            'd': tx_date})
                    else:
                        # Legacy fallback for rows without tx_date in snapshot
                        conn.execute(text(
                            "UPDATE transactions SET "
                            "  category=COALESCE(:cat, category), "
                            "  label=COALESCE(:lbl, label), "
                            "  user_corrected=1 "
                            "WHERE report_month=:m "
                            "  AND UPPER(place)=UPPER(:pl) "
                            "  AND ROUND(amount,2)=ROUND(:amt,2)"
                        ), {'cat': corr['category'], 'lbl': corr['label'],
                            'pl': corr['place'], 'amt': corr.get('amount'),
                            'm': month})
            conn.commit()

    keywords = _load_investment_keywords_from_db(engine)
    _sync_merchant_metadata(engine, keywords, normalised['place'].dropna().tolist())
    _auto_learn_keywords(engine, month)
    _apply_merchant_rules(engine, month)
    _apply_income_keywords(engine, month)
    _auto_label_investment_income(engine, month)
    _auto_mark_bank_transfers(engine, month)
    _auto_categorize_credits(engine, month)
    _auto_apply_manual_deletes(engine, month)

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
