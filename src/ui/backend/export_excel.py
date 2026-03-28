"""
export_excel.py — Excel export router for the Automated Budgeting API.

Provides GET /api/transactions/export?month=YYYY-MM
Generates a three-sheet .xlsx workbook:
  1. Transaction Ledger   — date-sorted ledger with type, description, category,
                            amount, frequency, and a blank Notes column.
  2. Category Breakdown   — total / count / avg per category, % of expenses,
                            % of income; sorted by spend descending.
  3. Budget Overview      — income vs. expenses summary + 50/30/20 rule analysis
                            showing target vs. actual for Needs/Wants/Savings.
"""

import io
import json as _json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

# ── Shared state from deps ───────────────────────────────────────────────────
from src.ui.backend.deps import (  # noqa: E402
    _DB_AVAILABLE, get_engine,
)


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter()


@router.get("/api/transactions/export")
def export_transactions(month: str = ''):
    """
    Export transactions for the given month (or all months) as a formatted Excel workbook.

    Sheet layout (based on personal-finance spreadsheet best practices):
      1. Transaction Ledger  — date-sorted ledger with type, description, category,
                               amount, frequency, and a blank Notes column.
      2. Category Breakdown  — total / count / avg per category, % of expenses,
                               % of income; sorted by spend descending.
      3. Budget Overview     — income vs. expenses summary + 50/30/20 rule analysis
                               showing target vs. actual for Needs/Wants/Savings.
    """
    if not _DB_AVAILABLE:
        return JSONResponse(status_code=503, content={'error': 'Database unavailable'})

    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from sqlalchemy import text as _text

        _eng = get_engine()
        params: dict = {}
        month_filter = " AND report_month = :month" if month else ""
        if month:
            params['month'] = month

        with _eng.connect() as conn:
            tx_rows = conn.execute(_text(
                "SELECT tx_hash, tx_date, place, amount, category, label, tx_type, report_month "
                "FROM transactions WHERE 1=1" + month_filter +
                " ORDER BY report_month ASC, tx_date ASC, place ASC"
            ), params).fetchall()

        label_month = month if month else 'All Months'

        # ── Shared style helpers ──────────────────────────────────────────────
        HDR_FILL     = PatternFill('solid', fgColor='1E3A5F')   # deep navy
        HDR_FONT     = Font(bold=True, color='FFFFFF', size=11)
        SUB_FILL     = PatternFill('solid', fgColor='2D6A9F')   # medium blue sub-header
        SUB_FONT     = Font(bold=True, color='FFFFFF', size=10)
        EXPENSE_FILL = PatternFill('solid', fgColor='FEF2F2')   # pale red
        INCOME_FILL  = PatternFill('solid', fgColor='F0FDF4')   # pale green
        REIMB_FILL   = PatternFill('solid', fgColor='F5F3FF')   # pale purple
        ALT_FILL     = PatternFill('solid', fgColor='F8FAFC')   # very light gray alt row
        TOTAL_FILL   = PatternFill('solid', fgColor='1E3A5F')
        TOTAL_FONT   = Font(bold=True, color='FFFFFF', size=11)
        OK_FILL      = PatternFill('solid', fgColor='DCFCE7')
        WARN_FILL    = PatternFill('solid', fgColor='FEF3C7')
        OVER_FILL    = PatternFill('solid', fgColor='FEE2E2')
        MONEY_FMT    = '#,##0.00'
        PCT_FMT      = '0.0%'

        def _hdr(ws, headers, col_widths):
            ws.append(headers)
            for i, _ in enumerate(headers, 1):
                c = ws.cell(1, i)
                c.fill = HDR_FILL; c.font = HDR_FONT
                c.alignment = Alignment(horizontal='center', vertical='center')
            ws.row_dimensions[1].height = 22
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for i, w in enumerate(col_widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w

        wb = openpyxl.Workbook()

        # ── Pre-compute totals ────────────────────────────────────────────────
        total_income   = sum(float(r[3] or 0) for r in tx_rows if r[6] == 'income')
        total_expenses = sum(float(r[3] or 0) for r in tx_rows if r[6] == 'expense' and float(r[3] or 0) >= 0)
        total_reimb    = sum(abs(float(r[3] or 0)) for r in tx_rows if r[6] == 'expense' and float(r[3] or 0) < 0)
        net_savings    = total_income - total_expenses + total_reimb

        # ── Sheet 1: Transaction Ledger ───────────────────────────────────────
        ws_tx = wb.active
        ws_tx.title = 'Transaction Ledger'

        # Title banner
        ws_tx.append([f'Personal Budget — {label_month}'])
        ws_tx.merge_cells('A1:G1')
        title_cell = ws_tx.cell(1, 1)
        title_cell.fill = HDR_FILL
        title_cell.font = Font(bold=True, color='FFFFFF', size=14)
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws_tx.row_dimensions[1].height = 28

        # Column headers (row 2)
        tx_headers = ['Date', 'Type', 'Description', 'Category', 'Amount', 'Frequency', 'Notes']
        tx_widths  = [13,     14,     36,             22,         14,       14,           30    ]
        ws_tx.append(tx_headers)
        for i, _ in enumerate(tx_headers, 1):
            c = ws_tx.cell(2, i)
            c.fill = SUB_FILL; c.font = SUB_FONT
            c.alignment = Alignment(horizontal='center', vertical='center')
        ws_tx.row_dimensions[2].height = 20
        ws_tx.freeze_panes = 'A3'
        for i, w in enumerate(tx_widths, 1):
            ws_tx.column_dimensions[get_column_letter(i)].width = w
        ws_tx.auto_filter.ref = f"A2:G{len(tx_rows) + 2}"

        FREQ_MAP = {
            'recurring':     'Regular',
            'one-time':      'One-Time',
            'bonus':         'Bonus',
            'reimbursement': 'Reimbursement',
        }
        TYPE_LABELS = {'expense': '💸 Expense', 'income': '💵 Income'}

        for row_num, r in enumerate(tx_rows, 3):
            _, tx_date, place, amount, category, label, tx_type, report_month = r
            amount_val = round(float(amount or 0), 2)
            is_reimb   = tx_type == 'expense' and amount_val < 0
            type_label = '↩️ Reimb.' if is_reimb else TYPE_LABELS.get(tx_type, tx_type.title())
            freq       = FREQ_MAP.get(str(label or '').lower(), str(label or '').title() or 'Regular')

            ws_tx.append([
                str(tx_date or ''),
                type_label,
                str(place or ''),
                str(category or ''),
                amount_val,
                freq,
                '',   # Notes — blank for user to fill
            ])

            if tx_type == 'income':
                row_fill = INCOME_FILL
            elif is_reimb:
                row_fill = REIMB_FILL
            else:
                row_fill = EXPENSE_FILL if row_num % 2 == 0 else ALT_FILL

            for col in range(1, 8):
                c = ws_tx.cell(row_num, col)
                c.fill = row_fill
                c.alignment = Alignment(vertical='center', wrap_text=(col == 7))

            amt_cell = ws_tx.cell(row_num, 5)
            amt_cell.number_format = MONEY_FMT
            amt_cell.alignment = Alignment(horizontal='right', vertical='center')
            if tx_type == 'income':
                amt_cell.font = Font(color='166534', bold=True)
            elif is_reimb:
                amt_cell.font = Font(color='5B21B6', bold=True)

        # Totals row at bottom of ledger
        total_row = len(tx_rows) + 3
        ws_tx.append(['', '', '', 'TOTAL', round(total_income - total_expenses + total_reimb, 2), '', ''])
        for col in range(1, 8):
            c = ws_tx.cell(total_row, col)
            c.fill = TOTAL_FILL; c.font = TOTAL_FONT
        ws_tx.cell(total_row, 5).number_format = MONEY_FMT
        ws_tx.cell(total_row, 5).alignment = Alignment(horizontal='right', vertical='center')

        # ── Sheet 2: Category Breakdown ───────────────────────────────────────
        ws_cat = wb.create_sheet('Category Breakdown')
        ws_cat.append([f'Category Breakdown — {label_month}'])
        ws_cat.merge_cells('A1:F1')
        c1 = ws_cat.cell(1, 1)
        c1.fill = HDR_FILL; c1.font = Font(bold=True, color='FFFFFF', size=13)
        c1.alignment = Alignment(horizontal='center', vertical='center')
        ws_cat.row_dimensions[1].height = 26

        cat_headers = ['Category', 'Total Spent', 'Transactions', 'Avg / Transaction', '% of Expenses', '% of Income']
        cat_widths  = [28,         16,             14,             20,                  16,               14           ]
        _hdr(ws_cat, cat_headers, cat_widths)
        ws_cat.freeze_panes = 'A3'

        cat_agg: dict = {}
        for r in tx_rows:
            _, _, _, amount, category, _, tx_type, _ = r
            amount_val = round(float(amount or 0), 2)
            if tx_type != 'expense' or amount_val < 0:
                continue
            cat = str(category or 'Uncategorized')
            if cat not in cat_agg:
                cat_agg[cat] = {'total': 0.0, 'count': 0}
            cat_agg[cat]['total'] += amount_val
            cat_agg[cat]['count'] += 1

        sorted_cats = sorted(cat_agg.items(), key=lambda x: -x[1]['total'])
        pct_income_avail = total_income > 0

        for i, (cat, data) in enumerate(sorted_cats):
            row_num = i + 3   # row 1=title, row 2=headers
            avg = data['total'] / data['count'] if data['count'] else 0
            pct_exp = data['total'] / total_expenses if total_expenses > 0 else 0
            pct_inc = data['total'] / total_income   if pct_income_avail else ''
            ws_cat.append([cat, round(data['total'], 2), data['count'], round(avg, 2), pct_exp, pct_inc])
            fill = ALT_FILL if i % 2 == 0 else PatternFill('solid', fgColor='FFFFFF')
            for col in range(1, 7):
                ws_cat.cell(row_num, col).fill = fill
            for col in (2, 4):
                ws_cat.cell(row_num, col).number_format = MONEY_FMT
                ws_cat.cell(row_num, col).alignment = Alignment(horizontal='right')
            for col in (5, 6):
                if pct_income_avail or col == 5:
                    ws_cat.cell(row_num, col).number_format = PCT_FMT
                    ws_cat.cell(row_num, col).alignment = Alignment(horizontal='right')

        # Grand-total row
        grand_total = sum(d['total'] for _, d in sorted_cats)
        grand_count = sum(d['count'] for _, d in sorted_cats)
        gt_row = len(sorted_cats) + 3
        ws_cat.append(['TOTAL EXPENSES', round(grand_total, 2), grand_count, '', 1.0 if sorted_cats else '', ''])
        for col in range(1, 7):
            c = ws_cat.cell(gt_row, col)
            c.fill = TOTAL_FILL; c.font = TOTAL_FONT
        ws_cat.cell(gt_row, 2).number_format = MONEY_FMT
        ws_cat.cell(gt_row, 2).alignment = Alignment(horizontal='right')
        ws_cat.cell(gt_row, 5).number_format = PCT_FMT

        # ── Sheet 3: Budget Overview ──────────────────────────────────────────
        ws_ov = wb.create_sheet('Budget Overview')

        def _ov_title(ws, text, row, cols='A:C'):
            ws.cell(row, 1, text).fill = HDR_FILL
            ws.cell(row, 1).font       = Font(bold=True, color='FFFFFF', size=12)
            ws.cell(row, 1).alignment  = Alignment(horizontal='left', vertical='center')
            ws.merge_cells(f'A{row}:{cols.split(":")[1]}{row}')
            ws.row_dimensions[row].height = 22

        def _ov_sub(ws, text, row):
            ws.cell(row, 1, text).fill = SUB_FILL
            ws.cell(row, 1).font       = SUB_FONT
            ws.cell(row, 1).alignment  = Alignment(horizontal='left', vertical='center')
            ws.merge_cells(f'A{row}:E{row}')
            ws.row_dimensions[row].height = 18

        def _ov_row(ws, row, lbl, actual, target, fill=None):
            variance = actual - target if target else 0
            status   = '✅ On Track' if variance <= 0 else '⚠️ Over Budget'
            row_fill = (fill or (OK_FILL if variance <= 0 else OVER_FILL))
            ws.cell(row, 1, lbl).alignment = Alignment(vertical='center')
            ws.cell(row, 2, round(actual,   2)).number_format = MONEY_FMT
            ws.cell(row, 3, round(target,   2)).number_format = MONEY_FMT
            ws.cell(row, 4, round(variance, 2)).number_format = MONEY_FMT
            ws.cell(row, 5, status)
            for col in range(1, 6):
                c = ws_ov.cell(row, col)
                c.fill = row_fill
                c.alignment = Alignment(vertical='center',
                                        horizontal='right' if col in (2, 3, 4) else 'left')
            ws.row_dimensions[row].height = 18
            return variance

        for col, w in zip('ABCDE', [30, 16, 16, 16, 16]):
            ws_ov.column_dimensions[col].width = w

        # Section 1: Income & Summary
        _ov_title(ws_ov, f'Budget Overview — {label_month}', 1, 'A:E')
        r = 2
        for col, hdr in enumerate(['', 'Actual', 'Target / Guide', 'Variance', 'Status'], 1):
            c = ws_ov.cell(r, col, hdr)
            c.fill = SUB_FILL; c.font = SUB_FONT
            c.alignment = Alignment(horizontal='center' if col > 1 else 'left', vertical='center')
        ws_ov.row_dimensions[r].height = 18
        r += 1

        # Income row
        ws_ov.cell(r, 1, '💵 Total Income').font = Font(bold=True)
        ws_ov.cell(r, 2, round(total_income, 2)).number_format = MONEY_FMT
        ws_ov.cell(r, 3, '—'); ws_ov.cell(r, 4, '—'); ws_ov.cell(r, 5, '—')
        for col in range(1, 6):
            ws_ov.cell(r, col).fill = INCOME_FILL
            ws_ov.cell(r, col).alignment = Alignment(
                vertical='center', horizontal='right' if col == 2 else 'left')
        ws_ov.row_dimensions[r].height = 18
        r += 1

        # Net savings row
        savings_target = round(total_income * 0.20, 2)
        ws_ov.cell(r, 1, '💰 Net Savings').font = Font(bold=True)
        ws_ov.cell(r, 2, round(net_savings, 2)).number_format = MONEY_FMT
        ws_ov.cell(r, 3, savings_target).number_format = MONEY_FMT
        savings_rate = net_savings / total_income if total_income > 0 else 0
        ws_ov.cell(r, 4, f'{savings_rate:.1%} of income')
        ws_ov.cell(r, 5, '✅ On Track' if savings_rate >= 0.20 else '⚠️ Below 20% target')
        sf = OK_FILL if savings_rate >= 0.20 else WARN_FILL
        for col in range(1, 6):
            ws_ov.cell(r, col).fill = sf
            ws_ov.cell(r, col).alignment = Alignment(
                vertical='center', horizontal='right' if col in (2, 3) else 'left')
        ws_ov.row_dimensions[r].height = 18
        r += 2   # blank spacer

        # Section 2: 50/30/20 Rule
        _ov_sub(ws_ov, '50 / 30 / 20 Rule Analysis  (based on total income)', r)
        r += 1

        NEEDS_CATS   = {'Housing', 'Rent', 'Mortgage', 'Utilities', 'Electric', 'Natural Gas',
                        'Water/Sewer', 'Internet/Cable', 'Groceries', 'Insurance', 'Health',
                        'Medical', 'Transportation', 'Gas/Fuel', 'Auto Maintenance', 'Childcare'}
        WANTS_CATS   = {'Dining', 'Entertainment', 'Shopping', 'Subscriptions', 'Travel',
                        'Vacation', 'Hobbies', 'Gym', 'Personal Care', 'Gifts & Charity',
                        'Gifts & Donations', 'Clothing', 'Electronics'}
        SAVINGS_CATS = {'Investment', 'Investment Transfer', 'Savings', 'Retirement', 'Emergency Fund'}

        buckets: dict = {'Needs': 0.0, 'Wants': 0.0, 'Savings & Investments': 0.0, 'Other': 0.0}
        for r_tx in tx_rows:
            _, _, _, amount, category, _, tx_type, _ = r_tx
            amount_val = round(float(amount or 0), 2)
            if tx_type != 'expense' or amount_val < 0:
                continue
            cat = str(category or '').strip()
            if cat in NEEDS_CATS:
                buckets['Needs'] += amount_val
            elif cat in WANTS_CATS:
                buckets['Wants'] += amount_val
            elif cat in SAVINGS_CATS:
                buckets['Savings & Investments'] += amount_val
            else:
                buckets['Other'] += amount_val

        bucket_targets = {
            'Needs':                 round(total_income * 0.50, 2),
            'Wants':                 round(total_income * 0.30, 2),
            'Savings & Investments': round(total_income * 0.20, 2),
            'Other':                 0.0,
        }
        BUCKET_EMOJI = {
            'Needs': '🏠', 'Wants': '🎉',
            'Savings & Investments': '📈', 'Other': '📦',
        }

        for col, hdr in enumerate(['Category', 'Actual', 'Target (50/30/20)', 'Variance', 'Status'], 1):
            c = ws_ov.cell(r, col, hdr)
            c.fill = SUB_FILL; c.font = SUB_FONT
            c.alignment = Alignment(horizontal='center' if col > 1 else 'left', vertical='center')
        ws_ov.row_dimensions[r].height = 18
        r += 1

        for bucket, actual in buckets.items():
            target  = bucket_targets[bucket]
            label_b = f"{BUCKET_EMOJI[bucket]} {bucket}"
            _ov_row(ws_ov, r, label_b, actual, target)
            r += 1

        r += 1   # blank spacer

        # Section 3: Category detail
        _ov_sub(ws_ov, 'Expense Breakdown by Category', r)
        r += 1

        for col, hdr in enumerate(['Category', 'Total Spent', '% of Expenses', '% of Income', ''], 1):
            c = ws_ov.cell(r, col, hdr)
            c.fill = SUB_FILL; c.font = SUB_FONT
            c.alignment = Alignment(horizontal='center' if col > 1 else 'left', vertical='center')
        ws_ov.row_dimensions[r].height = 18
        r += 1

        for i, (cat, data) in enumerate(sorted_cats):
            pct_exp = data['total'] / total_expenses if total_expenses > 0 else 0
            pct_inc = data['total'] / total_income   if total_income   > 0 else 0
            fill = ALT_FILL if i % 2 == 0 else PatternFill('solid', fgColor='FFFFFF')
            ws_ov.cell(r, 1, cat).fill = fill
            ws_ov.cell(r, 2, round(data['total'], 2)).number_format = MONEY_FMT
            ws_ov.cell(r, 3, pct_exp).number_format = PCT_FMT
            ws_ov.cell(r, 4, pct_inc).number_format = PCT_FMT
            for col in range(1, 5):
                ws_ov.cell(r, col).fill = fill
                ws_ov.cell(r, col).alignment = Alignment(
                    vertical='center', horizontal='right' if col > 1 else 'left')
            r += 1

        # ── Serialise ─────────────────────────────────────────────────────────
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"budget_{month or 'all'}.xlsx"
        return StreamingResponse(
            buf,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    except Exception as exc:
        logging.exception("Excel export failed")
        return JSONResponse(status_code=500, content={'error': str(exc)})
