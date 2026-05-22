"""routes/settings.py — Auto-filter tracker endpoints for the Settings tab."""

import json
import logging
import re as _re
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import _DB_AVAILABLE, get_engine

router = APIRouter()
logger = logging.getLogger(__name__)


def _derive_clean_place(place_raw: str) -> str:
    """Strip variable noise from a transfer-keyword-filtered description.

    Removes common transfer prefixes, masked account numbers, inline dates,
    and inline times so the remaining text is a meaningful merchant/payee name.
    """
    s = str(place_raw)
    # Remove common transfer-instruction prefixes
    s = _re.sub(
        r'^(ONLINE[\s\-]PHONE TRANSFER TO|ONLINE TRANSFER TO|ACH TRANSFER TO|WIRE TRANSFER TO'
        r'|ONLINE PAYMENT TO|ELECTRONIC TRANSFER TO)\s*',
        '', s, flags=_re.IGNORECASE,
    )
    # Remove masked account tokens: XXXXXX5218, Xxxxxx1234
    s = _re.sub(r'[Xx]{3,}\d*', '', s)
    # Remove inline dates: 1/01/25, 12/01/2025
    s = _re.sub(r'\b\d{1,2}/\d{2}(?:/\d{2,4})?\b', '', s)
    # Remove "AT HH:MM" / "AT H:MM"
    s = _re.sub(r'\bAT\s+\d{1,2}:\d{2}\b', '', s, flags=_re.IGNORECASE)
    # Collapse spaces
    s = _re.sub(r'\s+', ' ', s).strip()
    # If stripping left a meaningful name, return it title-cased; else keep original
    return s.title() if len(s) > 2 else place_raw.title()


def _whitelist_categorize(clean_name: str, amount: float) -> str:
    """Best-effort category for a newly restored whitelisted transaction.

    Uses keyword matching + optional LLM via the standard TransactionCategorizer.
    Returns 'Uncategorized' on any error so the insertion never fails.
    """
    try:
        from src.ai_classification.categorizer import TransactionCategorizer
        cat = TransactionCategorizer(use_llm=True).categorize_transaction(clean_name, amount)
        return cat or 'Uncategorized'
    except Exception:
        return 'Uncategorized'


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
def set_whitelist(record_id: int, body: dict = Body(None)):
    """Toggle the whitelisted flag for a given record.
    Body should contain ``{"whitelisted": true|false}``.
    Defaults to True if body is omitted.

    When whitelisting: immediately restores the transaction's tx_type from 'transfer'
    back to 'expense'/'income' so it appears in the all-transactions list right away
    without requiring a reprocess.

    When un-whitelisting: re-runs the transfer-detection pass for affected months
    so the transaction is correctly re-marked as 'transfer'.
    """
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'DB unavailable'})
    whitelisted = True
    if body and 'whitelisted' in body:
        whitelisted = bool(body['whitelisted'])
    try:
        from sqlalchemy import text as _text
        from src.database.db_utils import (
            set_auto_deleted_whitelist, _normalize_merchant_key,
            _normalize_whitelist_key, _make_hash,
            _auto_mark_bank_transfers,
        )
        engine = get_engine()
        ok = set_auto_deleted_whitelist(engine, record_id, whitelisted)
        if not ok:
            return JSONResponse(status_code=500, content={'error': 'Update failed'})

        # Sync the transactions table immediately so the UI reflects the change
        # without waiting for a full reprocess.
        with engine.connect() as conn:
            rec = conn.execute(_text(
                "SELECT place_normalized, seen_months, tx_type, "
                "place_display, amount, tx_date, original_statement "
                "FROM auto_deleted_transactions WHERE id=:id"
            ), {'id': record_id}).fetchone()

        transactions_updated = 0
        if rec:
            place_norm     = rec[0]
            seen_months_raw= rec[1]
            stored_tx_type = rec[2]
            place_display  = rec[3]
            amount_raw     = float(rec[4] or 0)
            tx_date_raw    = str(rec[5] or '')
            original_stmt  = str(rec[6] or '')

            seen_months = json.loads(seen_months_raw or '[]') if seen_months_raw else []
            place_wl_norm = _normalize_whitelist_key(place_norm)

            if whitelisted:
                # ── Step 1: flip any existing 'transfer' rows back to expense/income ──
                with engine.connect() as conn:
                    transfer_rows = conn.execute(_text(
                        "SELECT tx_hash, place, amount FROM transactions "
                        "WHERE tx_type='transfer' AND user_corrected=0"
                    )).fetchall()
                    for tx_hash, place, amount in transfer_rows:
                        norm = _normalize_merchant_key(place or '')
                        if norm == place_norm or _normalize_whitelist_key(norm) == place_wl_norm:
                            restore_type = stored_tx_type or (
                                'expense' if float(amount or 0) >= 0 else 'income'
                            )
                            conn.execute(_text(
                                "UPDATE transactions SET tx_type=:t WHERE tx_hash=:h"
                            ), {'t': restore_type, 'h': tx_hash})
                            transactions_updated += 1
                    conn.commit()

                # ── Step 2: insert rows for months where the transaction was filtered
                #    out entirely during parsing (never reached the transactions table) ──
                clean_name   = _derive_clean_place(place_display)
                restore_type = stored_tx_type or 'expense'
                category     = _whitelist_categorize(clean_name, amount_raw)

                with engine.connect() as conn:
                    for month in seen_months:
                        # Check whether a matching non-transfer row already exists
                        month_rows = conn.execute(_text(
                            "SELECT place FROM transactions "
                            "WHERE report_month=:m AND tx_type != 'transfer'"
                        ), {'m': month}).fetchall()

                        already_there = any(
                            _normalize_whitelist_key(r[0] or '') == place_wl_norm
                            or _normalize_merchant_key(r[0] or '') == place_norm
                            for r in month_rows
                        )
                        if already_there:
                            continue

                        # Insert the missing transaction with LLM-cleaned name + category
                        tx_hash = _make_hash(
                            month, tx_date_raw, clean_name,
                            amount_raw, restore_type, original_stmt,
                        )
                        conn.execute(_text("""
                            INSERT OR IGNORE INTO transactions
                            (tx_hash, report_month, tx_type, tx_date, place, amount,
                             category, label, statement, user_corrected)
                            VALUES (:h, :m, :t, :d, :p, :a, :cat, 'recurring', :stmt, 0)
                        """), {
                            'h': tx_hash, 'm': month, 't': restore_type,
                            'd': tx_date_raw, 'p': clean_name, 'a': amount_raw,
                            'cat': category, 'stmt': original_stmt,
                        })
                        transactions_updated += 1
                    conn.commit()
            else:
                # Un-whitelist: re-run transfer detection for each affected month so
                # the rows are correctly re-marked as 'transfer'.
                for month in (seen_months or []):
                    transactions_updated += _auto_mark_bank_transfers(engine, month)

        return {'id': record_id, 'whitelisted': whitelisted, 'transactions_updated': transactions_updated}
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

