"""routes/statements.py — Statement file management, processing jobs, and manual review."""

import logging
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Body, File, UploadFile
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _DB_AVAILABLE, get_engine,
    _STATEMENTS_BASE, _PROJECT_ROOT,
    _is_valid_month, _safe_statement_path,
    _INVESTMENT_CATEGORIES, _INVESTMENT_PLATFORM_KEYWORDS,
    _rebuild_transfers_for_month,
    _jobs, _jobs_lock,
)

router = APIRouter()


# ── List statements ───────────────────────────────────────────────────────────

@router.get("/api/statements")
def list_statements():
    """Return all statement months with their PDF/CSV file lists."""
    processed_months: set = set()
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                rows = conn.execute(_text(
                    "SELECT DISTINCT report_month FROM transactions"
                )).fetchall()
            processed_months = {r[0] for r in rows}
        except Exception:
            pass
    months = []
    for d in sorted(_STATEMENTS_BASE.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        files = []
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in ('.pdf', '.csv'):
                files.append({
                    'name': f.name,
                    'type': f.suffix.lower().lstrip('.'),
                    'size': f.stat().st_size,
                })
        months.append({'month': d.name, 'files': files, 'is_processed': d.name in processed_months})
    return months


# ── Upload statement ──────────────────────────────────────────────────────────

@router.post("/api/statements/{month}/upload")
async def upload_statement(month: str, file: UploadFile = File(...)):
    """Upload a PDF statement to statements/YYYY-MM/."""
    if not _is_valid_month(month):
        return JSONResponse(status_code=400, content={'error': 'Month must be YYYY-MM format'})
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return JSONResponse(status_code=400, content={'error': 'Only PDF files are accepted'})
    try:
        dest_path = _safe_statement_path(month, file.filename)
        with open(dest_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={'error': str(exc)})
    finally:
        file.file.close()
    logging.info(f'Uploaded {dest_path.name} to statements/{month}/')
    return {'success': True, 'filename': dest_path.name, 'month': month}


# ── Delete statement file ─────────────────────────────────────────────────────

@router.delete("/api/statements/{month}/{filename}")
def delete_statement_file(month: str, filename: str):
    """Delete a PDF file from statements/YYYY-MM/."""
    try:
        target = _safe_statement_path(month, filename)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={'error': str(exc)})
    if not target.exists():
        return JSONResponse(status_code=404, content={'error': 'File not found'})
    if target.suffix.lower() != '.pdf':
        return JSONResponse(status_code=400, content={'error': 'Can only delete PDF files'})
    target.unlink()
    logging.info(f'Deleted statements/{month}/{target.name}')
    return {'success': True}


# ── Delete statement month ────────────────────────────────────────────────────

@router.delete("/api/statements/{month}")
def delete_statement_month(month: str):
    """Delete an entire statement month folder and all DB rows for that month."""
    if not _is_valid_month(month):
        return JSONResponse(status_code=400, content={'error': 'Month must be YYYY-MM format'})
    month_dir = (_STATEMENTS_BASE / month).resolve()
    if _STATEMENTS_BASE.resolve() not in month_dir.parents:
        return JSONResponse(status_code=400, content={'error': 'Invalid month path'})
    if not month_dir.exists():
        return JSONResponse(status_code=404, content={'error': 'Month not found'})
    shutil.rmtree(month_dir)
    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                conn.execute(_text("DELETE FROM transactions WHERE report_month = :m"), {'m': month})
                conn.execute(_text("DELETE FROM transfers WHERE report_month = :m"), {'m': month})
                conn.commit()
            logging.info(f'Deleted DB rows for {month}')
        except Exception as exc:
            logging.warning(f'Could not delete DB rows for {month}: {exc}')
    logging.info(f'Deleted statements/{month}/ (entire month)')
    return {'success': True}


# ── Process month ─────────────────────────────────────────────────────────────

@router.post("/api/statements/{month}/process")
def process_month(month: str, force: bool = False):
    """Start background processing and return a job_id. Poll /api/jobs/{job_id} for status."""
    if not _is_valid_month(month) and month != 'latest':
        return JSONResponse(status_code=400, content={'error': 'Month must be YYYY-MM format'})

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'output': '', 'errors': '', 'started_at': time.time()}

    process_script  = _PROJECT_ROOT / 'scripts' / 'process_monthly.py'
    aggregate_script = _PROJECT_ROOT / 'scripts' / 'aggregate_monthly.py'

    def _run():
        try:
            cmd = ['python3', str(process_script), '--month', month]
            if force:
                cmd.append('--force')
            r1 = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600, cwd=str(_PROJECT_ROOT)
            )
            with _jobs_lock:
                _jobs[job_id]['output'] += r1.stdout or ''
                _jobs[job_id]['errors'] += r1.stderr or ''
            if r1.returncode != 0:
                with _jobs_lock:
                    stderr = (r1.stderr or '').strip()
                    if stderr:
                        _jobs[job_id]['output'] += '\n\n--- STDERR ---\n' + stderr
                    _jobs[job_id]['status'] = 'error'
                    _jobs[job_id]['error_msg'] = f'process_monthly.py failed (exit {r1.returncode})'
                return
            r2 = subprocess.run(
                ['python3', str(aggregate_script)],
                capture_output=True, text=True, timeout=600, cwd=str(_PROJECT_ROOT)
            )
            with _jobs_lock:
                _jobs[job_id]['output'] += r2.stdout or ''
                _jobs[job_id]['errors'] += r2.stderr or ''
                _jobs[job_id]['status'] = 'done'
            logging.info(f'✅ Processed & aggregated month {month} (job {job_id})')
        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _jobs[job_id]['status'] = 'error'
                _jobs[job_id]['error_msg'] = 'Processing timed out (>60 min)'
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id]['status'] = 'error'
                _jobs[job_id]['error_msg'] = str(e)
            logging.exception('Failed to process month')

    threading.Thread(target=_run, daemon=True).start()
    return {'job_id': job_id}


