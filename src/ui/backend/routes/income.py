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
    _PAYMENT_APP_KEYWORDS,
    _reload_investment_keywords,
    _reload_income_keywords,
)


def _learn_keyword_from_label(place: str, label: str) -> None:
    """Persist a keyword learned from a user correction so future transactions
    from this merchant are auto-classified without manual intervention.

    investment_transfer → investment_keywords
    recurring           → income_keywords (only if not already in list)
    """
    if not _DB_AVAILABLE or not place:
        return
    try:
        import re as _re
        from sqlalchemy import text as _text

        def _norm(s: str) -> str:
            s = str(s).lower()
            s = _re.sub(r"['\.\ \-,#]", ' ', s)
            s = _re.sub(r'\b\d{3,}\b', '', s)
            return ' '.join(s.split())

        kw = _norm(place)
        if not kw:
            return

        engine = get_engine()
        if label == 'investment_transfer':
            # Skip if already covered by an existing keyword
            if any(existing in kw for existing in _INVESTMENT_PLATFORM_KEYWORDS):
                return
            with engine.connect() as conn:
                conn.execute(_text(
                    "INSERT OR IGNORE INTO investment_keywords (keyword, source) VALUES (:kw, 'learned')"
                ), {'kw': kw})
                conn.commit()
            _reload_investment_keywords()
            logging.info(f'Learned investment keyword from user action: "{kw}"')
        elif label == 'recurring':
            from src.ui.backend.deps import _INCOME_KEYWORDS
            if any(existing.lower() in kw for existing in _INCOME_KEYWORDS):
                return
            # Never learn payment-app merchants (Cash App, Venmo, Zelle, etc.) or
            # investment platforms as income keywords — they are not payroll/salary.
            if any(existing.lower() in kw for existing in _PAYMENT_APP_KEYWORDS):
                return
            if any(existing.lower() in kw for existing in _INVESTMENT_PLATFORM_KEYWORDS):
                return
            with engine.connect() as conn:
                conn.execute(_text(
                    "INSERT OR IGNORE INTO income_keywords (keyword, source) VALUES (:kw, 'learned')"
                ), {'kw': kw})
                conn.commit()
            _reload_income_keywords()
            logging.info(f'Learned income keyword from user action: "{kw}"')
    except Exception as exc:
        logging.warning(f'_learn_keyword_from_label: {exc}')

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
                if rlabel in ('reimbursement', 'investment_transfer'):
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
    """Return raw income rows for a given month (or all months), including category.
    The 'month' filter and the 'month' field in the response use the calendar month
    of the actual transaction date, consistent with get_all_expenses.
    """
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            query = (
                "SELECT tx_hash, tx_date, place, amount, report_month, statement, label, category, "
                "CASE WHEN INSTR(tx_date, '/') > 0 THEN "
                "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)) "
                "ELSE '' END AS tx_month "
                "FROM transactions WHERE tx_type='income'"
            )
            params: dict = {}
            if month:
                query += (
                    " AND INSTR(tx_date, '/') > 0"
                    " AND ("
                    "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER))"
                    ") = :month"
                )
                params['month'] = month
            query += " ORDER BY tx_date DESC, place"
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
                    'month':     r[8] or r[4] or '',
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
                    "WHERE tx_type='income' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND (SUBSTR(tx_date, LENGTH(tx_date)-3, 4)||'-'||"
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)))=:month "
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
    if label not in ('recurring', 'bonus', 'investment_transfer'):
        return JSONResponse(status_code=400, content={'error': 'label must be recurring, bonus, or investment_transfer'})

    ok = False
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET label=:label, user_corrected=1 "
                    "WHERE tx_type='income' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND (SUBSTR(tx_date, LENGTH(tx_date)-3, 4)||'-'||"
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)))=:month "
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

    if label == 'investment_transfer' and month:
        try:
            _rebuild_transfers_for_month(month)
        except Exception as exc:
            logging.warning(f'Could not rebuild transfers after investment_transfer label: {exc}')

    _learn_keyword_from_label(place, label)

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
                    "WHERE tx_type='income' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND (SUBSTR(tx_date, LENGTH(tx_date)-3, 4)||'-'||"
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)))=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'month': month, 'date': date, 'place': place, 'amount': amount})
                conn.commit()
            ok = result.rowcount > 0
        except Exception as exc:
            logging.warning(f'DB reclassify income→reimbursement failed: {exc}')

    # Inherit category from the most recent expense for the same merchant
    inherited_category = ''
    if ok and _DB_AVAILABLE:
        try:
            from src.database.db_utils import _normalize_merchant_key
            mk = _normalize_merchant_key(place)
            with get_engine().connect() as conn2:
                candidates = conn2.execute(_text(
                    "SELECT place, category FROM transactions "
                    "WHERE tx_type='expense' AND label != 'reimbursement' "
                    "AND category IS NOT NULL AND TRIM(category) != '' "
                    "ORDER BY report_month DESC, tx_date DESC LIMIT 500"
                )).fetchall()
            for exp_place, cat in candidates:
                if _normalize_merchant_key(exp_place) == mk:
                    inherited_category = str(cat).strip()
                    break
            if inherited_category:
                with get_engine().connect() as conn3:
                    conn3.execute(_text(
                        "UPDATE transactions SET category=:cat "
                        "WHERE tx_type='expense' AND label='reimbursement' "
                        "AND INSTR(tx_date, '/') > 0 "
                        "AND (SUBSTR(tx_date, LENGTH(tx_date)-3, 4)||'-'||"
                        "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)))=:month "
                        "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                        "AND (category IS NULL OR TRIM(category)='')"
                    ), {'cat': inherited_category, 'month': month, 'date': date, 'place': place})
                    conn3.commit()
        except Exception as exc:
            logging.warning(f'reclassify reimbursement category lookup failed: {exc}')

    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _move_row(stmt_dir / 'income.csv', stmt_dir / 'expenses.csv')

    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in income data'})

    logging.info(f'Reclassified income as reimbursement: {place} [{month}] ${amount}')
    return {'success': True, 'category': inherited_category}


