
from fastapi import FastAPI, Body, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import csv
from collections import defaultdict
import re
import requests
import pandas as pd
import sys
import threading
import uuid
import time
import logging
import json as _json
import shutil
from datetime import datetime
import os

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# ── Background job store ──────────────────────────────────────────────────────
_jobs: dict = {}  # job_id → {status, output, errors, started_at}

app = FastAPI(
    title="Automated Budgeting API",
    description="API for processing bank statements and generating financial reports",
    version="1.0.0"
)

# Allow React dev server to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CONFIG_ROOT = Path(__file__).parent.parent.parent.parent / "config"
# Runtime data written by the UI (labels, manual entries) — kept separate from static config
_DATA_ROOT  = Path(__file__).parent.parent / "data"
_DATA_ROOT.mkdir(parents=True, exist_ok=True)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_STATEMENTS_BASE = _DATA_ROOT / 'statements'              # all statement files (PDFs, TXTs, CSVs)
_WRITE_API_KEY = os.environ.get('AUTOBUDGET_API_KEY', '').strip()

_jobs_lock = threading.Lock()


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


@app.middleware("http")
async def _write_auth_middleware(request: Request, call_next):
    if _WRITE_API_KEY and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.url.path.startswith('/api/'):
        provided = request.headers.get('x-api-key', '').strip()
        if provided != _WRITE_API_KEY:
            return JSONResponse(status_code=401, content={'error': 'Unauthorized'})
    return await call_next(request)

# Mount React build directory for dashboard
react_build_path = Path(__file__).parent.parent / "build"
if react_build_path.exists():
    app.mount("/static", StaticFiles(directory=str(react_build_path / "static")), name="static")

# Serve React dashboard at root
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the React dashboard"""
    index_path = Path(__file__).parent.parent / "build" / "index.html"
    if index_path.exists():
        with open(index_path, 'r') as f:
            return f.read()
    # Fallback if React not built    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Automated Budgeting</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 700px;
                margin: 80px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .card {
                background: white;
                padding: 50px;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }
            h1 {
                color: #2c3e50;
                margin: 0 0 10px 0;
                font-size: 2.5em;
            }
            .subtitle {
                color: #7f8c8d;
                margin: 0 0 40px 0;
                font-size: 1.1em;
            }
            .status {
                display: inline-block;
                background: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 20px;
                font-weight: bold;
                margin-bottom: 40px;
            }
            .links {
                display: flex;
                gap: 15px;
                justify-content: center;
                margin: 30px 0;
            }
            .btn {
                flex: 1;
                padding: 15px 25px;
                background: #3498db;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                transition: all 0.3s;
                display: block;
            }
            .btn:hover {
                background: #2980b9;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(52, 152, 219, 0.4);
            }
            .btn.secondary {
                background: #95a5a6;
            }
            .btn.secondary:hover {
                background: #7f8c8d;
            }
            .info {
                margin-top: 40px;
                padding: 20px;
                background: #ecf0f1;
                border-radius: 8px;
                font-size: 0.95em;
            }
            .info h3 {
                margin-top: 0;
                color: #34495e;
            }
            ul {
                text-align: left;
                color: #555;
            }
            .footer {
                margin-top: 30px;
                color: #95a5a6;
                font-size: 0.85em;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🏦 Automated Budgeting</h1>
            <p class="subtitle">Turn PDFs into organized spreadsheets</p>
            
            <div class="status">✅ System Ready</div>
            
            <div class="links">
                <a href="/docs" class="btn">📊 View API</a>
                <a href="/redoc" class="btn secondary">📖 Documentation</a>
            </div>
            
            <div class="info">
                <h3>🚀 Quick Start</h3>
                <ul>
                    <li>Put your PDF statements in <code>statements/YYYY-MM/</code></li>
                    <li>Run: <code>make process MONTH=YYYY-MM</code></li>
                    <li>Get organized CSV files in <code>monthly_reports/</code></li>
                </ul>
            </div>
            
            <div class="footer">
                Running in Docker • Powered by Ollama LLM
            </div>
        </div>
    </body>
    </html>
    """

