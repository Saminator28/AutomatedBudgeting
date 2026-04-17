"""deps.py — Shared state and utility functions for the Automated Budgeting backend.

Imported by all route modules to access:
  - Database connectivity  (get_engine, _DB_AVAILABLE)
  - Path constants         (_PROJECT_ROOT, _CONFIG_ROOT, _DATA_ROOT, _STATEMENTS_BASE)
  - Background job store   (_jobs, _jobs_lock)
  - Keyword lists          (_INVESTMENT_PLATFORM_KEYWORDS, _INCOME_KEYWORDS, …)
  - Reload helpers         (_reload_investment_keywords, …)
  - Data access utility    (_query_df)
  - Validation helpers     (_is_valid_month, _safe_statement_path)
  - Domain logic           (_rebuild_transfers_for_month, _update_csv_label)

Keyword lists are mutated in-place by their respective reload functions so that
any module which imported the list directly always sees the current values.
"""

import sys
import re
import logging
import json as _json
import threading
import os
from pathlib import Path

import pandas as pd

# ── Path / project-root setup ─────────────────────────────────────────────────
_BACKEND_DIR  = Path(__file__).parent                        # …/src/ui/backend/
_PROJECT_ROOT = _BACKEND_DIR.parent.parent.parent            # repo root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Database ──────────────────────────────────────────────────────────────────
try:
    from src.database.session import get_engine                              # type: ignore
    from src.database.db_utils import write_month_to_db, write_transfers_to_db  # type: ignore
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    get_engine            = None  # type: ignore
    write_transfers_to_db = None  # type: ignore
    logging.warning("SQLAlchemy not installed — DB features disabled (pip install sqlalchemy)")

# ── Runtime paths ─────────────────────────────────────────────────────────────
_CONFIG_ROOT     = _PROJECT_ROOT / "config"
_DATA_ROOT       = _BACKEND_DIR.parent / "data"         # …/src/ui/data/
_DATA_ROOT.mkdir(parents=True, exist_ok=True)
_STATEMENTS_BASE = _DATA_ROOT / "statements"
_WRITE_API_KEY   = os.environ.get("AUTOBUDGET_API_KEY", "").strip()

# ── Background job store ──────────────────────────────────────────────────────
_jobs: dict      = {}   # job_id → {status, output, errors, started_at}
_jobs_lock       = threading.Lock()

# ── Keyword lists (mutated in-place so direct imports stay current) ───────────
_INVESTMENT_PLATFORM_KEYWORDS: list = []
_INCOME_KEYWORDS:         list = []
_IGNORE_KEYWORDS:         list = []
_PAYMENT_APP_KEYWORDS:    list = []
_TRANSFER_KEYWORDS:       list = []

# ── Investment category set ───────────────────────────────────────────────────
_INVESTMENT_CATEGORIES = {'Investment', 'Investment Transfer'}


# ── Keyword reload functions ──────────────────────────────────────────────────

def _reload_investment_keywords() -> None:
    """Re-populate _INVESTMENT_PLATFORM_KEYWORDS from the DB (in-place)."""
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM investment_keywords ORDER BY keyword')).fetchall()
        _INVESTMENT_PLATFORM_KEYWORDS[:] = [r[0] for r in rows]
    except Exception as exc:
        logging.warning(f'Could not reload investment keywords: {exc}')


def _reload_income_keywords() -> None:
    """Re-populate _INCOME_KEYWORDS from the DB (in-place, uppercased)."""
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM income_keywords ORDER BY keyword')).fetchall()
        _INCOME_KEYWORDS[:] = [r[0].upper() for r in rows]
    except Exception as exc:
        logging.warning(f'Could not reload income keywords: {exc}')


def _reload_ignore_keywords() -> None:
    """Re-populate _IGNORE_KEYWORDS from the DB (in-place, uppercased)."""
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM ignore_keywords ORDER BY keyword')).fetchall()
        _IGNORE_KEYWORDS[:] = [r[0].upper() for r in rows]
    except Exception as exc:
        logging.warning(f'Could not reload ignore keywords: {exc}')


def _reload_payment_app_keywords() -> None:
    """Re-populate _PAYMENT_APP_KEYWORDS from the DB (in-place, uppercased)."""
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM payment_app_keywords ORDER BY keyword')).fetchall()
        _PAYMENT_APP_KEYWORDS[:] = [r[0].upper() for r in rows]
    except Exception as exc:
        logging.warning(f'Could not reload payment app keywords: {exc}')


def _reload_transfer_keywords() -> None:
    """Re-populate _TRANSFER_KEYWORDS from the DB (in-place, uppercased)."""
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM transfer_keywords ORDER BY keyword')).fetchall()
        _TRANSFER_KEYWORDS[:] = [r[0].upper() for r in rows]
    except Exception as exc:
        logging.warning(f'Could not reload transfer keywords: {exc}')


