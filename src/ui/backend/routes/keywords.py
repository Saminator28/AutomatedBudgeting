"""routes/keywords.py — CRUD endpoints for all five keyword types."""

import logging
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _DB_AVAILABLE, get_engine,
    _INVESTMENT_PLATFORM_KEYWORDS,
    _INCOME_KEYWORDS,
    _IGNORE_KEYWORDS,
    _PAYMENT_APP_KEYWORDS,
    _TRANSFER_KEYWORDS,
    _reload_investment_keywords,
    _reload_income_keywords,
    _reload_ignore_keywords,
    _reload_payment_app_keywords,
    _reload_transfer_keywords,
)

router = APIRouter()


# ── Investment-platform keywords ──────────────────────────────────────────────

@router.get("/api/investment-keywords")
def list_investment_keywords():
    return {'keywords': sorted(_INVESTMENT_PLATFORM_KEYWORDS)}


@router.post("/api/investment-keywords")
def add_investment_keyword(body: dict = Body(...)):
    kw = str(body.get('keyword', '')).strip().lower()
    if not kw:
        return JSONResponse(status_code=400, content={'error': 'keyword is required'})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('INSERT OR IGNORE INTO investment_keywords (keyword) VALUES (:kw)'), {'kw': kw})
            conn.commit()
        _reload_investment_keywords()
        return {'keyword': kw, 'keywords': sorted(_INVESTMENT_PLATFORM_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/investment-keywords/{keyword}")
def delete_investment_keyword(keyword: str):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM investment_keywords WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        _reload_investment_keywords()
        return {'deleted': kw, 'keywords': sorted(_INVESTMENT_PLATFORM_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── Income keywords ───────────────────────────────────────────────────────────

@router.get("/api/income-keywords")
def list_income_keywords():
    return {'keywords': sorted(_INCOME_KEYWORDS)}


@router.post("/api/income-keywords")
def add_income_keyword(body: dict = Body(...)):
    kw = str(body.get('keyword', '')).strip().lower()
    if not kw:
        return JSONResponse(status_code=400, content={'error': 'keyword is required'})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('INSERT OR IGNORE INTO income_keywords (keyword) VALUES (:kw)'), {'kw': kw})
            conn.commit()
        _reload_income_keywords()
        return {'keyword': kw, 'keywords': sorted(_INCOME_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/income-keywords/{keyword}")
def delete_income_keyword(keyword: str):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM income_keywords WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        _reload_income_keywords()
        return {'deleted': kw, 'keywords': sorted(_INCOME_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── Ignore keywords ───────────────────────────────────────────────────────────

@router.get("/api/ignore-keywords")
def list_ignore_keywords():
    return {'keywords': sorted(_IGNORE_KEYWORDS)}


@router.post("/api/ignore-keywords")
def add_ignore_keyword(body: dict = Body(...)):
    kw = str(body.get('keyword', '')).strip().lower()
    if not kw:
        return JSONResponse(status_code=400, content={'error': 'keyword is required'})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('INSERT OR IGNORE INTO ignore_keywords (keyword) VALUES (:kw)'), {'kw': kw})
            conn.commit()
        _reload_ignore_keywords()
        return {'keyword': kw, 'keywords': sorted(_IGNORE_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/ignore-keywords/{keyword}")
def delete_ignore_keyword(keyword: str):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM ignore_keywords WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        _reload_ignore_keywords()
        return {'deleted': kw, 'keywords': sorted(_IGNORE_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── Payment-app keywords ──────────────────────────────────────────────────────

@router.get("/api/payment-app-keywords")
def list_payment_app_keywords():
    return {'keywords': sorted(_PAYMENT_APP_KEYWORDS)}


@router.post("/api/payment-app-keywords")
def add_payment_app_keyword(body: dict = Body(...)):
    kw = str(body.get('keyword', '')).strip().lower()
    if not kw:
        return JSONResponse(status_code=400, content={'error': 'keyword is required'})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('INSERT OR IGNORE INTO payment_app_keywords (keyword) VALUES (:kw)'), {'kw': kw})
            conn.commit()
        _reload_payment_app_keywords()
        return {'keyword': kw, 'keywords': sorted(_PAYMENT_APP_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/payment-app-keywords/{keyword}")
def delete_payment_app_keyword(keyword: str):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM payment_app_keywords WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        _reload_payment_app_keywords()
        return {'deleted': kw, 'keywords': sorted(_PAYMENT_APP_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── Transfer keywords ─────────────────────────────────────────────────────────

@router.get("/api/transfer-keywords")
def list_transfer_keywords():
    return {'keywords': sorted(_TRANSFER_KEYWORDS)}


@router.post("/api/transfer-keywords")
def add_transfer_keyword(body: dict = Body(...)):
    kw = str(body.get('keyword', '')).strip().lower()
    if not kw:
        return JSONResponse(status_code=400, content={'error': 'keyword is required'})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('INSERT OR IGNORE INTO transfer_keywords (keyword) VALUES (:kw)'), {'kw': kw})
            conn.commit()
        _reload_transfer_keywords()
        return {'keyword': kw, 'keywords': sorted(_TRANSFER_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/transfer-keywords/{keyword}")
def delete_transfer_keyword(keyword: str):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM transfer_keywords WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        _reload_transfer_keywords()
        return {'deleted': kw, 'keywords': sorted(_TRANSFER_KEYWORDS)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})