# New endpoint for last 12 months income (for bar graph)
@app.get("/api/income-by-month")
def get_income_by_month():
    base_path = _DATA_ROOT / "monthly_reports"

    results = []
    for income_path in sorted(base_path.glob("income_*.csv")):
        month_str = income_path.stem.replace("income_", "")
        if not month_str:
            continue
        recurring_total = 0.0
        bonus_total = 0.0
        with open(income_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    continue
                # Income from investment platforms (auto-detected by place name) is
                # tracked in the Investments tab as Direction=In, not as regular income.
                place_lower = str(row.get('Place', '')).strip().lower()
                if any(kw in place_lower for kw in _INVESTMENT_PLATFORM_KEYWORDS):
                    continue
                label = str(row.get("Label", "recurring")).strip().lower()
                # Reimbursements live in expenses.csv as negatives — don't count here
                if label == 'reimbursement':
                    continue
                if label == "bonus":
                    bonus_total += amount
                else:
                    recurring_total += amount
        results.append({
            "month": month_str,
            "income": round(recurring_total, 2),          # recurring only (for avg baseline)
            "bonus": round(bonus_total, 2),               # bonus tracked separately
            "total_income": round(recurring_total + bonus_total, 2),
        })
    return results


# ── Income & Expense Label Helpers ──────────────────────────────────────────

def _update_csv_label(csv_path: Path, date: str, place: str, amount: float, new_label: str) -> bool:
    """Find the matching row in a monthly_reports CSV and update its Label column in-place."""
    try:
        import pandas as _pd
        df = _pd.read_csv(csv_path)
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
    except Exception as e:
        logging.warning(f"_update_csv_label failed on {csv_path}: {e}")
        return False


@app.get("/api/income-breakdown")
def get_income_breakdown():
    """Return all income rows from the last 12 months with labels (recurring/bonus)."""
    base_path = _DATA_ROOT / "monthly_reports"
    rows = []
    for f in sorted(base_path.glob("income_*.csv")):
        month_str = f.stem.replace('income_', '')
        try:
            with open(f, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    place = row.get('Place', '')
                    try:
                        amount = round(float(row.get('Amount', 0)), 2)
                    except Exception:
                        continue
                    if str(row.get('category', '')).strip() == 'Investment Return':
                        continue
                    rows.append({
                        'date':   row.get('Transaction Date', ''),
                        'place':  place,
                        'amount': amount,
                        'month':  month_str,
                        'label':  str(row.get('Label', 'recurring')).strip() or 'recurring',
                    })
        except Exception as e:
            logging.warning(f"Could not read {f}: {e}")
    return rows


@app.get("/api/income-entries")
def get_income_entries(month: str = ''):
    """
    Return raw income rows for a given month (or all months), including category.
    Used by the Investments tab to surface potential investment returns.
    """
    base_path = _DATA_ROOT / 'monthly_reports'
    rows = []
    pattern = f'income_{month}.csv' if month else 'income_*.csv'
    for f in sorted(base_path.glob(pattern)):
        month_str = f.stem.replace('income_', '')
        try:
            df = pd.read_csv(f)
            if 'category' not in df.columns:
                df['category'] = ''
            for _, row in df.iterrows():
                place = str(row.get('Place', '')).strip()
                try:
                    amount = round(float(row.get('Amount', 0)), 2)
                except Exception:
                    continue
                def _clean(v): return '' if str(v).strip().lower() in ('nan', 'none', '') else str(v).strip()
                rows.append({
                    'date':     str(row.get('Transaction Date', '')).strip(),
                    'place':    place,
                    'amount':   amount,
                    'month':    month_str,
                    'statement': str(row.get('Statement', '')).strip(),
                    'label':    _clean(row.get('Label', '')) or 'recurring',
                    'category': _clean(row.get('category', '')),
                })
        except Exception as e:
            logging.warning(f'Could not read {f}: {e}')
    return rows


@app.patch("/api/income/categorize")
def categorize_income(payload: dict = Body(...)):
    """
    Set or clear the category on an income row.
    Writes to monthly_reports/income_YYYY-MM.csv AND statements/YYYY-MM/income.csv.
    If category is 'Investment Return', also rebuilds transfers for this month.
    """
    month  = str(payload.get('month', '')).strip()
    date   = str(payload.get('date', '')).strip()
    place  = str(payload.get('place', '')).strip()
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

    ok1 = _apply_category(_DATA_ROOT / 'monthly_reports' / f'income_{month}.csv')
    _apply_category(_STATEMENTS_BASE / month / 'income.csv')

    if not ok1:
        return JSONResponse(status_code=404, content={'error': 'Row not found in income report'})

    # Rebuild transfers for this month so Direction=In rows appear immediately
    try:
        _rebuild_transfers_for_month(month)
    except Exception as exc:
        logging.warning(f'Could not rebuild transfers after income categorize: {exc}')

    logging.info(f'Income categorized: {place} [{month}] → {category}')
    return {'success': True}


@app.post("/api/income/label")
def set_income_label(payload: dict = Body(...)):
    """Update the Label column for an income row directly in the monthly_reports CSV."""
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
    base_path = _DATA_ROOT / "monthly_reports"
    csv_path = base_path / f"income_{month}.csv"
    if not csv_path.exists():
        return JSONResponse(status_code=404, content={'error': f'No income file for {month}'})
    ok = _update_csv_label(csv_path, date, place, amount, label)
    return {'ok': ok, 'date': date, 'place': place, 'amount': amount, 'label': label}


@app.post("/api/income/reclassify-as-reimbursement")
def reclassify_income_as_reimbursement(payload: dict = Body(...)):
    """
    Move an income row into the expenses CSV as a reimbursement (negative amount).
    Removes the row from income_YYYY-MM.csv and appends it to expenses_YYYY-MM.csv.
    """
    date  = str(payload.get('date', '')).strip()
    place = str(payload.get('place', '')).strip()
    month = str(payload.get('month', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    reports_dir = _DATA_ROOT / 'monthly_reports'
    income_report = reports_dir / f'income_{month}.csv'
    expense_report = reports_dir / f'expenses_{month}.csv'

    if not income_report.exists():
        return JSONResponse(status_code=404, content={'error': f'No income file for {month}'})

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
                # Ensure category column exists
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

    ok = _move_row(income_report, expense_report)
    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in income report'})

    # Best-effort: also update source statement CSVs
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _move_row(stmt_dir / 'income.csv', stmt_dir / 'expenses.csv')

    logging.info(f'Reclassified income as reimbursement: {place} [{month}] ${amount}')
    return {'success': True}


@app.post("/api/expense/reclassify-as-income")
def reclassify_expense_as_income(payload: dict = Body(...)):
    """
    Move an expense row into the income CSV.
    Removes the row from expenses_YYYY-MM.csv and appends it to income_YYYY-MM.csv.
    """
    date  = str(payload.get('date', '')).strip()
    place = str(payload.get('place', '')).strip()
    month = str(payload.get('month', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    reports_dir = _DATA_ROOT / 'monthly_reports'
    expense_report = reports_dir / f'expenses_{month}.csv'
    income_report  = reports_dir / f'income_{month}.csv'

    if not expense_report.exists():
        return JSONResponse(status_code=404, content={'error': f'No expenses file for {month}'})

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

    ok = _move_row(expense_report, income_report)
    if not ok:
        return JSONResponse(status_code=404, content={'error': 'Row not found in expenses report'})

    # Best-effort: also update source statement CSVs
    for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
        if stmt_dir.is_dir():
            _move_row(stmt_dir / 'expenses.csv', stmt_dir / 'income.csv')

    # If the place is a known investment platform, rebuild transfers so the new
    # income row appears immediately as Direction=In without any manual step.
    if any(kw in place.lower() for kw in _INVESTMENT_PLATFORM_KEYWORDS):
        try:
            _rebuild_transfers_for_month(month)
        except Exception as exc:
            logging.warning(f'Could not rebuild transfers after income reclassification: {exc}')

    logging.info(f'Reclassified expense as income: {place} [{month}] ${amount}')
    return {'success': True}


@app.get("/api/one-time-expenses")
def get_one_time_expenses():
    """Return all expense rows labelled one-time from the last 12 months."""
    base_path = _DATA_ROOT / "monthly_reports"
    rows = []
    for f in sorted(base_path.glob("expenses_*.csv")):
        month_str = f.stem.replace('expenses_', '')
        try:
            with open(f, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    place = row.get('Place', '')
                    if 'EXPENSE BREAKDOWN' in place.upper() or 'TOTAL:' in place.upper() or 'GRAND TOTAL' in place.upper():
                        continue
                    label = str(row.get('Label', 'recurring')).strip()
                    if label != 'one-time':
                        continue
                    try:
                        amount = round(float(row.get('Amount', 0)), 2)
                    except Exception:
                        continue
                    rows.append({
                        'date':     row.get('Transaction Date', ''),
                        'place':    place,
                        'amount':   amount,
                        'month':    month_str,
                        'category': row.get('category', ''),
                        'label':    label,
                    })
        except Exception as e:
            logging.warning(f"Could not read {f}: {e}")
    return rows


@app.post("/api/expense/label")
def set_expense_label(payload: dict = Body(...)):
    """Update the Label column for an expense row directly in the monthly_reports CSV."""
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
    base_path = _DATA_ROOT / "monthly_reports"
    csv_path = base_path / f"expenses_{month}.csv"
    if not csv_path.exists():
        return JSONResponse(status_code=404, content={'error': f'No expense file for {month}'})
    ok = _update_csv_label(csv_path, date, place, amount, label)
    return {'ok': ok, 'date': date, 'place': place, 'amount': amount, 'label': label}


# ── Investment Transfers ─────────────────────────────────────────────────────

def _load_transfer_labels() -> dict:
    """Return {(date, place_upper, amount): label} from transfer_labels.json."""
    try:
        with open(_DATA_ROOT / 'transfer_labels.json') as f:
            return {
                (str(e['date']).strip(), str(e['place']).strip().upper(), round(float(e['amount']), 2)): e['label']
                for e in _json.load(f).get('labels', [])
            }
    except Exception:
        return {}


@app.get("/api/transfers")
def get_transfers():
    """Return all investment transfer rows with Retirement/Personal labels applied."""
    base_path = _DATA_ROOT / "monthly_reports"
    labels = _load_transfer_labels()
    rows = []
    for f in sorted(base_path.glob("transfers_*.csv")):
        month_str = f.stem.replace('transfers_', '')
        try:
            with open(f, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    place = row.get('Place', '')
                    date  = row.get('Transaction Date', '')
                    try:
                        amount = round(float(row.get('Amount', 0)), 2)
                    except Exception:
                        amount = 0.0
                    direction = row.get('Direction', 'In')
                    label = labels.get((date.strip(), place.strip().upper(), amount))
                    rows.append({
                        'date':      date,
                        'place':     place,
                        'amount':    amount,
                        'month':     month_str,
                        'statement': row.get('Statement', ''),
                        'direction': direction,
                        'label':     label,
                    })
        except Exception as e:
            logging.warning(f"Could not read transfers file {f}: {e}")

    # Merge manually added transfers — apply any label overrides from transfer_labels.json
    for r in _load_manual_transfers():
        override = labels.get((str(r['date']).strip(), str(r['place']).strip().upper(), round(float(r['amount']), 2)))
        rows.append({**r, 'label': override if override is not None else r.get('label')})

    return rows


@app.post("/api/transfers/label")
def set_transfer_label(payload: dict = Body(...)):
    """Set or clear a Retirement / Personal label on an investment transfer row."""
    date  = str(payload.get('date', '')).strip()
    place = str(payload.get('place', '')).strip()
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})
    label = payload.get('label')  # 'Retirement' | 'Personal' | None to clear

    excl_path = _DATA_ROOT / 'transfer_labels.json'
    try:
        with open(excl_path) as f:
            data = _json.load(f)
    except Exception:
        data = {'labels': []}

    # Remove any existing entry for this transaction
    labels_list = [
        e for e in data.get('labels', [])
        if not (str(e.get('date', '')).strip() == date
                and str(e.get('place', '')).strip().upper() == place.upper()
                and round(float(e.get('amount', 0)), 2) == amount)
    ]

    if label in ('Retirement', 'Personal'):
        labels_list.append({'date': date, 'place': place, 'amount': amount, 'label': label})

    data['labels'] = labels_list
    with open(excl_path, 'w') as f:
        _json.dump(data, f, indent=2)

    logging.info(f"Transfer label set: {date} {place} ${amount} → {label}")
    return {'date': date, 'place': place, 'amount': amount, 'label': label}


# ── Manual Investment Transfers ──────────────────────────────────────────────

_MANUAL_TRANSFERS_FILE = _DATA_ROOT / 'manual_investment_transfers.json'


def _load_manual_transfers() -> list:
    if not _MANUAL_TRANSFERS_FILE.exists():
        return []
    try:
        with open(_MANUAL_TRANSFERS_FILE) as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_manual_transfers(records: list) -> None:
    _MANUAL_TRANSFERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MANUAL_TRANSFERS_FILE, 'w') as f:
        _json.dump(records, f, indent=2)


@app.post("/api/transfers/manual")
def add_manual_transfer(payload: dict = Body(...)):
    """
    Add a manual investment transfer (e.g. a payment-app investment that shouldn't
    be a blanket keyword match).  Body: {date, place, amount, direction, label}
    """
    try:
        required = ['date', 'place', 'amount', 'direction']
        for field in required:
            if field not in payload:
                return JSONResponse(status_code=400, content={'error': f'Missing field: {field}'})

        dt = datetime.strptime(payload['date'], '%Y-%m-%d')
        month = dt.strftime('%Y-%m')
        csv_date = dt.strftime('%-m/%-d/%Y')

        record = {
            'id':        str(uuid.uuid4()),
            'date':      csv_date,         # MM/DD/YYYY to match auto-detected rows
            'place':     payload['place'].strip(),
            'amount':    round(float(payload['amount']), 2),
            'direction': payload.get('direction', 'Out'),   # 'In' or 'Out'
            'label':     payload.get('label') or None,       # 'Retirement' | 'Personal' | None
            'month':     month,
            'statement': 'Manual',
            'manual':    True,
        }

        records = _load_manual_transfers()
        records.append(record)
        _save_manual_transfers(records)

        logging.info(f"✏️ Manual transfer added: {record['place']} ${record['amount']} {record['direction']} ({month})")
        return {'success': True, 'transfer': record}

    except Exception as e:
        logging.exception('Failed to add manual transfer')
        return JSONResponse(status_code=500, content={'error': str(e)})


@app.delete("/api/transfers/manual/{tx_id}")
def delete_manual_transfer(tx_id: str):
    """Delete a manually added investment transfer by ID."""
    try:
        records = _load_manual_transfers()
        target = next((r for r in records if r['id'] == tx_id), None)
        if target is None:
            return JSONResponse(status_code=404, content={'error': 'Not found'})
        records = [r for r in records if r['id'] != tx_id]
        _save_manual_transfers(records)
        logging.info(f"🗑️ Manual transfer deleted: {target['place']} ${target['amount']}")
        return {'success': True}
    except Exception as e:
        logging.exception('Failed to delete manual transfer')
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── All-Expenses Browse & Inline Edit ────────────────────────────────────────

@app.get("/api/available-months")
def get_available_months():
    """Return sorted list of months that have expenses data in monthly_reports/."""
    base_path = _DATA_ROOT / "monthly_reports"
    months = sorted(
        [p.stem.replace('expenses_', '') for p in base_path.glob('expenses_*.csv')],
        reverse=True
    )
    return months


@app.get("/api/all-expenses")
def get_all_expenses(month: str = None, category: str = None, search: str = None):
    """Return expense rows from monthly_reports, optionally filtered by month/category/search."""
    base_path = _DATA_ROOT / "monthly_reports"
    rows = []
    files = sorted(base_path.glob("expenses_*.csv"))
    if month:
        files = [f for f in files if f.stem == f"expenses_{month}"]
    for f in files:
        month_str = f.stem.replace('expenses_', '')
        try:
            df = pd.read_csv(f)
            df = df[~df['Place'].astype(str).str.contains(
                'EXPENSE BREAKDOWN|Total:|GRAND TOTAL', case=False, na=False, regex=True
            )]
            for idx, row in df.iterrows():
                place = str(row.get('Place', '')).strip()
                if search and search.lower() not in place.lower():
                    continue
                cat = str(row.get('category', '')).strip()
                if category and cat.lower() != category.lower():
                    continue
                try:
                    amount = round(float(row.get('Amount', 0)), 2)
                except Exception:
                    continue
                rows.append({
                    'date':      str(row.get('Transaction Date', '')).strip(),
                    'place':     place,
                    'amount':    amount,
                    'category':  cat,
                    'label':     str(row.get('Label', 'recurring')).strip(),
                    'statement': str(row.get('Statement', '')).strip(),
                    'month':     month_str,
                    'row_idx':   int(idx),
                })
        except Exception as e:
            logging.warning(f"Could not read {f}: {e}")
    return rows


_INVESTMENT_CATEGORIES = {'Investment', 'Investment Transfer'}

# TODO: Move this list to config/investment_platforms.json and load it at startup
# so platforms can be added/removed without a code change or container rebuild.
# See docs/FUTURE_FEATURES.md — Technical Debt > High Priority (database-backed merchant metadata).
#
# Place-name keywords that identify income as coming from an investment platform.
# Income matching these is automatically included as Direction=In in the transfers
# rebuild without requiring the user to manually tag it as 'Investment Return'.
_INVESTMENT_PLATFORM_KEYWORDS = [
    'investment', 'brokerage', 'trading', 'portfolio', 'securities', 'fund',
    'robinhood', 'edward jones', 'cash app', 'vanguard', 'fidelity', 'schwab',
    'ameritrade', 'webull', 'acorns', 'stash', 'betterment', 'wealthfront', 'sofi',
]

def _rebuild_transfers_for_month(month: str) -> None:
    """Rebuild transfers_YYYY-MM.csv for a single month from source statements + current expenses."""
    reports_dir    = _DATA_ROOT / 'monthly_reports'
    statements_dir = _STATEMENTS_BASE
    transfers_out  = reports_dir / f'transfers_{month}.csv'

    # 1. Collect raw statement transfers whose parsed date falls in this month
    raw_rows = []
    for stmt_dir in sorted(statements_dir.glob('*')):
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

    # 2. Extract investment rows from the current expenses report for this month.
    #    Also build a set of (date, amount) pairs that are explicitly categorised
    #    as non-investment so we can exclude them from the raw statement transfers above.
    #    We match on (date, amount) only — name may have been renamed by the user.
    exp_file = reports_dir / f'expenses_{month}.csv'
    non_investment_keys: set = set()
    if exp_file.exists():
        try:
            edf = pd.read_csv(exp_file)
            if 'category' in edf.columns:
                # Rows the user re-categorised away from investment
                non_inv = edf[~edf['category'].astype(str).str.strip().isin(_INVESTMENT_CATEGORIES)]
                for _, row in non_inv.iterrows():
                    try:
                        non_investment_keys.add((
                            str(row['Transaction Date']).strip(),
                            round(float(row['Amount']), 2),
                        ))
                    except Exception:
                        pass

                inv = edf[edf['category'].astype(str).str.strip().isin(_INVESTMENT_CATEGORIES)].copy()
                if not inv.empty:
                    t = pd.DataFrame({
                        'Transaction Date': inv['Transaction Date'].values,
                        'Place':            inv['Place'].values,
                        'Amount':           inv['Amount'].abs().values,
                        'Direction':        'Out',
                        'Statement':        inv['Statement'].values if 'Statement' in inv.columns else 'Manual',
                    })
                    raw_rows.append(t)
        except Exception as exc:
            logging.warning(f'Could not read {exp_file}: {exc}')

    # Remove any raw statement transfer rows that the user has re-categorised as
    # a non-investment expense — the expense CSV is the authoritative source.
    # Match on (date, amount) since the place name may have been changed by the user.
    if non_investment_keys and raw_rows:
        filtered = []
        for df_chunk in raw_rows:
            def _key(r):
                try:
                    return (str(r['Transaction Date']).strip(),
                            round(float(r['Amount']), 2))
                except Exception:
                    return None
            keep = df_chunk.apply(lambda r: _key(r) not in non_investment_keys, axis=1)
            filtered.append(df_chunk[keep])
        raw_rows = filtered

    # 3. Extract investment income rows from the current income report for this month.
    #    Includes rows explicitly tagged as 'Investment Return' AND rows whose place
    #    name matches a known investment platform — no manual tagging required.
    inc_file = reports_dir / f'income_{month}.csv'
    if inc_file.exists():
        try:
            idf = pd.read_csv(inc_file)
            if 'category' not in idf.columns:
                idf['category'] = ''
            is_tagged = idf['category'].astype(str).str.strip() == 'Investment Return'
            is_platform = idf['Place'].astype(str).str.lower().apply(
                lambda p: any(kw in p for kw in _INVESTMENT_PLATFORM_KEYWORDS)
            )
            ret = idf[is_tagged | is_platform].copy()
            if not ret.empty:
                t = pd.DataFrame({
                    'Transaction Date': ret['Transaction Date'].values,
                    'Place':            ret['Place'].values,
                    'Amount':           ret['Amount'].values,
                    'Direction':        'In',
                    'Statement':        ret['Statement'].values if 'Statement' in ret.columns else 'Manual',
                })
                raw_rows.append(t)
        except Exception as exc:
            logging.warning(f'Could not read {inc_file}: {exc}')

    if not raw_rows:
        # No transfers at all — write an empty file so stale data is cleared
        pd.DataFrame(columns=['Transaction Date', 'Place', 'Amount', 'Direction', 'Statement']).to_csv(transfers_out, index=False)
        return

    combined = pd.concat(raw_rows, ignore_index=True)
    dedup_cols = [c for c in combined.columns if c not in ('Source', 'Statement')]
    combined = combined.drop_duplicates(subset=dedup_cols, keep='first')
    combined = combined.sort_values('Transaction Date')
    combined.to_csv(transfers_out, index=False)
    logging.info(f'Rebuilt transfers for {month}: {len(combined)} row(s)')


@app.patch("/api/expense/edit")
def edit_expense(payload: dict = Body(...)):
    """
    Update place/category/label of a specific expense row in-place.
    Identifies row by row_idx (preferred) or falls back to {date, original_place, amount, month}.
    """
    month = str(payload.get('month', '')).strip()
    date  = str(payload.get('date', '')).strip()
    original_place = str(payload.get('original_place', '')).strip()
    row_idx = payload.get('row_idx')  # stable CSV row index — avoids stale-name mismatches
    try:
        amount = round(float(payload.get('amount', 0)), 2)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid amount'})

    base_path = _DATA_ROOT / "monthly_reports"
    csv_path = base_path / f"expenses_{month}.csv"
    if not csv_path.exists():
        return JSONResponse(status_code=404, content={'error': f'No expenses file for {month}'})

    try:
        df = pd.read_csv(csv_path)
        # Prefer stable row index lookup; fall back to field matching
        if row_idx is not None and int(row_idx) in df.index:
            mask = df.index == int(row_idx)
        else:
            mask = (
                (df['Transaction Date'].astype(str).str.strip() == date) &
                (df['Place'].astype(str).str.strip() == original_place) &
                (df['Amount'].apply(lambda x: round(float(x), 2)) == amount)
            )
        if not mask.any():
            return JSONResponse(status_code=404, content={'error': 'Row not found'})

        # Capture old category before we overwrite it
        old_category = str(df.loc[mask, 'category'].iloc[0]).strip() if 'category' in df.columns else ''

        if payload.get('new_place'):
            df.loc[mask, 'Place'] = str(payload['new_place']).strip()
        if payload.get('new_category'):
            df.loc[mask, 'category'] = str(payload['new_category']).strip()
            # Mark this row as explicitly user-corrected so _restore_user_categories
            # in aggregate_monthly.py knows to preserve it across re-aggregations.
            if 'user_corrected' not in df.columns:
                df['user_corrected'] = False
            df['user_corrected'] = df['user_corrected'].astype(object)
            df.loc[mask, 'user_corrected'] = True
        if payload.get('new_label'):
            df.loc[mask, 'Label'] = str(payload['new_label']).strip()
        if payload.get('new_amount') is not None:
            df.loc[mask, 'Amount'] = round(float(payload['new_amount']), 2)

        df.to_csv(csv_path, index=False)
        logging.info(f"✏️ Expense edited: {original_place} → {payload.get('new_place') or original_place} [{month}]")

        # ── Also write correction back to the source statements CSV so it survives re-aggregation ──
        # The transaction's calendar month (e.g. 2026-01) may differ from the statement folder
        # it physically lives in (e.g. statements/2026-02/expenses.csv spans Dec-Jan).
        # Search the matching-month folder first, then fall back to all statement folders.
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
                if payload.get('new_place'):    src_df.loc[src_mask, 'Place']    = str(payload['new_place']).strip()
                if payload.get('new_category'): src_df.loc[src_mask, 'category'] = str(payload['new_category']).strip()
                if payload.get('new_label'):    src_df.loc[src_mask, 'Label']    = str(payload['new_label']).strip()
                if payload.get('new_amount') is not None: src_df.loc[src_mask, 'Amount'] = round(float(payload['new_amount']), 2)
                src_df.to_csv(src_csv, index=False)
                return True
            except Exception as exc:
                logging.warning(f'Could not write back to {src_csv}: {exc}')
                return False

        # Try same-name month folder first (fast path)
        if not _apply_src_edit(_STATEMENTS_BASE / month / 'expenses.csv'):
            # Fall back: search all statement folders (handles cross-month statements)
            for stmt_dir in sorted(_STATEMENTS_BASE.iterdir()):
                if stmt_dir.is_dir() and stmt_dir.name != month:
                    if _apply_src_edit(stmt_dir / 'expenses.csv'):
                        break

        # ── If an investment category was added or removed, rebuild transfers for this month ──
        new_category = str(payload.get('new_category', '')).strip()
        if new_category or old_category:
            touches_investment = (
                old_category in _INVESTMENT_CATEGORIES or
                new_category in _INVESTMENT_CATEGORIES
            )
            if touches_investment:
                try:
                    _rebuild_transfers_for_month(month)
                except Exception as exc:
                    logging.warning(f'Could not rebuild transfers for {month}: {exc}')

        return {'success': True}
    except Exception as e:
        logging.exception('Failed to edit expense')
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── Manual Review ─────────────────────────────────────────────────────────────

@app.get("/api/manual-review")
def get_manual_review_items():
    """Return all rows from statements/*/manual_review.csv that still need classification."""
    statements_root = _STATEMENTS_BASE
    rows = []
    for review_file in sorted(statements_root.glob("*/manual_review.csv")):
        month = review_file.parent.name
        try:
            df = pd.read_csv(review_file, sep=None, engine='python')
            # After classifying via GUI, rows are deleted from this file.
            # Any rows still here are pending classification.
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


@app.post("/api/manual-review/classify")
def classify_manual_review(payload: dict = Body(...)):
    """
    Classify a manual_review.csv item: write Classification + optional category/name rename,
    then trigger process_monthly.py --manual-only --month YYYY-MM.
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

        statements_root = _STATEMENTS_BASE
        review_file = statements_root / month / 'manual_review.csv'
        if not review_file.exists():
            return JSONResponse(status_code=404, content={'error': f'No manual_review.csv for {month}'})

        df = pd.read_csv(review_file, sep=None, engine='python')
        place_col     = df['Place'].astype(str).str.strip()
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

        # ── Capture the classified row before deleting it from manual_review ──
        classified_row = df[mask].iloc[0]
        final_place    = new_place if new_place else str(classified_row['Place']).strip()
        final_category = new_category if new_category else str(classified_row.get('category', '')).strip()
        row_date       = str(classified_row['Transaction Date']).strip()
        row_amount     = round(float(classified_row['Amount']), 2)
        row_statement  = str(classified_row.get('Statement', '')).strip()

        # ── Delete the classified row from manual_review.csv ──
        remaining = df[~mask]
        if remaining.empty:
            review_file.unlink(missing_ok=True)
            logging.info(f"🗑 Removed manual_review.csv for {month} (all rows classified)")
        else:
            remaining.to_csv(review_file, index=False)
        logging.info(f"📝 Manual review classified: {original_place} → {classification} ({month})")

        # ── Write the classified row to BOTH statements/ and monthly_reports/ CSVs ──
        # Writing to statements/ ensures the data survives if aggregate_monthly.py reruns.
        reports_dir     = _DATA_ROOT / 'monthly_reports'
        stmt_dir        = statements_root / month

        def _upsert_csv(path, row_dict, dedup_cols):
            """Append row_dict to a CSV if not already present (checked via dedup_cols)."""
            if path.exists():
                existing = pd.read_csv(path)
                # Strip summary rows from monthly_reports CSVs
                if 'Place' in existing.columns:
                    existing = existing[~existing['Place'].astype(str).str.contains(
                        r'--- EXPENSE BREAKDOWN ---|Total:|GRAND TOTAL', case=False, na=False, regex=True
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
            wrote_reports = _upsert_csv(reports_dir / f'expenses_{month}.csv', exp_row, dedup)
            wrote_stmts   = _upsert_csv(stmt_dir / 'expenses.csv',              exp_row, dedup)
            if wrote_reports or wrote_stmts:
                logging.info(f"✅ Added {final_place} ${row_amount} to expenses ({month})")

        elif classification == 'Income':
            wrote_reports = _upsert_csv(reports_dir / f'income_{month}.csv', base_row, dedup)
            wrote_stmts   = _upsert_csv(stmt_dir / 'income.csv',              base_row, dedup)
            if wrote_reports or wrote_stmts:
                logging.info(f"✅ Added {final_place} ${row_amount} to income ({month})")

        # Rebuild transfers if this row affects the investments tab:
        # - Expense with an investment category (Direction=Out)
        # - Income from a known investment platform (Direction=In)
        place_lower = final_place.lower()
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


# ── Statements Management ────────────────────────────────────────────────────

_STATEMENTS_ROOT = lambda: _STATEMENTS_BASE


@app.get("/api/statements")
def list_statements():
    """Return all statement months with their PDF/CSV file lists."""
    root = _STATEMENTS_ROOT()
    months = []
    for d in sorted(root.iterdir(), reverse=True):
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
        months.append({'month': d.name, 'files': files})
    return months


@app.post("/api/statements/{month}/upload")
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


@app.delete("/api/statements/{month}/{filename}")
def delete_statement_file(month: str, filename: str):
    """Delete a file from statements/YYYY-MM/."""
    try:
        target = _safe_statement_path(month, filename)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={'error': str(exc)})
    if not target.exists():
        return JSONResponse(status_code=404, content={'error': 'File not found'})
    # Only allow deleting PDFs (not auto-generated CSVs)
    if target.suffix.lower() != '.pdf':
        return JSONResponse(status_code=400, content={'error': 'Can only delete PDF files'})
    target.unlink()
    logging.info(f'Deleted statements/{month}/{target.name}')
    return {'success': True}


@app.delete("/api/statements/{month}")
def delete_statement_month(month: str):
    """Delete an entire statement month folder and all its contents."""
    if not _is_valid_month(month):
        return JSONResponse(status_code=400, content={'error': 'Month must be YYYY-MM format'})
    month_dir = (_STATEMENTS_BASE / month).resolve()
    if _STATEMENTS_BASE.resolve() not in month_dir.parents:
        return JSONResponse(status_code=400, content={'error': 'Invalid month path'})
    if not month_dir.exists():
        return JSONResponse(status_code=404, content={'error': 'Month not found'})
    import shutil as _shutil
    _shutil.rmtree(month_dir)
    # Also remove any monthly_reports files whose transactions came solely from this statement folder.
    # Since aggregate_monthly re-reads all remaining statement folders, the safest approach is to
    # delete the matching calendar-month report files so stale data doesn't linger.
    reports_dir = _DATA_ROOT / 'monthly_reports'
    for pattern in (f'expenses_{month}.csv', f'income_{month}.csv'):
        report_file = reports_dir / pattern
        if report_file.exists():
            report_file.unlink()
    logging.info(f'Deleted statements/{month}/ (entire month) and matching monthly_reports files')
    return {'success': True}


@app.post("/api/statements/{month}/process")
def process_month(month: str, force: bool = False):
    """
    Start processing in a background thread and return a job_id immediately.
    Poll /api/jobs/{job_id} for status.
    """
    import subprocess
    if not _is_valid_month(month) and month != 'latest':
        return JSONResponse(status_code=400, content={'error': 'Month must be YYYY-MM format'})

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {'status': 'running', 'output': '', 'errors': '', 'started_at': time.time()}

    project_root    = Path(__file__).parent.parent.parent.parent
    process_script  = project_root / 'scripts' / 'process_monthly.py'
    aggregate_script = project_root / 'scripts' / 'aggregate_monthly.py'

    def _run():
        try:
            cmd = ['python3', str(process_script), '--month', month]
            if force:
                cmd.append('--force')
            r1 = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=3600, cwd=str(project_root)
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
                    _jobs[job_id]['error_msg'] = 'process_monthly.py failed (exit {})'.format(r1.returncode)
                return
            r2 = subprocess.run(
                ['python3', str(aggregate_script)],
                capture_output=True, text=True, timeout=600, cwd=str(project_root)
            )
            with _jobs_lock:
                _jobs[job_id]['output'] += r2.stdout or ''
                _jobs[job_id]['errors'] += r2.stderr or ''
                _jobs[job_id]['status'] = 'done'
            logging.info(f'✅ Processed & aggregated month {month} via dashboard (job {job_id})')
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


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Poll the status of a background processing job."""
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return JSONResponse(status_code=404, content={'error': 'Job not found'})
    return {
        'status':    job['status'],       # 'running' | 'done' | 'error'
        'output':    job.get('output', '')[-5000:],
        'errors':    job.get('errors', ''),
        'error_msg': job.get('error_msg', ''),
    }


@app.post("/api/aggregate")
def run_aggregate():
    import subprocess
    script = Path(__file__).parent.parent.parent.parent / 'scripts' / 'aggregate_monthly.py'
    try:
        result = subprocess.run(
            ['python3', str(script)],
            capture_output=True, text=True, timeout=120,
            cwd=str(Path(__file__).parent.parent.parent.parent),
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


@app.get("/api/category-hierarchy")
def get_category_hierarchy():
    """
    Return the parent→subcategory hierarchy from categories.json.
    Used by the dashboard to roll up subcategories under parent groups.
    Returns: { "Transportation": ["Gas/Fuel", "Auto Maintenance"], ... }
    """
    import json
    config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'categories.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('hierarchy', {})
    except Exception as e:
        logging.exception("Failed to load category hierarchy")
        return {}


@app.get("/api/categories")
def get_flat_categories():
    """
    Return the flat list of category names from categories.json.
    Used by the manual transactions form dropdown.
    """
    config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'categories.json'
    try:
        with open(config_path, 'r') as f:
            config = _json.load(f)
        return [{'category': c} for c in config.get('categories', [])]
    except Exception:
        return []


@app.get("/api/expense-categories")
def get_expense_categories(month: str = None):
    # Read from monthly_reports (aggregated by actual transaction month)
    # If month is provided, use that; otherwise find the most recent month with data
    base_path = _DATA_ROOT / "monthly_reports"
    
    if not base_path.exists():
        logging.warning(f"Monthly reports directory not found: {base_path}")
        return []
    
    if month:
        # Use the specified month
        expenses_path = base_path / f"expenses_{month}.csv"
        if not expenses_path.exists():
            logging.warning(f"No expense file found for {month}")
            return []
    else:
        # Get all expense files and sort them
        expense_files = sorted([f for f in base_path.glob("expenses_*.csv")], reverse=True)
        
        if not expense_files:
            logging.warning("No expense files found")
            return []
        
        # Use the most recent month
        expenses_path = expense_files[0]
    
    category_totals = defaultdict(float)
    try:
        with open(expenses_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                category = row.get("category", "Uncategorized")
                # Skip summary rows
                if category == "" or not category or "TOTAL" in str(row.get("Place", "")).upper():
                    continue
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    amount = 0
                category_totals[category] += amount
        # Also include reimbursements from income_*.csv as negative expenses
        # (handles cases where the parser wrote the reimbursement directly to income)
        income_path = expenses_path.parent / expenses_path.name.replace("expenses_", "income_")
        if income_path.exists():
            with open(income_path, newline="") as inc_file:
                inc_reader = csv.DictReader(inc_file)
                for row in inc_reader:
                    if str(row.get("Label", "")).strip().lower() != "reimbursement":
                        continue
                    try:
                        amount = float(row.get("Amount", row.get("amount", 0)))
                    except Exception:
                        continue
                    category = str(row.get("category", "Uncategorized")).strip() or "Uncategorized"
                    category_totals[category] -= abs(amount)
        return [
            {"category": cat, "amount": round(total, 2)}
            for cat, total in category_totals.items()
            if cat  # Filter out empty categories
        ]
    except Exception as e:
        logging.exception("Failed to read expenses.csv")
        return JSONResponse(status_code=500, content={"error": str(e)})


# New endpoint for last 12 months categorized expenses (for line plot)
@app.get("/api/expenses-by-month")
def get_expenses_by_month():
    # Read from monthly_reports (aggregated by actual transaction month)
    base_path = _DATA_ROOT / "monthly_reports"

    # Load hierarchy for subcategory rollup
    hierarchy = {}
    try:
        cat_path = Path(__file__).parent.parent.parent.parent / "config" / "categories.json"
        with open(cat_path) as f:
            hierarchy = _json.load(f).get("hierarchy", {})
    except Exception:
        pass
    sub_to_parent = {sub: parent for parent, subs in hierarchy.items() for sub in subs}

    results = []
    for expenses_path in sorted(base_path.glob("expenses_*.csv")):
        month_str = expenses_path.stem.replace("expenses_", "")
        if not month_str:
            continue
        category_totals = defaultdict(float)
        with open(expenses_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                category = row.get("category", "Uncategorized")
                place = row.get("Place", "")
                # Skip summary rows
                if not category or "TOTAL" in place.upper() or "BREAKDOWN" in place.upper():
                    continue
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    amount = 0
                # Roll subcategory up to parent if applicable
                category = sub_to_parent.get(category, category)
                category_totals[category] += amount
        # Also include reimbursements from income_*.csv as negative expenses
        # (handles cases where the parser wrote the reimbursement directly to income)
        income_path = base_path / f"income_{month_str}.csv"
        if income_path.exists():
            with open(income_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if str(row.get("Label", "")).strip().lower() != "reimbursement":
                        continue
                    try:
                        amount = float(row.get("Amount", row.get("amount", 0)))
                    except Exception:
                        continue
                    category = str(row.get("category", "Uncategorized")).strip() or "Uncategorized"
                    category = sub_to_parent.get(category, category)
                    category_totals[category] -= abs(amount)
        for cat, total in category_totals.items():
            if cat:
                results.append({
                    "month": month_str,
                    "category": cat,
                    "amount": round(total, 2)
                })
    return results


# AI-powered insights and forecasting endpoints

@app.get("/api/insights/{month}")
def get_monthly_insights(month: str):
    """
    Get AI-generated insights for a specific month.
    
    Args:
        month: Month in YYYY-MM format
        
    Returns:
        Insights including summary, highlights, anomalies, and recommendations
    """
    try:
        from src.ai_analysis.insights_generator import InsightsGenerator
        from src.ai_analysis.model_loader import FinGPTModelLoader
        
        base_path = _DATA_ROOT / "monthly_reports"
        
        # Load current month data
        expenses_path = base_path / f"expenses_{month}.csv"
        if not expenses_path.exists():
            return JSONResponse(status_code=404, content={"error": f"No data found for {month}"})
        
        expenses_df = pd.read_csv(expenses_path)
        
        # Filter out summary rows
        expenses_df = expenses_df[
            ~expenses_df['Place'].astype(str).str.contains(
                'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                case=False, na=False, regex=True
            )
        ]
        
        # Load previous month for comparison
        year, month_num = map(int, month.split('-'))
        prev_month_num = month_num - 1 if month_num > 1 else 12
        prev_year = year if month_num > 1 else year - 1
        prev_month = f"{prev_year:04d}-{prev_month_num:02d}"
        
        prev_expenses_path = base_path / f"expenses_{prev_month}.csv"
        prev_expenses_df = None
        if prev_expenses_path.exists():
            prev_expenses_df = pd.read_csv(prev_expenses_path)
            prev_expenses_df = prev_expenses_df[
                ~prev_expenses_df['Place'].astype(str).str.contains(
                    'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                    case=False, na=False, regex=True
                )
            ]
        
        # Try to use AI-powered insights with financial analysis model
        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model: {e}")
        
        # Initialize generator with or without AI
        if model_loader and getattr(model_loader, 'available', False):
            generator = InsightsGenerator(model_loader=model_loader, use_ai=True)
            logging.info(f"✨ Generating AI insights using model: {generator.model_name}")
        else:
            logging.info("📊 Using rule-based insights (no financial model configured)")
            generator = InsightsGenerator(use_ai=False)
        
        insights = generator.generate_monthly_insights(month, expenses_df, prev_expenses_df)
        
        logging.info(f"📊 Generated insights for {month} (AI: {insights.get('ai_generated', False)}, Model: {insights.get('model_name', 'N/A')})")
        
        return insights
        
    except Exception as e:
        logging.exception("Failed to generate insights")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/forecast")
def get_budget_forecast(months_ahead: int = 1, savings_goal: float = None, 
                       filter_outliers: bool = True):
    """
    Get budget forecast based on historical data.
    
    Args:
        months_ahead: Number of months to forecast (default: 1)
        savings_goal: Optional monthly savings goal for recommendations
        filter_outliers: Exclude large one-time purchases from forecast (default: True)
        
    Returns:
        Forecast with category breakdowns and budget recommendations
    """
    try:
        from src.ai_analysis.forecaster import BudgetForecaster
        from src.ai_analysis.model_loader import FinGPTModelLoader
        
        base_path = _DATA_ROOT / "monthly_reports"
        
        # Load all historical expense data
        expense_files = sorted(base_path.glob("expenses_*.csv"))
        
        if not expense_files:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})
        
        # Combine all expense data
        all_expenses = []
        for file in expense_files:
            df = pd.read_csv(file)
            # Filter out summary rows
            df = df[
                ~df['Place'].astype(str).str.contains(
                    'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                    case=False, na=False, regex=True
                )
            ]
            all_expenses.append(df)
        
        historical_df = pd.concat(all_expenses, ignore_index=True)
        
        # Try to use AI-powered forecasting with financial analysis model
        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model for forecasting: {e}")
        
        # Initialize forecaster with or without AI
        if model_loader and getattr(model_loader, 'available', False):
            forecaster = BudgetForecaster(model_loader=model_loader, use_ai=True, 
                                         filter_outliers=filter_outliers, 
                                         outlier_threshold=1.5)
            logging.info(f"Using AI-powered forecasting with {model_loader.financial_model}")
        else:
            logging.info("Using statistical forecasting (no financial model configured)")
            forecaster = BudgetForecaster(use_ai=False, filter_outliers=filter_outliers, 
                                         outlier_threshold=1.5)
        
        forecast = forecaster.forecast_total(historical_df, months_ahead)
        
        # Add budget recommendations if savings goal provided
        if savings_goal is not None:
            historical_avg = historical_df['Amount'].sum() / len(expense_files)
            recommendations = forecaster.create_budget_recommendations(
                forecast, historical_avg, savings_goal
            )
            forecast['recommendations'] = recommendations
        
        return forecast
        
    except Exception as e:
        logging.exception("Failed to generate forecast")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/trends")
def get_spending_trends(months: int = 6):
    """
    Analyze spending trends over recent months.
    
    Args:
        months: Number of recent months to analyze (default: 6)
        
    Returns:
        Trend analysis by category
    """
    try:
        from src.ai_analysis.forecaster import BudgetForecaster
        
        base_path = _DATA_ROOT / "monthly_reports"
        
        # Load recent expense data
        expense_files = sorted(base_path.glob("expenses_*.csv"))[-months:]
        
        if not expense_files:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})
        
        # Combine expense data
        all_expenses = []
        for file in expense_files:
            df = pd.read_csv(file)
            # Filter out summary rows
            df = df[
                ~df['Place'].astype(str).str.contains(
                    'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                    case=False, na=False, regex=True
                )
            ]
            all_expenses.append(df)
        
        historical_df = pd.concat(all_expenses, ignore_index=True)
        
        # Analyze trends
        forecaster = BudgetForecaster(use_ai=False)
        trends = forecaster.analyze_trends(historical_df, months)
        
        return trends
        
    except Exception as e:
        logging.exception("Failed to analyze trends")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/budget-suggestions")
def get_budget_suggestions(analysis_months: int = 3):
    """
    Get AI-powered budget suggestions based on spending history.
    
    Args:
        analysis_months: Number of recent months to analyze (default: 3)
        
    Returns:
        Suggested budgets per category with AI reasoning
    """
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor
        from src.ai_analysis.model_loader import FinGPTModelLoader
        
        base_path = _DATA_ROOT / "monthly_reports"
        
        # Load recent expense data
        expense_files = sorted(base_path.glob("expenses_*.csv"))[-analysis_months:]
        
        if not expense_files:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})
        
        # Combine expense data
        all_expenses = []
        for file in expense_files:
            df = pd.read_csv(file)
            # Filter out summary rows  
            df = df[
                ~df['Place'].astype(str).str.contains(
                    'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                    case=False, na=False, regex=True
                )
            ]
            all_expenses.append(df)
        
        historical_df = pd.concat(all_expenses, ignore_index=True)

        # Exclude one-time expenses (Label == 'one-time') from projection averages.
        # They still appear in the monthly actuals — just not in budget projections.
        _amt_col = next((c for c in historical_df.columns if c.lower() == 'amount'), None)
        _lbl_col = next((c for c in historical_df.columns if c.lower() == 'label'), None)
        if _lbl_col:
            _one_time_mask = historical_df[_lbl_col].str.strip().str.lower() == 'one-time'
            _n_one_time = int(_one_time_mask.sum())
            if _n_one_time > 0:
                logging.info(f"📊 Excluding {_n_one_time} one-time expense(s) from budget projection averages")
            historical_df = historical_df[~_one_time_mask]

        # Load recent income data — use only rows labelled 'recurring'
        income_months_used = []
        income_files = sorted(base_path.glob("income_*.csv"))[-analysis_months:]
        total_income = 0.0
        _skipped_bonus_count = 0
        for ifile in income_files:
            try:
                idf = pd.read_csv(ifile)
                amt_col   = next((c for c in idf.columns if c.lower() == 'amount'), None)
                place_col = next((c for c in idf.columns if c.lower() == 'place'), None)
                lbl_col   = next((c for c in idf.columns if c.lower() == 'label'), None)
                if not amt_col:
                    continue
                month_total = 0.0
                for _, irow in idf.iterrows():
                    try:
                        amount = float(irow[amt_col])
                    except Exception:
                        continue
                    lbl = str(irow[lbl_col]).strip().lower() if lbl_col else 'recurring'
                    if lbl == 'bonus':
                        _skipped_bonus_count += 1
                        place = str(irow[place_col]).upper() if place_col else ""
                        logging.info(f"📊 Skipping bonus income ${amount:,.2f} ({place}) from avg baseline")
                        continue
                    month_total += amount
                total_income += month_total
                income_months_used.append(ifile.stem)
            except Exception as ie:
                logging.warning(f"Could not read income file {ifile}: {ie}")
        avg_monthly_income = (total_income / len(income_months_used)) if income_months_used else 0.0
        if _skipped_bonus_count:
            logging.info(f"📊 Excluded {_skipped_bonus_count} bonus income deposit(s) from avg baseline")
        logging.info(f"💵 Avg monthly recurring income: ${avg_monthly_income:,.2f} (from {len(income_months_used)} months)")

        # Initialize budget advisor
        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model for budget suggestions: {e}")
        
        if model_loader and getattr(model_loader, 'available', False):
            advisor = BudgetAdvisor(model_loader=model_loader, use_ai=True)
            logging.info(f"✨ Generating AI budget suggestions using {model_loader.financial_model}")
        else:
            logging.info("📊 Generating rule-based budget suggestions")
            advisor = BudgetAdvisor(use_ai=False)
        
        suggestions = advisor.suggest_monthly_budgets(historical_df, months=analysis_months, avg_monthly_income=avg_monthly_income)

        logging.info(f"💰 Generated budget suggestions (AI: {suggestions.get('ai_generated', False)}, income: ${avg_monthly_income:,.2f})")

        return suggestions
        
    except Exception as e:
        logging.exception("Failed to generate budget suggestions")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/budget/{month}")
def get_budget_comparison(month: str):
    """
    Compare actual spending to budget goals for a specific month.
    
    Args:
        month: Month in YYYY-MM format
        
    Returns:
        Budget vs actual comparison
    """
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor
        import json
        
        base_path = _DATA_ROOT / "monthly_reports"
        expenses_path = base_path / f"expenses_{month}.csv"
        
        if not expenses_path.exists():
            return JSONResponse(status_code=404, content={"error": f"No data for month {month}"})
        
        expenses_df = pd.read_csv(expenses_path)
        expenses_df = expenses_df[
            ~expenses_df['Place'].astype(str).str.contains(
                'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                case=False, na=False, regex=True
            )
        ]
        
        # Load saved budgets
        budget_file = Path(__file__).parent.parent.parent.parent / 'config' / 'budgets.json'
        if not budget_file.exists():
            return JSONResponse(status_code=404, content={"error": "No budget goals found. Generate suggestions first."})
        
        with open(budget_file, 'r') as f:
            budget_data = json.load(f)
            budget_goals = budget_data.get('budgets', {})
        
        if not budget_goals:
            return JSONResponse(status_code=404, content={"error": "No budget goals found."})
        
        advisor = BudgetAdvisor(use_ai=False)
        comparison = advisor.compare_to_budget(expenses_df, budget_goals)
        comparison['month'] = month
        
        return comparison
        
    except Exception as e:
        logging.exception("Failed to compare budget")
        return JSONResponse(status_code=500, content={"error": str(e)})


from fastapi import Body

@app.post("/api/budget/save")
async def save_budget_goals(budgets: dict = Body(...)):
    """
    Save user's budget goals to config file.
    
    Args:
        budgets: Dictionary with budget goals per category
        
    Returns:
        Success confirmation
    """
    try:
        import json
        
        budget_file = Path(__file__).parent.parent.parent.parent / 'config' / 'budgets.json'
        
        # Save budgets
        with open(budget_file, 'w') as f:
            json.dump({'budgets': budgets}, f, indent=2)
        
        logging.info(f"💾 Saved budget goals for {len(budgets)} categories")
        
        return {"success": True, "message": f"Saved budgets for {len(budgets)} categories"}
        
    except Exception as e:
        logging.exception("Failed to save budgets")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/chat/available")
async def check_chat_availability():
    """
    Check if AI chatbot is available by checking Ollama and config.
    
    Returns:
        Dict with available status and model name
    """
    try:
        import json

        # Load config to get financial_analysis_model
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'llm_models.json'
        if not config_path.exists():
            return {"available": False, "model_name": None}

        with open(config_path) as f:
            config = json.load(f)

        model_name = config.get('financial_analysis_model', '')
        if not model_name:
            return {"available": False, "model_name": None}

        # Check if model exists in Ollama via REST
        try:
            resp = requests.get('http://localhost:11434/api/tags', timeout=3)
            model_names = [m['name'] for m in resp.json().get('models', [])]
            is_available = any(
                model_name in name or name.startswith(model_name + ':')
                for name in model_names
            )
            logging.info(f"💬 Chat availability check: {model_name} - {'Available' if is_available else 'Not found'}")
            return {
                "available": is_available,
                "model_name": model_name if is_available else None
            }
        except Exception as e:
            logging.warning(f"Could not check Ollama models: {e}")
            return {"available": False, "model_name": None}
            
    except Exception as e:
        logging.error(f"Chat availability check failed: {e}")
        return {"available": False, "model_name": None}


@app.post("/api/chat")
async def chat_with_assistant(request: dict = Body(...)):
    """
    Interactive AI chatbot for financial analysis and expense management.
    
    Allows users to:
    - Ask questions about expenses ("show me all shopping expenses")
    - Mark expenses as one-time purchases
    - Add contextual notes to transactions
    - Get personalized financial insights
    
    Args:
        request: Dict containing:
            - month: Optional month filter (YYYY-MM), if not provided uses all months
            - message: User's message
            - conversation_history: List of previous messages (optional)
    
    Returns:
        AI response with optional expense lists and action confirmations
    """
    try:
        from src.ai_analysis.chatbot_assistant import ChatbotAssistant
        import json

        month = request.get('month')  # Optional now
        message = request.get('message')
        conversation_history = request.get('conversation_history', [])

        if not message:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing required field: message"}
            )

        # Check for financial analysis model in config
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'llm_models.json'
        model_name = None

        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                model_name = config.get('financial_analysis_model', '')

        # Verify model exists via REST
        if model_name:
            try:
                resp = requests.get('http://localhost:11434/api/tags', timeout=3)
                model_names = [m['name'] for m in resp.json().get('models', [])]
                is_available = any(
                    model_name in name or name.startswith(model_name + ':')
                    for name in model_names
                )
                if is_available:
                    logging.info(f"🤖 Chat using Ollama model: {model_name}")
                else:
                    logging.info("📊 Chat using rule-based fallback (model not found)")
                    model_name = None
            except Exception as e:
                logging.warning(f"Could not verify Ollama model: {e}")
                model_name = None
        else:
            logging.info("📊 Chat using rule-based fallback (no model configured)")
        
        # Initialize chatbot with direct Ollama model name
        chatbot = ChatbotAssistant(model_name=model_name)
        
        # Process message
        result = chatbot.process_message(month, message, conversation_history)
        
        expenses_count = len(result.get('expenses') or []) if result.get('expenses') is not None else 0
        logging.info(f"💬 Chat processed: {message[:50]}... → {expenses_count} expenses returned")
        
        # Return with no-cache headers to prevent browser caching
        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        logging.exception("Failed to process chat message")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Manual Transactions ──────────────────────────────────────────────────────

_MANUAL_TRANSACTIONS_FILE = _DATA_ROOT / "manual_transactions.json"
_MONTHLY_REPORTS_ROOT = _DATA_ROOT / "monthly_reports"


def _load_manual_transactions() -> list:
    """Load manual transactions from config file."""
    if not _MANUAL_TRANSACTIONS_FILE.exists():
        return []
    try:
        with open(_MANUAL_TRANSACTIONS_FILE) as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_manual_transactions(transactions: list) -> None:
    """Persist manual transactions list to config file."""
    _MANUAL_TRANSACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MANUAL_TRANSACTIONS_FILE, "w") as f:
        _json.dump(transactions, f, indent=2)


def _manual_tx_to_csv_row(tx: dict) -> dict:
    """Convert a manual transaction dict to the CSV row format used by monthly_reports."""
    # Date stored as YYYY-MM-DD → convert to MM/DD/YYYY for CSV consistency
    try:
        dt = datetime.strptime(tx["date"], "%Y-%m-%d")
        csv_date = dt.strftime("%-m/%-d/%Y")
    except Exception:
        csv_date = tx["date"]

    if tx["type"] == "income":
        return {
            "Transaction Date": csv_date,
            "Place": tx["place"],
            "Amount": str(tx["amount"]),
            "Statement": "Manual",
            "Label": tx.get("label", "recurring"),
        }
    elif tx["type"] == "reimbursement":
        return {
            "Transaction Date": csv_date,
            "Place": tx["place"],
            "Amount": str(-abs(tx["amount"])),  # negative to offset the category spend
            "Statement": "Manual",
            "category": tx.get("category", ""),
            "Label": tx.get("label", "one-time"),
        }
    else:
        return {
            "Transaction Date": csv_date,
            "Place": tx["place"],
            "Amount": str(tx["amount"]),
            "Statement": "Manual",
            "category": tx.get("category", ""),
            "Label": tx.get("label", "recurring"),
        }


def _append_to_monthly_csv(tx: dict) -> None:
    """Append a manual transaction row to the appropriate monthly_reports CSV."""
    month = tx["month"]  # YYYY-MM
    tx_type = tx["type"]
    # reimbursements live in expenses CSV (as negative rows)
    filename = f"{'income' if tx_type == 'income' else 'expenses'}_{month}.csv"
    csv_path = _MONTHLY_REPORTS_ROOT / filename

    row = _manual_tx_to_csv_row(tx)

    if csv_path.exists():
        import pandas as _pd
        df = _pd.read_csv(csv_path)
        new_row = _pd.DataFrame([row])
        # Align columns — fill missing with empty string
        for col in df.columns:
            if col not in new_row.columns:
                new_row[col] = ""
        df = _pd.concat([df, new_row[df.columns]], ignore_index=True)
        df.to_csv(csv_path, index=False)
    else:
        # Create new file
        import csv as _csv_mod
        _MONTHLY_REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = _csv_mod.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)