# ── Validation helpers ────────────────────────────────────────────────────────

def _is_valid_month(month: str) -> bool:
    return bool(re.match(r'^\d{4}-\d{2}$', str(month or '').strip()))


def _safe_statement_path(month: str, filename: str) -> Path:
    if not _is_valid_month(month):
        raise ValueError('Month must be YYYY-MM format')
    clean_name = Path(str(filename or '')).name
    if not clean_name or clean_name in ('.', '..'):
        raise ValueError('Invalid filename')
    if clean_name != str(filename):
        raise ValueError('Filename must not contain path separators')
    month_dir = (_STATEMENTS_BASE / month).resolve()
    month_dir.mkdir(parents=True, exist_ok=True)
    target = (month_dir / clean_name).resolve()
    if month_dir not in target.parents:
        raise ValueError('Invalid file path')
    return target


# ── Data access ───────────────────────────────────────────────────────────────

def _query_df(tx_type: str, months: list = None, recent_n: int = None, date_months: list = None, exclude_one_time: bool = False) -> pd.DataFrame:
    """Load transactions from the DB as a CSV-compatible DataFrame.

    Column mapping: tx_date→'Transaction Date', place→'Place', amount→'Amount',
                    category→'category', label→'Label', statement→'Statement',
                    report_month→'month'.
    Returns an empty DataFrame if DB is unavailable or no rows match.
    """
    if not _DB_AVAILABLE:
        return pd.DataFrame()
    from sqlalchemy import text as _text
    _eng = get_engine()
    _months = months
    if recent_n is not None and _months is None:
        with _eng.connect() as conn:
            _months = [
                r[0] for r in conn.execute(_text(
                    "SELECT DISTINCT report_month FROM transactions "
                    "WHERE tx_type=:t ORDER BY report_month DESC LIMIT :n"
                ), {'t': tx_type, 'n': recent_n}).fetchall()
            ]
        if not _months:
            return pd.DataFrame()
    q = (
        "SELECT tx_date, place, amount, category, label, statement, report_month "
        "FROM transactions WHERE tx_type=:t"
    )
    params: dict = {'t': tx_type}
    if _months:
        phs = ','.join(f':m{i}' for i in range(len(_months)))
        q += f' AND report_month IN ({phs})'
        for i, m in enumerate(_months):
            params[f'm{i}'] = m
    if date_months:
        # Filter by the calendar month of the actual transaction date.
        # tx_date may be stored as zero-padded MM/DD/YYYY or non-padded M/D/YYYY,
        # so derive YYYY-MM robustly: year = last 4 chars; month = chars before
        # the first '/' cast to int then zero-padded via printf.
        phs = ','.join(f':dm{i}' for i in range(len(date_months)))
        q += (
            " AND INSTR(tx_date, '/') > 0"
            " AND ("
            "SUBSTR(tx_date, LENGTH(tx_date) - 3, 4) || '-' || "
            "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date, '/') - 1) AS INTEGER))"
            f") IN ({phs})"
        )
        for i, m in enumerate(date_months):
            params[f'dm{i}'] = m
    if exclude_one_time:
        q += " AND (label IS NULL OR label != 'one-time')"
    q += ' ORDER BY report_month, tx_date'
    with _eng.connect() as conn:
        rows = conn.execute(_text(q), params).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        rows,
        columns=['Transaction Date', 'Place', 'Amount', 'category', 'Label', 'Statement', 'month'],
    )
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    return df


# ── CSV label helper ──────────────────────────────────────────────────────────

def _update_csv_label(csv_path: Path, date: str, place: str, amount: float, new_label: str) -> bool:
    """Find the matching row in a statement CSV and update its Label column in-place."""
    try:
        df = pd.read_csv(csv_path)
        if 'Label' not in df.columns:
            df['Label'] = 'recurring'
        matched = False
        for idx, row in df.iterrows():
            try:
                row_amount = round(float(row.get('Amount', 0)), 2)
            except Exception:
                continue
            if (
                str(row.get('Transaction Date', '')).strip() == date.strip()
                and str(row.get('Place', '')).strip().upper() == place.strip().upper()
                and row_amount == round(amount, 2)
            ):
                df.at[idx, 'Label'] = new_label
                matched = True
        if matched:
            df.to_csv(csv_path, index=False)
        return matched
    except Exception as exc:
        logging.warning(f'_update_csv_label failed on {csv_path}: {exc}')
        return False


# ── Transfer rebuild ──────────────────────────────────────────────────────────

