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


def _list_keywords_with_source(table: str):
    """Query a keyword table and return [{keyword, source}] sorted by keyword."""
    if not _DB_AVAILABLE:
        return []
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text(
                f"SELECT keyword, COALESCE(source, 'default') FROM {table} ORDER BY keyword"
            )).fetchall()
        return [{'keyword': r[0], 'source': r[1]} for r in rows]
    except Exception as exc:
        logging.warning(f'_list_keywords_with_source({table}): {exc}')
        return []


def _add_keyword(table: str, keyword: str, reload_fn) -> dict:
    kw = keyword.strip().lower()
    if not kw:
        return {'error': 'keyword is required'}
    if not _DB_AVAILABLE:
        return {'error': 'DB unavailable'}
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text(
                f"INSERT OR IGNORE INTO {table} (keyword, source) VALUES (:kw, 'user')"
            ), {'kw': kw})
            conn.commit()
        reload_fn()
        return {'ok': True, 'keyword': kw}
    except Exception as exc:
        return {'error': str(exc)}


def _delete_keyword(table: str, keyword: str, reload_fn):
    kw = keyword.strip().lower()
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            row = conn.execute(_text(
                f"SELECT source FROM {table} WHERE keyword = :kw"
            ), {'kw': kw}).fetchone()
            if row and row[0] == 'default':
                return JSONResponse(status_code=403, content={
                    'error': 'Default keywords cannot be deleted. They ensure core functionality.'
                })
            conn.execute(_text(f'DELETE FROM {table} WHERE keyword = :kw'), {'kw': kw})
            conn.commit()
        reload_fn()
        return {'deleted': kw}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


# ── All-keywords (Settings UI) ────────────────────────────────────────────────

@router.get("/api/all-keywords")
def get_all_keywords():
    """Return all 5 keyword lists with source tags for the Settings UI."""
    return {
        'investment':   _list_keywords_with_source('investment_keywords'),
        'income':       _list_keywords_with_source('income_keywords'),
        'ignore':       _list_keywords_with_source('ignore_keywords'),
        'payment_app':  _list_keywords_with_source('payment_app_keywords'),
        'transfer':     _list_keywords_with_source('transfer_keywords'),
    }


# ── Investment-platform keywords ──────────────────────────────────────────────

@router.get("/api/investment-keywords")
def list_investment_keywords():
    return {'keywords': sorted(_INVESTMENT_PLATFORM_KEYWORDS)}


@router.post("/api/investment-keywords")
def add_investment_keyword(body: dict = Body(...)):
    result = _add_keyword('investment_keywords', str(body.get('keyword', '')), _reload_investment_keywords)
    if 'error' in result:
        status = 503 if result['error'] == 'DB unavailable' else 400 if result['error'] == 'keyword is required' else 500
        return JSONResponse(status_code=status, content=result)
    return {'keyword': result['keyword'], 'keywords': sorted(_INVESTMENT_PLATFORM_KEYWORDS)}


@router.delete("/api/investment-keywords/{keyword}")
def delete_investment_keyword(keyword: str):
    return _delete_keyword('investment_keywords', keyword, _reload_investment_keywords)


# ── Income keywords ───────────────────────────────────────────────────────────

@router.get("/api/income-keywords")
def list_income_keywords():
    return {'keywords': sorted(_INCOME_KEYWORDS)}


@router.post("/api/income-keywords")
def add_income_keyword(body: dict = Body(...)):
    result = _add_keyword('income_keywords', str(body.get('keyword', '')), _reload_income_keywords)
    if 'error' in result:
        status = 503 if result['error'] == 'DB unavailable' else 400 if result['error'] == 'keyword is required' else 500
        return JSONResponse(status_code=status, content=result)
    return {'keyword': result['keyword'], 'keywords': sorted(_INCOME_KEYWORDS)}


@router.delete("/api/income-keywords/{keyword}")
def delete_income_keyword(keyword: str):
    return _delete_keyword('income_keywords', keyword, _reload_income_keywords)


# ── Ignore keywords ───────────────────────────────────────────────────────────

@router.get("/api/ignore-keywords")
def list_ignore_keywords():
    return {'keywords': sorted(_IGNORE_KEYWORDS)}


@router.post("/api/ignore-keywords")
def add_ignore_keyword(body: dict = Body(...)):
    result = _add_keyword('ignore_keywords', str(body.get('keyword', '')), _reload_ignore_keywords)
    if 'error' in result:
        status = 503 if result['error'] == 'DB unavailable' else 400 if result['error'] == 'keyword is required' else 500
        return JSONResponse(status_code=status, content=result)
    return {'keyword': result['keyword'], 'keywords': sorted(_IGNORE_KEYWORDS)}


@router.delete("/api/ignore-keywords/{keyword}")
def delete_ignore_keyword(keyword: str):
    return _delete_keyword('ignore_keywords', keyword, _reload_ignore_keywords)


# ── Payment-app keywords ──────────────────────────────────────────────────────