def _remove_from_monthly_csv(tx: dict) -> None:
    """Remove a manual transaction row from its monthly_reports CSV by matching Statement=='Manual' and all fields."""
    month = tx["month"]
    tx_type = tx["type"]
    # reimbursements live in the expenses CSV as negative rows
    if tx_type == "reimbursement":
        filename = f"expenses_{month}.csv"
        lookup_amount = str(-abs(tx["amount"]))
    else:
        filename = f"{'income' if tx_type == 'income' else 'expenses'}_{month}.csv"
        lookup_amount = str(tx["amount"])
    csv_path = _MONTHLY_REPORTS_ROOT / filename
    if not csv_path.exists():
        return
    try:
        dt = datetime.strptime(tx["date"], "%Y-%m-%d")
        csv_date = dt.strftime("%-m/%-d/%Y")
    except Exception:
        csv_date = tx["date"]

    import pandas as _pd
    df = _pd.read_csv(csv_path)
    mask = (
        (df["Transaction Date"].astype(str) == csv_date) &
        (df["Place"].astype(str) == tx["place"]) &
        (df["Amount"].astype(str) == lookup_amount) &
        (df["Statement"].astype(str) == "Manual")
    )
    df = df[~mask]
    df.to_csv(csv_path, index=False)


@app.get("/api/manual-transactions")
async def get_manual_transactions():
    """Return all manually added transactions."""
    return _load_manual_transactions()


