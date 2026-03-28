"""routes/expenses.py — Expense browse, edit, manual transactions, and category endpoints."""

import re
import logging
import json as _json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _DB_AVAILABLE, get_engine,
    _DATA_ROOT, _CONFIG_ROOT, _STATEMENTS_BASE,
    _query_df,
    _update_csv_label,
    _rebuild_transfers_for_month,
    _INVESTMENT_CATEGORIES,
)

router = APIRouter()

_MANUAL_TRANSACTIONS_FILE = _DATA_ROOT / "manual_transactions.json"


# ── One-time expenses ─────────────────────────────────────────────────────────

@router.get("/api/one-time-expenses")
def get_one_time_expenses():
    """Return all expense rows labelled one-time from all available months."""
    df = _query_df('expense')
    if df.empty:
        return []
    lbl_col = next((c for c in df.columns if c.lower() == 'label'), None)
    if lbl_col is None:
        return []
    df = df[df[lbl_col].astype(str).str.strip() == 'one-time']
    rows = []
    for _, row in df.iterrows():
        try:
            rows.append({
                'date':     str(row.get('Transaction Date', '')).strip(),
                'place':    str(row.get('Place', '')).strip(),
                'amount':   round(float(row.get('Amount', 0)), 2),
                'month':    str(row.get('month', '')).strip(),
                'category': str(row.get('category', '')).strip(),
                'label':    'one-time',
            })
        except Exception:
            pass
    return rows


# ── Expense label ─────────────────────────────────────────────────────────────

@router.post("/api/expense/label")
def set_expense_label(payload: dict = Body(...)):
    """Update the Label column for an expense row (DB primary, CSV backup)."""
    date   = str(payload.get('date', '')).strip()
    place  = str(payload.get('place', '')).strip()
    month  = str(payload.get('month', '')).strip()
    label  = str(payload.get('label', 'recurring')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})
    if label not in ('recurring', 'one-time'):
        return JSONResponse(status_code=400, content={'error': 'label must be recurring or one-time'})

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET label=:label, user_corrected=1 "
                    "WHERE tx_type='expense' AND report_month=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'label': label, 'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB expense label update failed: {exc}')
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _update_csv_label(stmt_dir / 'expenses.csv', date, place, amount, label)

    return {'ok': ok, 'date': date, 'place': place, 'amount': amount, 'label': label}


# ── Available months ──────────────────────────────────────────────────────────

@router.get("/api/available-months")
def get_available_months():
    """Return sorted list of months that have expense transactions in the DB."""
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                rows = conn.execute(_text(
                    "SELECT DISTINCT report_month FROM transactions "
                    "WHERE tx_type='expense' ORDER BY report_month DESC"
                )).fetchall()
            return [r[0] for r in rows]
        except Exception as exc:
            logging.warning(f"DB available-months query failed: {exc}")
    return []


# ── All expenses ──────────────────────────────────────────────────────────────

@router.get("/api/all-expenses")
def get_all_expenses(month: str = None, category: str = None, search: str = None):
    """Return expense rows from the DB, optionally filtered by month/category/search."""
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            query = (
                "SELECT tx_hash, tx_date, place, amount, category, label, statement, "
                "report_month, rowid AS row_idx "
                "FROM transactions WHERE tx_type='expense'"
            )
            params: dict = {}
            if month:
                query += " AND report_month = :month"
                params['month'] = month
            if category:
                query += " AND lower(category) = lower(:category)"
                params['category'] = category
            if search:
                query += " AND lower(place) LIKE lower(:search)"
                params['search'] = f'%{search}%'
            query += " ORDER BY report_month DESC, tx_date"
            with get_engine().connect() as conn:
                result = conn.execute(_text(query), params).fetchall()
            return [
                {
                    'tx_hash':   r[0] or '',
                    'date':      r[1] or '',
                    'place':     r[2] or '',
                    'amount':    round(float(r[3] or 0), 2),
                    'category':  r[4] or '',
                    'label':     r[5] or 'recurring',
                    'statement': r[6] or '',
                    'month':     r[7] or '',
                    'row_idx':   r[8],
                }
                for r in result
            ]
        except Exception as exc:
            logging.warning(f"DB all-expenses query failed: {exc}")
    return []


# ── Delete transaction ────────────────────────────────────────────────────────

