"""routes/transfers.py — Investment transfer endpoints."""

import logging
import json as _json
import uuid
from datetime import datetime

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _DB_AVAILABLE, get_engine,
    _DATA_ROOT,
)

router = APIRouter()

_MANUAL_TRANSFERS_FILE = _DATA_ROOT / 'manual_investment_transfers.json'


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/transfers")
def get_transfers():
    """Return all investment transfer rows with Retirement/Personal labels applied."""
    labels = _load_transfer_labels()
    rows = []

    if _DB_AVAILABLE:
        try:
            from sqlalchemy import text as _text
            with get_engine().connect() as conn:
                db_rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, report_month, statement, direction, label, "
                    "CASE WHEN INSTR(tx_date, '/') > 0 THEN "
                    "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER)) "
                    "ELSE '' END AS tx_month "
                    "FROM transfers ORDER BY tx_date"
                )).fetchall()
            for r in db_rows:
                date  = r[0] or ''
                place = r[1] or ''
                try:
                    amount = round(float(r[2] or 0), 2)
                except Exception:
                    amount = 0.0
                override = labels.get((date.strip(), place.strip().upper(), amount))
                # Use computed tx_date month (r[7]) so filter always matches selectedMonth
                tx_month = r[7] or r[3] or ''
                rows.append({
                    'date':      date,
                    'place':     place,
                    'amount':    amount,
                    'month':     tx_month,
                    'statement': r[4] or '',
                    'direction': r[5] or 'Out',
                    'label':     override if override is not None else r[6],
                })
        except Exception as exc:
            logging.warning(f'DB transfers query failed: {exc}')

    for r in _load_manual_transfers():
        override = labels.get((str(r['date']).strip(), str(r['place']).strip().upper(), round(float(r['amount']), 2)))
        rows.append({**r, 'label': override if override is not None else r.get('label')})

    return rows


@router.post("/api/transfers/label")
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


@router.post("/api/transfers/manual")
def add_manual_transfer(payload: dict = Body(...)):
    """Add a manual investment transfer. Body: {date, place, amount, direction, label}"""
    try:
        required = ['date', 'place', 'amount', 'direction']
        for field in required:
            if field not in payload:
                return JSONResponse(status_code=400, content={'error': f'Missing field: {field}'})

        dt = datetime.strptime(payload['date'], '%Y-%m-%d')
        month = dt.strftime('%Y-%m')
        csv_date = f"{dt.month}/{dt.day}/{dt.year}"

        record = {
            'id':        str(uuid.uuid4()),
            'date':      csv_date,
            'place':     payload['place'].strip(),
            'amount':    round(float(payload['amount']), 2),
            'direction': payload.get('direction', 'Out'),
            'label':     payload.get('label') or None,
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


@router.delete("/api/transfers/manual/{tx_id}")
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
