"""routes/statements.py — Statement file management, processing jobs, and manual review."""

import logging
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, UploadFile
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