@app.post("/api/manual-transactions")
async def add_manual_transaction(tx: dict = Body(...)):
    """
    Add a manual transaction.
    Expected body: { date (YYYY-MM-DD), place, amount, category (expenses/reimbursements only),
                     type ('expense'|'income'|'reimbursement'), label ('recurring'|'bonus'|'one-time') }
    Reimbursements are stored as negative expenses in the monthly CSV to offset category spend.
    """
    try:
        # Validate required fields
        required = ["date", "place", "amount", "type"]
        for field in required:
            if field not in tx:
                return JSONResponse(status_code=400, content={"error": f"Missing field: {field}"})

        # Derive month from date
        dt = datetime.strptime(tx["date"], "%Y-%m-%d")
        month = dt.strftime("%Y-%m")

        # Assign a unique ID
        record = {
            "id": str(uuid.uuid4()),
            "date": tx["date"],
            "place": tx["place"].strip(),
            "amount": float(tx["amount"]),
            "type": tx["type"],
            "category": tx.get("category", "") if tx["type"] in ("expense", "reimbursement") else "",
            "label": tx.get("label", "recurring"),
            "month": month,
        }

        # Persist to JSON
        transactions = _load_manual_transactions()
        transactions.append(record)
        _save_manual_transactions(transactions)

        # Sync to monthly CSV
        _append_to_monthly_csv(record)

        logging.info(f"✏️ Manual transaction added: {record['place']} ${record['amount']} ({record['month']})")
        return {"success": True, "transaction": record}

    except Exception as e:
        logging.exception("Failed to add manual transaction")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/manual-transactions/{tx_id}")
async def delete_manual_transaction(tx_id: str):
    """Delete a manual transaction by ID and remove from monthly CSV."""
    try:
        transactions = _load_manual_transactions()
        target = next((t for t in transactions if t["id"] == tx_id), None)
        if target is None:
            return JSONResponse(status_code=404, content={"error": "Transaction not found"})

        # Remove from JSON
        transactions = [t for t in transactions if t["id"] != tx_id]
        _save_manual_transactions(transactions)

        # Remove from CSV
        _remove_from_monthly_csv(target)

        logging.info(f"🗑️ Manual transaction deleted: {target['place']} ${target['amount']}")
        return {"success": True}

    except Exception as e:
        logging.exception("Failed to delete manual transaction")
        return JSONResponse(status_code=500, content={"error": str(e)})
