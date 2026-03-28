"""main.py — FastAPI application bootstrap.

All routes live in dedicated modules:
  src/ui/backend/routes/income.py      — income endpoints
  src/ui/backend/routes/expenses.py    — expense browse / edit / manual transactions
  src/ui/backend/routes/transfers.py   — investment transfer endpoints
  src/ui/backend/routes/statements.py  — statement management / processing jobs
  src/ui/backend/routes/keywords.py    — keyword CRUD (5 types)
  src/ui/backend/routes/analytics.py   — AI insights / forecast / budget / chat
  src/ui/backend/export_excel.py       — Excel export

Shared state (DB, paths, helpers) lives in src/ui/backend/deps.py.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Add project root to sys.path so all src.* imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# ── Routers ───────────────────────────────────────────────────────────────────
from src.ui.backend.export_excel import router as _export_router          # noqa: E402
from src.ui.backend.routes.income import router as _income_router         # noqa: E402
from src.ui.backend.routes.expenses import router as _expenses_router     # noqa: E402
from src.ui.backend.routes.transfers import router as _transfers_router   # noqa: E402
from src.ui.backend.routes.statements import router as _statements_router # noqa: E402
from src.ui.backend.routes.keywords import router as _keywords_router     # noqa: E402
from src.ui.backend.routes.analytics import router as _analytics_router   # noqa: E402

# ── Shared state ──────────────────────────────────────────────────────────────
from src.ui.backend import deps                                            # noqa: E402

_WRITE_API_KEY = os.environ.get('AUTOBUDGET_API_KEY', '').strip()


# ── DB / startup ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialise the SQLite DB on startup and seed keyword tables if needed."""
    if deps._DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            from src.database.session import init_db
            from src.database.db_utils import (
                seed_investment_keywords, seed_income_keywords,
                seed_ignore_keywords, seed_payment_app_keywords,
                seed_transfer_keywords,
            )
            _engine = init_db()

            def _seed_if_empty(table: str, seed_fn) -> None:
                with _engine.connect() as _c:
                    cnt = _c.execute(_text(f'SELECT COUNT(*) FROM {table}')).scalar()
                if not cnt:
                    n = seed_fn(_engine)
                    logging.info(f"✅ Seeded {n} rows into {table}")

            _seed_if_empty('investment_keywords',  seed_investment_keywords)
            _seed_if_empty('income_keywords',      seed_income_keywords)
            _seed_if_empty('ignore_keywords',      seed_ignore_keywords)
            _seed_if_empty('payment_app_keywords', seed_payment_app_keywords)
            _seed_if_empty('transfer_keywords',    seed_transfer_keywords)

            deps._reload_investment_keywords()
            deps._reload_income_keywords()
            deps._reload_ignore_keywords()
            deps._reload_payment_app_keywords()
            deps._reload_transfer_keywords()
        except Exception as exc:
            logging.warning(f"⚠️  DB startup check failed (non-fatal): {exc}")
    yield


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Automated Budgeting API",
    description="API for processing bank statements and generating financial reports",
    version="1.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Write-auth middleware ─────────────────────────────────────────────────────
@app.middleware("http")
async def _write_auth_middleware(request: Request, call_next):
    if (_WRITE_API_KEY
            and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
            and request.url.path.startswith('/api/')):
        provided = request.headers.get('x-api-key', '').strip()
        if provided != _WRITE_API_KEY:
            return JSONResponse(status_code=401, content={'error': 'Unauthorized'})
    return await call_next(request)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(_export_router)
app.include_router(_income_router)
app.include_router(_expenses_router)
app.include_router(_transfers_router)
app.include_router(_statements_router)
app.include_router(_keywords_router)
app.include_router(_analytics_router)

# ── Static files & dashboard ──────────────────────────────────────────────────
_react_build = Path(__file__).parent.parent / "build"
if _react_build.exists():
    app.mount("/static", StaticFiles(directory=str(_react_build / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the React dashboard (falls back to a status page if not built)."""
    index_path = Path(__file__).parent.parent / "build" / "index.html"
    if index_path.exists():
        with open(index_path, 'r') as f:
            return f.read()
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
            h1 { color: #2c3e50; margin: 0 0 10px 0; font-size: 2.5em; }
            .subtitle { color: #7f8c8d; margin: 0 0 40px 0; font-size: 1.1em; }
            .status {
                display: inline-block;
                background: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 20px;
                font-weight: bold;
                margin-bottom: 40px;
            }
            .links { display: flex; gap: 15px; justify-content: center; margin: 30px 0; }
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
            .btn:hover { background: #2980b9; transform: translateY(-2px); }
            .btn.secondary { background: #95a5a6; }
            .btn.secondary:hover { background: #7f8c8d; }
            .info {
                margin-top: 40px;
                padding: 20px;
                background: #ecf0f1;
                border-radius: 8px;
                font-size: 0.95em;
            }
            .info h3 { margin-top: 0; color: #34495e; }
            ul { text-align: left; color: #555; }
            .footer { margin-top: 30px; color: #95a5a6; font-size: 0.85em; }
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
            <div class="footer">Running in Docker • Powered by Ollama LLM</div>
        </div>
    </body>
    </html>
    """
