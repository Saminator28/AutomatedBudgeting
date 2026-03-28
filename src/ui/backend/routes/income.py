"""routes/income.py — Income endpoints."""

import logging
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _DB_AVAILABLE, get_engine,
    _STATEMENTS_BASE,
    _update_csv_label,
    _rebuild_transfers_for_month,
    _INVESTMENT_PLATFORM_KEYWORDS,
)

router = APIRouter()


@router.get("/api/income-by-month")
def get_income_by_month():
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                db_rows = conn.execute(_text(
                    "SELECT report_month, label, amount, place "
                    "FROM transactions WHERE tx_type='income' "
                    "ORDER BY report_month"
                )).fetchall()
            month_map: dict = {}
            for r in db_rows:
                rmonth, rlabel = r[0], (r[1] or '').lower()
                ramount, rplace = float(r[2] or 0), (r[3] or '').lower()
                if any(kw in rplace for kw in _INVESTMENT_PLATFORM_KEYWORDS):
                    continue
                if rlabel == 'reimbursement':
                    continue
                if rmonth not in month_map:
                    month_map[rmonth] = {'recurring': 0.0, 'bonus': 0.0}
                if rlabel == 'bonus':
                    month_map[rmonth]['bonus'] += ramount
                else:
                    month_map[rmonth]['recurring'] += ramount
            return [
                {
                    'month':        m,
                    'income':       round(v['recurring'], 2),
                    'bonus':        round(v['bonus'], 2),
                    'total_income': round(v['recurring'] + v['bonus'], 2),
                }
                for m, v in sorted(month_map.items())
            ]
        except Exception as exc:
            logging.warning(f"DB income-by-month query failed: {exc}")
    return []


@router.get("/api/income-breakdown")
def get_income_breakdown():
    """Return all income rows with labels (recurring/bonus), excluding Investment Return."""
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                db_rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, report_month, label, category "
                    "FROM transactions WHERE tx_type='income' ORDER BY report_month, tx_date"
                )).fetchall()
            return [
                {
                    'date':   r[0] or '',
                    'place':  r[1] or '',
                    'amount': round(float(r[2] or 0), 2),
                    'month':  r[3] or '',
                    'label':  (r[4] or 'recurring') or 'recurring',
                }
                for r in db_rows
                if str(r[5] or '').strip() != 'Investment Return'
            ]
        except Exception as exc:
            logging.warning(f'DB income-breakdown failed: {exc}')
    return []


@router.get("/api/income-entries")
def get_income_entries(month: str = ''):
    """Return raw income rows for a given month (or all months), including category."""
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            query = (
                "SELECT tx_hash, tx_date, place, amount, report_month, statement, label, category "
                "FROM transactions WHERE tx_type='income'"
            )
            params: dict = {}
            if month:
                query += " AND report_month = :month"
                params['month'] = month
            query += " ORDER BY report_month, tx_date"
            with get_engine().connect() as conn:
                db_rows = conn.execute(_text(query), params).fetchall()

            def _clean(v):
                return '' if str(v or '').strip().lower() in ('nan', 'none', '') else str(v).strip()

            return [
                {
                    'tx_hash':   r[0] or '',
                    'date':      r[1] or '',
                    'place':     r[2] or '',
                    'amount':    round(float(r[3] or 0), 2),
                    'month':     r[4] or '',
                    'statement': r[5] or '',
                    'label':     _clean(r[6]) or 'recurring',
                    'category':  _clean(r[7]),
                }
                for r in db_rows
            ]
        except Exception as exc:
            logging.warning(f"DB income-entries query failed: {exc}")
    return []