@router.get("/api/payment-app-keywords")
def list_payment_app_keywords():
    return {'keywords': sorted(_PAYMENT_APP_KEYWORDS)}


@router.post("/api/payment-app-keywords")
def add_payment_app_keyword(body: dict = Body(...)):
    result = _add_keyword('payment_app_keywords', str(body.get('keyword', '')), _reload_payment_app_keywords)
    if 'error' in result:
        status = 503 if result['error'] == 'DB unavailable' else 400 if result['error'] == 'keyword is required' else 500
        return JSONResponse(status_code=status, content=result)
    return {'keyword': result['keyword'], 'keywords': sorted(_PAYMENT_APP_KEYWORDS)}


@router.delete("/api/payment-app-keywords/{keyword}")
def delete_payment_app_keyword(keyword: str):
    return _delete_keyword('payment_app_keywords', keyword, _reload_payment_app_keywords)


# ── Transfer keywords ─────────────────────────────────────────────────────────

@router.get("/api/transfer-keywords")
def list_transfer_keywords():
    return {'keywords': sorted(_TRANSFER_KEYWORDS)}


@router.post("/api/transfer-keywords")
def add_transfer_keyword(body: dict = Body(...)):
    result = _add_keyword('transfer_keywords', str(body.get('keyword', '')), _reload_transfer_keywords)
    if 'error' in result:
        status = 503 if result['error'] == 'DB unavailable' else 400 if result['error'] == 'keyword is required' else 500
        return JSONResponse(status_code=status, content=result)
    return {'keyword': result['keyword'], 'keywords': sorted(_TRANSFER_KEYWORDS)}


@router.delete("/api/transfer-keywords/{keyword}")
def delete_transfer_keyword(keyword: str):
    return _delete_keyword('transfer_keywords', keyword, _reload_transfer_keywords)




@router.get("/api/merchant-rules")
def list_merchant_rules():
    """Return all user-defined merchant rules."""
    if not _DB_AVAILABLE:
        return {'rules': []}
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            rows = conn.execute(_text(
                "SELECT id, merchant_key, display_name, action, category "
                "FROM merchant_rules ORDER BY display_name"
            )).fetchall()
        return {'rules': [
            {'id': r[0], 'merchant_key': r[1], 'display_name': r[2],
             'action': r[3], 'category': r[4]}
            for r in rows
        ]}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.post("/api/merchant-rules")
def upsert_merchant_rule(body: dict = Body(...)):
    """Create or update a merchant rule (upsert by merchant_key)."""
    merchant_key = str(body.get('merchant_key', '')).strip().lower()
    display_name = str(body.get('display_name', merchant_key)).strip()
    action       = str(body.get('action', '')).strip().lower()
    category     = str(body.get('category', '') or '').strip() or None
    if not merchant_key:
        return JSONResponse(status_code=400, content={'error': 'merchant_key is required'})
    if action not in ('income', 'expense', 'ignore'):
        return JSONResponse(status_code=400, content={'error': "action must be 'income', 'expense', or 'ignore'"})
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text(
                """
                INSERT INTO merchant_rules (merchant_key, display_name, action, category)
                VALUES (:mk, :dn, :act, :cat)
                ON CONFLICT(merchant_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    action       = excluded.action,
                    category     = excluded.category
                """
            ), {'mk': merchant_key, 'dn': display_name, 'act': action, 'cat': category})
            conn.commit()
        return {'merchant_key': merchant_key, 'display_name': display_name,
                'action': action, 'category': category}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.patch("/api/merchant-rules/{rule_id}")
def update_merchant_rule(rule_id: int, body: dict = Body(...)):
    """Update action and/or category for a merchant rule."""
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    action = body.get('action')
    category = body.get('category')
    if action and action not in ('income', 'expense', 'ignore'):
        return JSONResponse(status_code=400, content={'error': 'action must be income, expense, or ignore'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            if action and category is not None:
                conn.execute(_text(
                    'UPDATE merchant_rules SET action=:a, category=:c WHERE id=:id'
                ), {'a': action, 'c': category or None, 'id': rule_id})
            elif action:
                conn.execute(_text(
                    'UPDATE merchant_rules SET action=:a WHERE id=:id'
                ), {'a': action, 'id': rule_id})
            elif category is not None:
                conn.execute(_text(
                    'UPDATE merchant_rules SET category=:c WHERE id=:id'
                ), {'c': category or None, 'id': rule_id})
            else:
                return JSONResponse(status_code=400, content={'error': 'Nothing to update'})
            conn.commit()
        return {'id': rule_id, 'action': action, 'category': category}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/merchant-rules/{rule_id}")
def delete_merchant_rule(rule_id: int):
    """Delete a merchant rule by id."""
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        with get_engine().connect() as conn:
            conn.execute(_text('DELETE FROM merchant_rules WHERE id = :id'), {'id': rule_id})
            conn.commit()
        return {'deleted': rule_id}
    except Exception as exc:
        return JSONResponse(status_code=500, content={'error': str(exc)})