# ── Job status ────────────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Poll the status of a background processing job."""
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return JSONResponse(status_code=404, content={'error': 'Job not found'})
    return {
        'status':    job['status'],
        'output':    job.get('output', '')[-5000:],
        'errors':    job.get('errors', ''),
        'error_msg': job.get('error_msg', ''),
    }


# ── Aggregate ─────────────────────────────────────────────────────────────────

@router.post("/api/aggregate")
def run_aggregate():
    script = _PROJECT_ROOT / 'scripts' / 'aggregate_monthly.py'
    try:
        result = subprocess.run(
            ['python3', str(script)],
            capture_output=True, text=True, timeout=120, cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            return JSONResponse(status_code=500, content={
                'error': result.stderr[-1000:] if result.stderr else 'aggregate_monthly.py failed'
            })
        logging.info('✅ aggregate_monthly.py ran successfully via dashboard')
        return {'success': True, 'output': result.stdout[-2000:] if result.stdout else ''}
    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=504, content={'error': 'Aggregate timed out after 120s'})
    except Exception as e:
        logging.exception('Failed to run aggregate')
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── Manual review ─────────────────────────────────────────────────────────────

@router.get("/api/manual-review")
def get_manual_review_items():
    """Return all rows from statements/*/manual_review.csv that still need classification."""
    rows = []
    for review_file in sorted(_STATEMENTS_BASE.glob("*/manual_review.csv")):
        month = review_file.parent.name
        try:
            df = pd.read_csv(review_file, sep=None, engine='python')
            for _, row in df.iterrows():
                try:
                    amt = round(float(row.get('Amount', 0)), 2)
                except Exception:
                    amt = 0.0
                rows.append({
                    'month':            month,
                    'date':             str(row.get('Transaction Date', '')).strip(),
                    'place':            str(row.get('Place', '')).strip(),
                    'place_original':   str(row.get('Place_Original', '')).strip(),
                    'amount':           amt,
                    'statement':        str(row.get('Statement', '')).strip(),
                    'current_category': str(row.get('category', '')).strip(),
                })
        except Exception as e:
            logging.warning(f"Could not read {review_file}: {e}")
    return rows