@router.delete("/api/transactions/{tx_hash}")
def delete_transaction(tx_hash: str):
    """Permanently delete a transaction by its tx_hash."""
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'Database unavailable'})
    if not re.match(r'^[0-9a-f]{24}$', tx_hash):
        return JSONResponse(status_code=400, content={'error': 'Invalid transaction id'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            row = conn.execute(
                _text("SELECT place, amount, tx_type FROM transactions WHERE tx_hash = :h"),
                {'h': tx_hash}
            ).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={'error': 'Transaction not found'})
            conn.execute(_text("DELETE FROM transactions WHERE tx_hash = :h"), {'h': tx_hash})
            conn.commit()
        logging.info(f"🗑️ Deleted transaction {tx_hash} ({row[0]} ${row[1]})")
        return {'success': True}
    except Exception as exc:
        logging.exception("Failed to delete transaction")
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── Edit expense ──────────────────────────────────────────────────────────────

@router.patch("/api/expense/edit")
def edit_expense(payload: dict = Body(...)):
    """Update place/category/label/amount of a specific expense row in-place."""
    month          = str(payload.get('month', '')).strip()
    date           = str(payload.get('date', '')).strip()
    original_place = str(payload.get('original_place', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    new_place    = str(payload.get('new_place', '')).strip() or None
    new_category = str(payload.get('new_category', '')).strip() or None
    new_label    = str(payload.get('new_label', '')).strip() or None
    new_amount   = payload.get('new_amount')

    old_category = ''
    db_ok = False

    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            _eng = get_engine()
            with _eng.connect() as conn:
                old_row = conn.execute(_text(
                    "SELECT category FROM transactions "
                    "WHERE tx_type='expense' AND report_month=:m "
                    "AND tx_date=:d AND UPPER(place)=UPPER(:p) "
                    "AND ROUND(amount,2)=ROUND(:a,2) LIMIT 1"
                ), {'m': month, 'd': date, 'p': original_place, 'a': amount}).fetchone()
                if old_row:
                    old_category = str(old_row[0] or '').strip()

            set_clauses, params = [], {'m': month, 'd': date, 'p': original_place, 'a': amount}
            if new_place:
                set_clauses.append('place=:new_place'); params['new_place'] = new_place
            if new_category:
                set_clauses.append('category=:new_cat'); params['new_cat'] = new_category
                set_clauses.append('user_corrected=1')
            if new_label:
                set_clauses.append('label=:new_lbl'); params['new_lbl'] = new_label
            if new_amount is not None:
                set_clauses.append('amount=:new_amt'); params['new_amt'] = round(float(new_amount), 2)

            if set_clauses:
                sql = (
                    f"UPDATE transactions SET {', '.join(set_clauses)} "
                    "WHERE tx_type='expense' AND report_month=:m "
                    "AND tx_date=:d AND UPPER(place)=UPPER(:p) "
                    "AND ROUND(amount,2)=ROUND(:a,2)"
                )
                with _eng.connect() as conn:
                    result = conn.execute(_text(sql), params)
                    conn.commit()
                db_ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB expense edit failed: {exc}')

    if not db_ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found'})

    logging.info(f"✏️ Expense edited: {original_place} → {new_place or original_place} [{month}]")

    def _apply_src_edit(src_csv: Path) -> bool:
        if not src_csv.exists():
            return False
        try:
            src_df = pd.read_csv(src_csv)
            src_mask = (
                (src_df['Transaction Date'].astype(str).str.strip() == date) &
                (src_df['Place'].astype(str).str.strip() == original_place) &
                (src_df['Amount'].apply(lambda x: round(float(x), 2)) == amount)
            )
            if not src_mask.any():
                return False
            if new_place:    src_df.loc[src_mask, 'Place']    = new_place
            if new_category: src_df.loc[src_mask, 'category'] = new_category
            if new_label:    src_df.loc[src_mask, 'Label']    = new_label
            if new_amount is not None: src_df.loc[src_mask, 'Amount'] = round(float(new_amount), 2)
            src_df.to_csv(src_csv, index=False)
            return True
        except Exception as exc:
            logging.warning(f'Could not write back to {src_csv}: {exc}')
            return False

    if not _apply_src_edit(_STATEMENTS_BASE / month / 'expenses.csv'):
        for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
            if stmt_dir.is_dir() and stmt_dir.name != month:
                if _apply_src_edit(stmt_dir / 'expenses.csv'):
                    break

    new_cat_eff = new_category or ''
    if new_cat_eff or old_category:
        if old_category in _INVESTMENT_CATEGORIES or new_cat_eff in _INVESTMENT_CATEGORIES:
            try:
                _rebuild_transfers_for_month(month)
            except Exception as exc:
                logging.warning(f'Could not rebuild transfers for {month}: {exc}')

    return {'success': True}


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/api/categories")
def get_flat_categories():
    """Return the flat list of category names from categories.json."""
    config_path = _CONFIG_ROOT / 'categories.json'
    try:
        with open(config_path, 'r') as f:
            config = _json.load(f)
        return [{'category': c} for c in config.get('categories', [])]
    except Exception:
        return []


@router.get("/api/category-subcategories")
def get_category_subcategories():
    """Return parent→subcategory mapping from categories.json."""
    config_path = _CONFIG_ROOT / 'categories.json'
    try:
        with open(config_path, 'r') as f:
            config = _json.load(f)
        return config.get('subcategories', {})
    except Exception as exc:
        logging.exception("Failed to load category subcategories")
        return {}


# ── Expense categories ────────────────────────────────────────────────────────

@router.get("/api/expense-categories")
def get_expense_categories(month: str = None):
    """Return per-category totals for a month (or the most recent month)."""
    if not month:
        if _DB_AVAILABLE:
            try:
                from sqlalchemy import text as _text
                with get_engine().connect() as conn:
                    row = conn.execute(_text(
                        "SELECT report_month FROM transactions WHERE tx_type='expense' "
                        "ORDER BY report_month DESC LIMIT 1"
                    )).fetchone()
                month = row[0] if row else None
            except Exception:
                pass
        if not month:
            return []

    exp_df = _query_df('expense', months=[month])
    inc_df = _query_df('income', months=[month])

    if exp_df.empty and inc_df.empty:
        return []

    category_totals: dict = defaultdict(float)

    if not exp_df.empty and 'category' in exp_df.columns:
        for _, row in exp_df.iterrows():
            cat = str(row.get('category', '')).strip() or 'Uncategorized'
            try:
                category_totals[cat] += float(row.get('Amount', 0) or 0)
            except Exception:
                pass

    if not inc_df.empty:
        for _, row in inc_df.iterrows():
            if str(row.get('Label', '')).strip().lower() != 'reimbursement':
                continue
            cat = str(row.get('category', '')).strip() or 'Uncategorized'
            try:
                category_totals[cat] -= abs(float(row.get('Amount', 0) or 0))
            except Exception:
                pass

    return [
        {'category': cat, 'amount': round(total, 2)}
        for cat, total in category_totals.items()
        if cat
    ]


@router.get("/api/expenses-by-month")
def get_expenses_by_month():
    """Return per-category totals for every available month (for trend chart)."""
    subcategories = {}
    try:
        with open(_CONFIG_ROOT / 'categories.json') as f:
            subcategories = _json.load(f).get("subcategories", {})
    except Exception:
        pass
    sub_to_parent = {sub: parent for parent, subs in subcategories.items() for sub in subs}

    exp_df = _query_df('expense')
    inc_df = _query_df('income')

    if exp_df.empty and inc_df.empty:
        return []

    months_set: set = set()
    if not exp_df.empty and 'month' in exp_df.columns:
        months_set.update(exp_df['month'].dropna().unique())
    if not inc_df.empty and 'month' in inc_df.columns:
        months_set.update(inc_df['month'].dropna().unique())

    results = []
    for month_str in sorted(months_set):
        category_totals: dict = defaultdict(float)

        exp_month = exp_df[exp_df['month'] == month_str] if not exp_df.empty else pd.DataFrame()
        if not exp_month.empty and 'category' in exp_month.columns:
            for _, row in exp_month.iterrows():
                cat = str(row.get('category', '')).strip() or 'Uncategorized'
                cat = sub_to_parent.get(cat, cat)
                try:
                    category_totals[cat] += float(row.get('Amount', 0) or 0)
                except Exception:
                    pass

        inc_month = inc_df[inc_df['month'] == month_str] if not inc_df.empty else pd.DataFrame()
        if not inc_month.empty:
            for _, row in inc_month.iterrows():
                if str(row.get('Label', '')).strip().lower() != 'reimbursement':
                    continue
                cat = str(row.get('category', '')).strip() or 'Uncategorized'
                cat = sub_to_parent.get(cat, cat)
                try:
                    category_totals[cat] -= abs(float(row.get('Amount', 0) or 0))
                except Exception:
                    pass

        for cat, total in category_totals.items():
            if cat:
                results.append({'month': month_str, 'category': cat, 'amount': round(total, 2)})

    return results


# ── Manual transactions ───────────────────────────────────────────────────────

def _load_manual_transactions() -> list:
    if not _MANUAL_TRANSACTIONS_FILE.exists():
        return []
    try:
        with open(_MANUAL_TRANSACTIONS_FILE) as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_manual_transactions(transactions: list) -> None:
    _MANUAL_TRANSACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MANUAL_TRANSACTIONS_FILE, "w") as f:
        _json.dump(transactions, f, indent=2)


def _write_manual_tx_to_db(record: dict) -> None:
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        from src.database.db_utils import _make_hash
        tx_type  = 'income' if record['type'] == 'income' else 'expense'
        amount   = -abs(record['amount']) if record['type'] == 'reimbursement' else abs(record['amount'])
        label    = 'reimbursement' if record['type'] == 'reimbursement' else record.get('label', 'recurring')
        tx_hash  = _make_hash(record['month'], record['date'], record['place'], amount, tx_type, 'Manual')
        with get_engine().connect() as conn:
            conn.execute(_text(
                "INSERT OR IGNORE INTO transactions "
                "(tx_hash, report_month, tx_date, place, amount, category, label, tx_type, statement, user_corrected) "
                "VALUES (:h, :m, :d, :p, :a, :c, :l, :t, 'Manual', 0)"
            ), {'h': tx_hash, 'm': record['month'], 'd': record['date'], 'p': record['place'],
                'a': amount, 'c': record.get('category', ''), 'l': label, 't': tx_type})
            conn.commit()
    except Exception as exc:
        logging.warning(f'Could not write manual transaction to DB: {exc}')


def _delete_manual_tx_from_db(record: dict) -> None:
    if not _DB_AVAILABLE:
        return
    try:
        from sqlalchemy import text as _text
        from src.database.db_utils import _make_hash
        tx_type = 'income' if record['type'] == 'income' else 'expense'
        amount  = -abs(record['amount']) if record['type'] == 'reimbursement' else abs(record['amount'])
        tx_hash = _make_hash(record['month'], record['date'], record['place'], amount, tx_type, 'Manual')
        with get_engine().connect() as conn:
            conn.execute(_text("DELETE FROM transactions WHERE tx_hash = :h"), {'h': tx_hash})
            conn.commit()
    except Exception as exc:
        logging.warning(f'Could not delete manual transaction from DB: {exc}')


@router.get("/api/manual-transactions")
async def get_manual_transactions():
    """Return all manually added transactions."""
    return _load_manual_transactions()


@router.post("/api/manual-transactions")
async def add_manual_transaction(tx: dict = Body(...)):
    """Add a manual transaction (expense, income, or reimbursement)."""
    try:
        required = ["date", "place", "amount", "type"]
        for field in required:
            if field not in tx:
                return JSONResponse(status_code=400, content={"error": f"Missing field: {field}"})

        dt = datetime.strptime(tx["date"], "%Y-%m-%d")
        month = dt.strftime("%Y-%m")

        record = {
            "id":       str(uuid.uuid4()),
            "date":     tx["date"],
            "place":    tx["place"].strip(),
            "amount":   float(tx["amount"]),
            "type":     tx["type"],
            "category": tx.get("category", "") if tx["type"] in ("expense", "reimbursement") else "",
            "label":    tx.get("label", "recurring"),
            "month":    month,
        }

        transactions = _load_manual_transactions()
        transactions.append(record)
        _save_manual_transactions(transactions)
        _write_manual_tx_to_db(record)

        logging.info(f"✏️ Manual transaction added: {record['place']} ${record['amount']} ({record['month']})")
        return {"success": True, "transaction": record}

    except Exception as e:
        logging.exception("Failed to add manual transaction")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/api/manual-transactions/{tx_id}")
async def delete_manual_transaction(tx_id: str):
    """Delete a manual transaction by ID and remove from DB."""
    try:
        transactions = _load_manual_transactions()
        target = next((t for t in transactions if t["id"] == tx_id), None)
        if target is None:
            return JSONResponse(status_code=404, content={"error": "Transaction not found"})

        transactions = [t for t in transactions if t["id"] != tx_id]
        _save_manual_transactions(transactions)
        _delete_manual_tx_from_db(target)

        logging.info(f"🗑️ Manual transaction deleted: {target['place']} ${target['amount']}")
        return {"success": True}

    except Exception as e:
        logging.exception("Failed to delete manual transaction")
        return JSONResponse(status_code=500, content={"error": str(e)})