def _rebuild_transfers_for_month(month: str) -> None:
    """Rebuild the DB transfers table for a single month.

    Sources (priority order):
      1. statements/*/transfers.csv — raw brokerage transfer rows
      2. DB expense rows with category in _INVESTMENT_CATEGORIES → Direction=Out
      3. DB income rows tagged 'Investment Return' or matching investment platform
         keywords → Direction=In
    """
    raw_rows: list = []

    # 1. Raw statement transfer CSVs
    for stmt_dir in sorted(_STATEMENTS_BASE.glob('*')):
        t_file = stmt_dir / 'transfers.csv'
        if not t_file.exists():
            continue
        try:
            df = pd.read_csv(t_file)
            if df.empty:
                continue
            df['_pdate'] = pd.to_datetime(df['Transaction Date'], format='mixed', errors='coerce')
            df['_month'] = df['_pdate'].dt.strftime('%Y-%m')
            df = df[df['_month'] == month].drop(columns=['_pdate', '_month'])
            if 'Place_Original' in df.columns:
                df = df.drop(columns=['Place_Original'])
            if not df.empty:
                raw_rows.append(df)
        except Exception as exc:
            logging.warning(f'Could not read {t_file}: {exc}')

    # 2 & 3. Pull investment rows from DB
    non_investment_keys: set = set()
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            _eng = get_engine()
            with _eng.connect() as conn:
                exp_rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, statement, category FROM transactions "
                    "WHERE tx_type='expense' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND ("
                    "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER))"
                    ")=:m"
                ), {'m': month}).fetchall()
                inv_expenses = [r for r in exp_rows if str(r[4] or '').strip() in _INVESTMENT_CATEGORIES]
                non_inv = [r for r in exp_rows if str(r[4] or '').strip() not in _INVESTMENT_CATEGORIES]
                for r in non_inv:
                    try:
                        non_investment_keys.add((str(r[0]).strip(), round(float(r[2] or 0), 2)))
                    except Exception:
                        pass
                if inv_expenses:
                    raw_rows.append(pd.DataFrame([{
                        'Transaction Date': r[0], 'Place': r[1],
                        'Amount': abs(float(r[2] or 0)), 'Direction': 'Out',
                        'Statement': r[3] or 'Manual',
                    } for r in inv_expenses]))

                inc_rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, statement, category, label FROM transactions "
                    "WHERE tx_type='income' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND ("
                    "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER))"
                    ")=:m"
                ), {'m': month}).fetchall()
                for r in inc_rows:
                    is_tagged            = str(r[4] or '').strip() == 'Investment Return'
                    is_platform          = any(kw in str(r[1] or '').lower() for kw in _INVESTMENT_PLATFORM_KEYWORDS)
                    is_investment_label  = str(r[5] or '').strip() == 'investment_transfer'
                    if is_tagged or is_platform or is_investment_label:
                        raw_rows.append(pd.DataFrame([{
                            'Transaction Date': r[0], 'Place': r[1],
                            'Amount': float(r[2] or 0), 'Direction': 'In',
                            'Statement': r[3] or 'Manual',
                        }]))
        except Exception as exc:
            logging.warning(f'DB query for transfers rebuild failed: {exc}')

    # Remove rows re-categorised as non-investment
    if non_investment_keys and raw_rows:
        filtered = []
        for df_chunk in raw_rows:
            def _key(r):
                try:
                    return (str(r['Transaction Date']).strip(), round(float(r['Amount']), 2))
                except Exception:
                    return None
            keep = df_chunk.apply(lambda r: _key(r) not in non_investment_keys, axis=1)
            filtered.append(df_chunk[keep])
        raw_rows = filtered

    # Write to DB transfers table
    if _DB_AVAILABLE:
        try:
            if not raw_rows:
                write_transfers_to_db(get_engine(), month, [])
                return
            combined = pd.concat(raw_rows, ignore_index=True)
            dedup_cols = [c for c in combined.columns if c not in ('Source', 'Statement')]
            combined = combined.drop_duplicates(subset=dedup_cols, keep='first')
            combined = combined.sort_values('Transaction Date')
            rows_list = [
                {
                    'tx_date':   str(r.get('Transaction Date', '')),
                    'place':     str(r.get('Place', '')),
                    'amount':    float(r.get('Amount', 0) or 0),
                    'direction': str(r.get('Direction', 'Out')),
                    'statement': str(r.get('Statement', '')),
                }
                for _, r in combined.iterrows()
            ]
            write_transfers_to_db(get_engine(), month, rows_list)
            logging.info(f'Rebuilt transfers for {month}: {len(rows_list)} row(s)')
        except Exception as exc:
            logging.warning(f'DB write for transfers failed: {exc}')