@router.post("/api/manual-review/classify")
def classify_manual_review(payload: dict = Body(...)):
    """
    Classify a manual_review.csv item and write it to the appropriate statement CSV + DB.
    Body: {month, date, original_place, amount, classification, category?, new_place?}
    """
    try:
        month          = str(payload['month']).strip()
        date           = str(payload.get('date', '')).strip()
        original_place = str(payload.get('original_place', '')).strip()
        classification = str(payload.get('classification', '')).strip()
        new_category   = str(payload.get('category', '')).strip()
        new_place      = str(payload.get('new_place', '')).strip()
        try:
            amount = round(float(payload.get('amount', 0)), 2)
        except Exception:
            return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

        if not classification:
            return JSONResponse(status_code=400, content={'error': 'classification is required'})

        review_file = _STATEMENTS_BASE / month / 'manual_review.csv'
        if not review_file.exists():
            return JSONResponse(status_code=404, content={'error': f'No manual_review.csv for {month}'})

        df = pd.read_csv(review_file, sep=None, engine='python')
        place_col      = df['Place'].astype(str).str.strip()
        place_orig_col = df['Place_Original'].astype(str).str.strip() if 'Place_Original' in df.columns else place_col
        mask = (
            (df['Transaction Date'].astype(str).str.strip() == date) &
            (df['Amount'].apply(lambda x: round(float(x), 2)) == amount) &
            (place_col.eq(original_place) | place_orig_col.eq(original_place))
        )
        if not mask.any():
            return JSONResponse(status_code=404, content={'error': 'Row not found in manual_review.csv'})

        if 'Classification' not in df.columns:
            df['Classification'] = ''
        df['Classification'] = df['Classification'].astype(object)
        df.loc[mask, 'Classification'] = classification
        if new_category:
            if 'category' not in df.columns:
                df['category'] = ''
            df['category'] = df['category'].astype(object)
            df.loc[mask, 'category'] = new_category
        if new_place:
            df['Place'] = df['Place'].astype(object)
            df.loc[mask, 'Place'] = new_place

        classified_row = df[mask].iloc[0]
        final_place    = new_place if new_place else str(classified_row['Place']).strip()
        final_category = new_category if new_category else str(classified_row.get('category', '')).strip()
        row_date       = str(classified_row['Transaction Date']).strip()
        row_amount     = round(float(classified_row['Amount']), 2)
        row_statement  = str(classified_row.get('Statement', '')).strip()

        # Delete classified row from manual_review.csv
        remaining = df[~mask]
        if remaining.empty:
            review_file.unlink(missing_ok=True)
            logging.info(f"🗑 Removed manual_review.csv for {month} (all rows classified)")
        else:
            remaining.to_csv(review_file, index=False)
        logging.info(f"📝 Manual review classified: {original_place} → {classification} ({month})")

        stmt_dir = _STATEMENTS_BASE / month

        def _upsert_csv(path: Path, row_dict: dict, dedup_cols: dict) -> bool:
            if path.exists():
                existing = pd.read_csv(path)
                if 'Place' in existing.columns:
                    existing = existing[~existing['Place'].astype(str).str.contains(
                        r'--- EXPENSE BREAKDOWN ---|Total:|GRAND TOTAL',
                        case=False, na=False, regex=True
                    )]
            else:
                existing = pd.DataFrame(columns=list(row_dict.keys()))
            dup = existing
            for col, val in dedup_cols.items():
                if col in dup.columns:
                    dup = dup[dup[col].astype(str).str.strip() == str(val)]
            if dup.empty:
                new_df = pd.concat([existing, pd.DataFrame([row_dict])], ignore_index=True)
                new_df.to_csv(path, index=False)
                return True
            return False

        base_row = {
            'Transaction Date': row_date,
            'Place':            final_place,
            'Amount':           row_amount,
            'Statement':        row_statement,
            'category':         final_category,
            'Label':            'recurring',
        }
        dedup = {'Transaction Date': row_date, 'Place': final_place, 'Amount': str(row_amount)}

        if classification in ('Expense', 'Reimbursement'):
            amount_to_write = -abs(row_amount) if classification == 'Reimbursement' else row_amount
            exp_row = {**base_row, 'Amount': amount_to_write}
            wrote_stmts = _upsert_csv(stmt_dir / 'expenses.csv', exp_row, dedup)
            if wrote_stmts:
                logging.info(f"✅ Added {final_place} ${row_amount} to expenses statements ({month})")
            if _DB_AVAILABLE:
                try:
                    from sqlalchemy import text as _text
                    from src.database.db_utils import _make_hash
                    tx_hash = _make_hash(month, row_date, final_place, amount_to_write, 'expense', row_statement)
                    with get_engine().connect() as conn:
                        conn.execute(_text(
                            "INSERT OR IGNORE INTO transactions "
                            "(tx_hash, report_month, tx_date, place, amount, category, label, tx_type, statement, user_corrected) "
                            "VALUES (:h, :m, :d, :p, :a, :c, :l, 'expense', :s, 0)"
                        ), {'h': tx_hash, 'm': month, 'd': row_date, 'p': final_place,
                            'a': amount_to_write, 'c': final_category, 'l': 'recurring', 's': row_statement})
                        conn.commit()
                except Exception as exc:
                    logging.warning(f'DB insert for classified expense failed: {exc}')

        elif classification == 'Income':
            wrote_stmts = _upsert_csv(stmt_dir / 'income.csv', base_row, dedup)
            if wrote_stmts:
                logging.info(f"✅ Added {final_place} ${row_amount} to income statements ({month})")
            if _DB_AVAILABLE:
                try:
                    from sqlalchemy import text as _text
                    from src.database.db_utils import _make_hash
                    tx_hash = _make_hash(month, row_date, final_place, row_amount, 'income', row_statement)
                    with get_engine().connect() as conn:
                        conn.execute(_text(
                            "INSERT OR IGNORE INTO transactions "
                            "(tx_hash, report_month, tx_date, place, amount, category, label, tx_type, statement, user_corrected) "
                            "VALUES (:h, :m, :d, :p, :a, :c, :l, 'income', :s, 0)"
                        ), {'h': tx_hash, 'm': month, 'd': row_date, 'p': final_place,
                            'a': row_amount, 'c': final_category, 'l': 'recurring', 's': row_statement})
                        conn.commit()
                except Exception as exc:
                    logging.warning(f'DB insert for classified income failed: {exc}')

        place_lower    = final_place.lower()
        is_inv_expense = classification in ('Expense', 'Reimbursement') and final_category in _INVESTMENT_CATEGORIES
        is_inv_income  = classification == 'Income' and any(kw in place_lower for kw in _INVESTMENT_PLATFORM_KEYWORDS)
        if is_inv_expense or is_inv_income:
            try:
                _rebuild_transfers_for_month(month)
                logging.info(f'Rebuilt transfers for {month} after classifying {final_place} as {classification}/{final_category}')
            except Exception as exc:
                logging.warning(f'Could not rebuild transfers: {exc}')

        return {'success': True, 'output': '', 'errors': ''}
    except Exception as e:
        logging.exception('Failed to classify manual review item')
        return JSONResponse(status_code=500, content={'error': str(e)})