@router.patch("/api/income/categorize")
def categorize_income(payload: dict = Body(...)):
    """Set or clear the category on an income row (DB primary + CSV backup)."""
    month    = str(payload.get('month', '')).strip()
    date     = str(payload.get('date', '')).strip()
    place    = str(payload.get('place', '')).strip()
    category = str(payload.get('category', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    def _apply_category(csv_path: Path) -> bool:
        if not csv_path.exists():
            return False
        try:
            df = pd.read_csv(csv_path)
            if 'category' not in df.columns:
                df['category'] = ''
            mask = (
                (df['Transaction Date'].astype(str).str.strip() == date) &
                (df['Place'].astype(str).str.strip() == place) &
                (df['Amount'].apply(lambda x: round(float(x), 2)) == amount)
            )
            if not mask.any():
                return False
            df.loc[mask, 'category'] = category
            df.to_csv(csv_path, index=False)
            return True
        except Exception as exc:
            logging.warning(f'Could not update {csv_path}: {exc}')
            return False

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET category=:cat, user_corrected=1 "
                    "WHERE tx_type='income' AND report_month=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'cat': category, 'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB income categorize failed: {exc}')
    _apply_category(_STATEMENTS_BASE / month / 'income.csv')
    if not ok:
        for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
            if stmt_dir.is_dir() and stmt_dir.name != month:
                if _apply_category(stmt_dir / 'income.csv'):
                    ok = True
                    break

    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in income data'})

    try:
        _rebuild_transfers_for_month(month)
    except Exception as exc:
        logging.warning(f'Could not rebuild transfers after income categorize: {exc}')

    logging.info(f'Income categorized: {place} [{month}] → {category}')
    return {'success': True}


@router.post("/api/income/label")
def set_income_label(payload: dict = Body(...)):
    """Update the Label column for an income row (DB primary, CSV backup)."""
    date   = str(payload.get('date', '')).strip()
    place  = str(payload.get('place', '')).strip()
    month  = str(payload.get('month', '')).strip()
    label  = str(payload.get('label', 'recurring')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})
    if label not in ('recurring', 'bonus'):
        return JSONResponse(status_code=400, content={'error': 'label must be recurring or bonus'})

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET label=:label, user_corrected=1 "
                    "WHERE tx_type='income' AND report_month=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'label': label, 'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB income label update failed: {exc}')
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _update_csv_label(stmt_dir / 'income.csv', date, place, amount, label)

    return {'ok': ok, 'date': date, 'place': place, 'amount': amount, 'label': label}


@router.post("/api/income/reclassify-as-reimbursement")
def reclassify_income_as_reimbursement(payload: dict = Body(...)):
    """Move an income row to the expenses table as a reimbursement (DB primary + CSV)."""
    date  = str(payload.get('date', '')).strip()
    place = str(payload.get('place', '')).strip()
    month = str(payload.get('month', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    def _move_row(src_csv: Path, dst_csv: Path) -> bool:
        if not src_csv.exists():
            return False
        try:
            src_df = pd.read_csv(src_csv)
            mask = (
                (src_df['Transaction Date'].astype(str).str.strip() == date) &
                (src_df['Place'].astype(str).str.strip() == place) &
                (src_df['Amount'].apply(lambda x: round(float(x), 2)) == amount)
            )
            if not mask.any():
                return False
            row_data = src_df.loc[mask].iloc[0].to_dict()
            src_df = src_df[~mask]
            src_df.to_csv(src_csv, index=False)
            new_row = {
                'Transaction Date': row_data.get('Transaction Date', date),
                'Place': row_data.get('Place', place),
                'Amount': -abs(amount),
                'Statement': row_data.get('Statement', ''),
                'category': '',
                'Label': 'reimbursement',
            }
            if dst_csv.exists():
                dst_df = pd.read_csv(dst_csv)
                if 'category' not in dst_df.columns:
                    dst_df['category'] = ''
            else:
                dst_df = pd.DataFrame(columns=list(new_row.keys()))
            dst_df = pd.concat([dst_df, pd.DataFrame([new_row])], ignore_index=True)
            dst_df.to_csv(dst_csv, index=False)
            return True
        except Exception as exc:
            logging.warning(f'reclassify_as_reimbursement: error in {src_csv}: {exc}')
            return False

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET tx_type='expense', amount=-ABS(amount), label='reimbursement' "
                    "WHERE tx_type='income' AND report_month=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB reclassify income→reimbursement failed: {exc}')
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _move_row(stmt_dir / 'income.csv', stmt_dir / 'expenses.csv')

    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in income data'})

    logging.info(f'Reclassified income as reimbursement: {place} [{month}] ${amount}')
    return {'success': True}


@router.post("/api/expense/reclassify-as-income")
def reclassify_expense_as_income(payload: dict = Body(...)):
    """Move an expense row into the income table (DB primary + CSV backup)."""
    date  = str(payload.get('date', '')).strip()
    place = str(payload.get('place', '')).strip()
    month = str(payload.get('month', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    def _move_row(src_csv: Path, dst_csv: Path) -> bool:
        if not src_csv.exists():
            return False
        try:
            src_df = pd.read_csv(src_csv)
            mask = (
                (src_df['Transaction Date'].astype(str).str.strip() == date) &
                (src_df['Place'].astype(str).str.strip() == place) &
                (src_df['Amount'].apply(lambda x: round(float(x), 2)) == amount)
            )
            if not mask.any():
                return False
            row_data = src_df.loc[mask].iloc[0].to_dict()
            src_df = src_df[~mask]
            src_df.to_csv(src_csv, index=False)
            new_row = {
                'Transaction Date': row_data.get('Transaction Date', date),
                'Place': row_data.get('Place', place),
                'Amount': abs(amount),
                'Statement': row_data.get('Statement', ''),
                'Label': 'recurring',
            }
            if dst_csv.exists():
                dst_df = pd.read_csv(dst_csv)
            else:
                dst_df = pd.DataFrame(columns=list(new_row.keys()))
            dst_df = pd.concat([dst_df, pd.DataFrame([new_row])], ignore_index=True)
            dst_df.to_csv(dst_csv, index=False)
            return True
        except Exception as exc:
            logging.warning(f'reclassify_expense_as_income: error in {src_csv}: {exc}')
            return False

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET tx_type='income', amount=ABS(amount), label='recurring' "
                    "WHERE tx_type='expense' AND report_month=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB reclassify expense→income failed: {exc}')
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _move_row(stmt_dir / 'expenses.csv', stmt_dir / 'income.csv')

    if any(kw in place.lower() for kw in _INVESTMENT_PLATFORM_KEYWORDS):
        try:
            _rebuild_transfers_for_month(month)
        except Exception as exc:
            logging.warning(f'Could not rebuild transfers after income reclassification: {exc}')

    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in expense data'})

    logging.info(f'Reclassified expense as income: {place} [{month}] ${amount}')
    return {'success': True}