@router.post("/api/expense/reclassify-as-income")
def reclassify_expense_as_income(payload: dict = Body(...)):
    """Move an expense row into the income table (DB primary + CSV backup).

    Pass ``save_rule=true`` in the payload to also persist a merchant rule so
    this merchant is ALWAYS treated as income on future reprocessing.  Only do
    this for recurring income sources (payroll, rent deposits, etc.) — do NOT
    use it for one-off investment withdrawals, reimbursements, or anything that
    only occasionally shows up as income.
    """
    date      = str(payload.get('date', '')).strip()
    place     = str(payload.get('place', '')).strip()
    month     = str(payload.get('month', '')).strip()
    save_rule = bool(payload.get('save_rule', False))
    label     = str(payload.get('label', 'recurring')).strip()
    if label not in ('recurring', 'bonus', 'investment_transfer'):
        label = 'recurring'
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
            from src.database.db_utils import _make_hash
            with get_engine().connect() as conn:
                result = conn.execute(_text(
                    "UPDATE transactions SET tx_type='income', amount=ABS(amount), label=:label, user_corrected=1 "
                    "WHERE tx_type='expense' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND (SUBSTR(tx_date, LENGTH(tx_date)-3, 4)||'-'||"
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)))=:month "
                    "AND tx_date=:date AND UPPER(place)=UPPER(:place) "
                    "AND ROUND(amount,2)=ROUND(:amount,2)"
                ), {'month': month, 'date': date, 'place': place, 'amount': amount, 'label': label})
                if result.rowcount > 0:
                    # tx_hash includes tx_type, so recompute it now that we changed
                    # tx_type from 'expense' to 'income', otherwise the snapshot/restore
                    # logic in aggregate_monthly.py silently fails to reapply corrections.
                    row = conn.execute(_text(
                        "SELECT report_month, tx_date, place, amount, statement, tx_hash "
                        "FROM transactions WHERE tx_type='income' "
                        "AND tx_date=:d AND UPPER(place)=UPPER(:p) AND ROUND(amount,2)=ROUND(:a,2)"
                    ), {'d': date, 'p': place, 'a': amount}).fetchone()
                    if row:
                        rmonth, txdate, txplace, txamt, txstmt, old_hash = row
                        new_hash = _make_hash(rmonth, txdate, txplace, txamt, 'income', txstmt or '')
                        if new_hash != old_hash:
                            upd = conn.execute(_text(
                                "UPDATE OR IGNORE transactions SET tx_hash=:nh WHERE tx_hash=:oh"
                            ), {'nh': new_hash, 'oh': old_hash})
                            if upd.rowcount == 0:
                                # UNIQUE conflict: canonical income row exists — drop stale duplicate
                                conn.execute(_text(
                                    "DELETE FROM transactions WHERE tx_hash=:oh"
                                ), {'oh': old_hash})
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

    # Persist a merchant rule only when the caller explicitly requests it
    # (save_rule=True) AND the merchant is not an investment platform or payment app.
    # This prevents one-off reclassifications (e.g. an investment withdrawal)
    # from permanently overriding all future transactions for that merchant.
    _place_upper = place.upper()
    _is_investment = any(kw in place.lower() for kw in _INVESTMENT_PLATFORM_KEYWORDS)
    _is_payment_app = any(kw in _place_upper for kw in _PAYMENT_APP_KEYWORDS)
    if save_rule and label == 'recurring' and _DB_AVAILABLE and not _is_investment and not _is_payment_app:
        try:
            import re as _re
            def _norm_mk(s: str) -> str:
                s = str(s).lower()
                s = _re.sub(r"['\.\-,#]", '', s)
                s = _re.sub(r'\b\d{3,}\b', '', s)
                return ' '.join(s.split())

            from sqlalchemy import text as _text
            mk = _norm_mk(place)
            with get_engine().connect() as conn:
                existing = conn.execute(_text(
                    "SELECT id FROM merchant_rules WHERE merchant_key=:mk"
                ), {'mk': mk}).fetchone()
                if not existing:
                    conn.execute(_text(
                        "INSERT INTO merchant_rules (merchant_key, display_name, action, category) "
                        "VALUES (:mk, :dn, 'income', NULL)"
                    ), {'mk': mk, 'dn': place})
                    conn.commit()
                    logging.info(f'Added merchant rule: {mk} → income')
        except Exception as exc:
            logging.warning(f'Could not add merchant rule for {place}: {exc}')

    _learn_keyword_from_label(place, label)

    logging.info(f'Reclassified expense as income: {place} [{month}] ${amount}')
    return {'success': True}
