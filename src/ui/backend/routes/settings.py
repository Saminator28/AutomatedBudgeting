"""routes/settings.py — Auto-filter tracker endpoints for the Settings tab."""

import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.ui.backend.deps import _DB_AVAILABLE, get_engine

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/auto-filters")
def list_auto_filters():
    """Return all auto_deleted_transactions rows ordered by last_seen desc."""
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from src.database.db_utils import get_auto_deleted_transactions
        records = get_auto_deleted_transactions(get_engine())
        return {'auto_filters': records}
    except Exception as exc:
        logger.error(f'list_auto_filters: {exc}')
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.patch("/api/auto-filters/{record_id}/whitelist")
def set_whitelist(record_id: int, body: dict = None):
    """Toggle the whitelisted flag for a given record.
    Body should contain ``{"whitelisted": true|false}``.
    Defaults to True if body is omitted.
    """
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    whitelisted = True
    if body and 'whitelisted' in body:
        whitelisted = bool(body['whitelisted'])
    try:
        from src.database.db_utils import set_auto_deleted_whitelist
        ok = set_auto_deleted_whitelist(get_engine(), record_id, whitelisted)
        if not ok:
            return JSONResponse(status_code=500, content={'error': 'Update failed'})
        return {'id': record_id, 'whitelisted': whitelisted}
    except Exception as exc:
        logger.error(f'set_whitelist: {exc}')
        return JSONResponse(status_code=500, content={'error': str(exc)})


@router.delete("/api/auto-filters/{record_id}")
def delete_auto_filter(record_id: int):
    """Remove an auto_deleted_transactions record entirely."""
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    try:
        from sqlalchemy import text as _text
        from src.database.db_utils import delete_auto_deleted_record, _make_hash
        engine = get_engine()

        # Fetch the record before deleting so we can optionally restore it
        with engine.connect() as conn:
            row = conn.execute(_text(
                "SELECT reason, place_display, place_normalized, amount, tx_date, "
                "report_month, tx_type, category, original_statement "
                "FROM auto_deleted_transactions WHERE id=:id"
            ), {'id': record_id}).fetchone()

        if row is None:
            return JSONResponse(status_code=404, content={'error': 'Record not found'})

        (reason, place_display, place_normalized, amount, tx_date,
         report_month, tx_type, category, original_statement) = row

        # For manual_delete records with enough stored data, restore the transaction
        restored = False
        if reason == 'manual_delete' and tx_type:
            place = place_display or place_normalized or ''
            statement = original_statement or 'Restored'
            tx_hash = _make_hash(
                str(report_month or ''),
                str(tx_date or ''),
                place,
                float(amount or 0),
                str(tx_type or 'expense'),
                statement,
            )
            try:
                with engine.connect() as conn:
                    conn.execute(_text(
                        "INSERT OR IGNORE INTO transactions "
                        "(tx_hash, report_month, tx_date, place, amount, "
                        " category, label, tx_type, statement, user_corrected) "
                        "VALUES (:h, :rm, :dt, :pl, :amt, :cat, '', :ttype, :stmt, 0)"
                    ), {
                        'h': tx_hash, 'rm': report_month, 'dt': tx_date or '',
                        'pl': place, 'amt': float(amount or 0),
                        'cat': category or 'Uncategorized', 'ttype': tx_type,
                        'stmt': statement,
                    })
                    conn.commit()
                restored = True
            except Exception as restore_exc:
                logger.error(f'delete_auto_filter restore: {restore_exc}')

        ok = delete_auto_deleted_record(engine, record_id)
        if not ok:
            return JSONResponse(status_code=500, content={'error': 'Delete failed'})
        return {'deleted': record_id, 'restored': restored}
    except Exception as exc:
        logger.error(f'delete_auto_filter: {exc}')
        return JSONResponse(status_code=500, content={'error': str(exc)})


# Merchant-rules CRUD is handled in keywords.py (registered earlier in main.py).

