#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggregate Monthly Transactions by Calendar Month

Reads all expenses.csv and income.csv files from statements/*/ directories,
groups transactions by their actual calendar month (from Transaction Date),
and writes directly to the SQLite DB (src/ui/data/budget.db).

monthly_reports/ CSV files are no longer generated; the DB is the sole
authoritative store for aggregated transaction data.

Usage:
    python aggregate_monthly.py                  # Aggregate all transactions
    python aggregate_monthly.py --debug          # Show detailed progress
"""

import sys
import argparse
import json
from pathlib import Path
import pandas as pd

_PROJECT_ROOT = Path(__file__).parent.parent



def _load_investment_keywords_from_db(engine) -> list:
    """Load investment-platform keywords from the DB."""
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            rows = conn.execute(_text('SELECT keyword FROM investment_keywords ORDER BY keyword')).fetchall()
        return [r[0] for r in rows]
    except Exception:
        pass
    return []

def _build_merchant_category_map(expenses_df: pd.DataFrame) -> dict:
    """
    Build a normalized-merchant → most-common-category map from expense data.
    Used to auto-categorize reimbursements by matching merchant name.
    """
    import re
    def _norm(name: str) -> str:
        s = str(name).lower()
        s = re.sub(r"['\.\-,]", '', s)
        s = re.sub(r'#\d+', '', s)
        s = re.sub(r'\b\d{3,}\b', '', s)
        return ' '.join(s.split())

    if expenses_df.empty or 'Place' not in expenses_df.columns or 'category' not in expenses_df.columns:
        return {}

    from collections import Counter, defaultdict
    counts = defaultdict(Counter)
    for _, row in expenses_df.iterrows():
        place = str(row.get('Place', '')).strip()
        cat = str(row.get('category', '')).strip()
        if not place or not cat or cat.lower() in ('uncategorized', 'nan', ''):
            continue
        counts[_norm(place)][cat] += 1

    return {merchant: counter.most_common(1)[0][0] for merchant, counter in counts.items()}


def _categorize_reimbursements(income_df: pd.DataFrame, merchant_cat_map: dict) -> pd.DataFrame:
    """
    For rows labelled 'reimbursement' with no category, look up the merchant in
    the expense history and assign the same category as the matching purchase.
    """
    import re
    def _norm(name: str) -> str:
        s = str(name).lower()
        s = re.sub(r"['\.\-,]", '', s)
        s = re.sub(r'#\d+', '', s)
        s = re.sub(r'\b\d{3,}\b', '', s)
        return ' '.join(s.split())

    if income_df.empty or not merchant_cat_map:
        return income_df

    if 'Label' not in income_df.columns or 'category' not in income_df.columns:
        return income_df

    income_df = income_df.copy()
    for idx, row in income_df.iterrows():
        if str(row.get('Label', '')).strip() != 'reimbursement':
            continue
        existing_cat = str(row.get('category', '')).strip()
        if existing_cat and existing_cat.lower() not in ('uncategorized', 'nan', ''):
            continue  # already categorized — don't overwrite
        key = _norm(str(row.get('Place', '')))
        cat = merchant_cat_map.get(key)
        if cat:
            income_df.at[idx, 'category'] = cat
    return income_df


def _auto_classify_income(df: pd.DataFrame, median_multiple: float = 1.75) -> pd.DataFrame:
    """Label each income row 'recurring' or 'bonus' using median-multiple detection.
    Rows already labelled 'reimbursement' (credit-card returns) are left untouched."""
    if df.empty or 'Amount' not in df.columns:
        df = df.copy()
        df['Label'] = 'recurring'
        return df
    df = df.copy()
    # Preserve pre-set reimbursement labels
    existing_reimb = df.get('Label', pd.Series(dtype=str)) == 'reimbursement'
    amounts = pd.to_numeric(df['Amount'], errors='coerce').dropna()
    median_amt = amounts.median() if not amounts.empty else 0.0
    threshold = median_amt * median_multiple if median_amt > 0 else float('inf')
    df['_amt_num'] = pd.to_numeric(df['Amount'], errors='coerce')
    df['Label'] = df['_amt_num'].apply(
        lambda a: 'bonus' if (pd.notna(a) and a >= threshold) else 'recurring'
    )
    # Re-apply reimbursement labels that were set during processing
    df.loc[existing_reimb, 'Label'] = 'reimbursement'
    df = df.drop(columns=['_amt_num'])
    return df


def _auto_classify_expenses(df: pd.DataFrame, abs_floor: float = 500.0, cat_multiple: float = 3.0) -> pd.DataFrame:
    """Label each expense row 'recurring' or 'one-time' using per-category median detection."""
    if df.empty or 'Amount' not in df.columns:
        df = df.copy()
        df['Label'] = 'recurring'
        return df
    df = df.copy()
    df['_amt_num'] = pd.to_numeric(df['Amount'], errors='coerce')
    cat_col = next((c for c in df.columns if c.lower() == 'category'), None)
    if cat_col:
        cat_medians = df.groupby(cat_col)['_amt_num'].median()
        def _classify(row):
            amt = row['_amt_num']
            if pd.isna(amt) or amt < abs_floor:
                return 'recurring'
            med = cat_medians.get(row.get(cat_col, ''), 0)
            return 'one-time' if med > 0 and amt >= cat_multiple * med else 'recurring'
        df['Label'] = df.apply(_classify, axis=1)
    else:
        overall_med = df['_amt_num'].median()
        df['Label'] = df['_amt_num'].apply(
            lambda a: 'one-time' if (pd.notna(a) and a >= abs_floor and overall_med > 0 and a >= cat_multiple * overall_med) else 'recurring'
        )
    df = df.drop(columns=['_amt_num'])
    return df


def aggregate_by_transaction_month(debug: bool = False):
    """
    Aggregate all expenses and income by their actual transaction month
    and write the results directly to the SQLite DB.

    Reads all transaction rows from the DB, re-groups them by the actual
    calendar month derived from tx_date, applies auto-classification, and
    writes back to the DB with corrected report_month values.
    """
    if debug:
        print("\n" + "="*70)
        print("Aggregating transactions by calendar month...")
        print("="*70)

    # Initialise DB connection early so per-month writes can happen inline
    _db_engine = None
    try:
        sys.path.insert(0, str(_PROJECT_ROOT))
        from src.database.session import init_db, get_engine
        from src.database.db_utils import write_month_to_db, write_transfers_to_db
        _db_engine = init_db()
    except ImportError:
        pass  # SQLAlchemy not installed — DB writes skipped
    except Exception as exc:
        print(f"⚠  DB init failed (non-fatal): {exc}")

    if _db_engine is None:
        print("⚠  DB unavailable — cannot aggregate (no data source)")
        return

    from sqlalchemy import text as _text

    # Load investment keywords from DB (single source of truth)
    _INVESTMENT_PLATFORM_KEYWORDS = _load_investment_keywords_from_db(_db_engine)

    # ── Read ALL expenses and income from DB ──────────────────────────────────
    all_expenses = []
    all_income = []

    try:
        with _db_engine.connect() as conn:
            exp_rows = conn.execute(_text(
                "SELECT tx_date, place, amount, category, label, statement, source_statement "
                "FROM transactions WHERE tx_type='expense' ORDER BY tx_date"
            )).fetchall()
        if exp_rows:
            df = pd.DataFrame(exp_rows, columns=['Transaction Date', 'Place', 'Amount', 'category', 'Label', 'Statement', 'source_statement'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
            all_expenses = [df]
            if debug:
                print(f"  Read {len(df)} expenses from DB")
        elif debug:
            print("  No expense rows in DB")
    except Exception as exc:
        print(f"⚠  Failed to read expenses from DB: {exc}")
        return

    try:
        with _db_engine.connect() as conn:
            inc_rows = conn.execute(_text(
                "SELECT tx_date, place, amount, category, label, statement "
                "FROM transactions WHERE tx_type='income' ORDER BY tx_date"
            )).fetchall()
        if inc_rows:
            df = pd.DataFrame(inc_rows, columns=['Transaction Date', 'Place', 'Amount', 'category', 'Label', 'Statement'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
            all_income = [df]
            if debug:
                print(f"  Read {len(df)} income rows from DB")
    except Exception as exc:
        print(f"⚠  Failed to read income from DB: {exc}")

    # ── Process expenses ──────────────────────────────────────────────────────
    category_promoted_transfers = []
    if all_expenses:
        combined_expenses = pd.concat(all_expenses, ignore_index=True)
        # Dedup: rows that share (date, place, amount, statement) but came from
        # DIFFERENT source_statements are cross-statement duplicates introduced by
        # a prior parsing bug — keep only the one from the LATEST source_statement.
        # Rows that share all those columns AND the same source_statement are genuine
        # separate transactions (e.g. two ATM withdrawals from the same PDF parse) and
        # must be preserved.
        _grp_cols = [c for c in ['Transaction Date', 'Place', 'Amount', 'Statement']
                     if c in combined_expenses.columns]
        if 'source_statement' in combined_expenses.columns and _grp_cols:
            _src_nunique = combined_expenses.groupby(_grp_cols, sort=False)['source_statement'].transform(
                lambda x: x.fillna('').nunique()
            )
            if (_src_nunique > 1).any():
                # Sort so the latest source_statement wins (keep='first' after sort)
                combined_expenses = combined_expenses.sort_values(
                    'source_statement', ascending=False, na_position='last', kind='stable'
                )
                _cross_src = _src_nunique > 1
                _to_drop   = _cross_src & combined_expenses.duplicated(subset=_grp_cols, keep='first')
                _removed   = _to_drop.sum()
                combined_expenses = combined_expenses[~_to_drop].reset_index(drop=True)
                if _removed and debug:
                    print(f"  Removed {_removed} cross-statement expense duplicate(s) via source_statement dedup")
        # Note: No further dedup here — the source_statement-aware cross-source dedup
        # above is the correct guard.  A blanket drop_duplicates on visible fields would
        # silently collapse genuine same-day same-amount transactions (e.g. two $200
        # ATM withdrawals from the same bank on the same day).

        if debug:
            print(f"\n  Combined {len(combined_expenses)} unique expenses")

        combined_expenses = _auto_classify_expenses(combined_expenses)

        combined_expenses['_parsed_date'] = pd.to_datetime(
            combined_expenses['Transaction Date'], format='mixed', errors='coerce'
        )
        combined_expenses['_month'] = combined_expenses['_parsed_date'].dt.strftime('%Y-%m')

        if _db_engine is not None:
            # Snapshot all user-corrected expense rows BEFORE the global wipe so
            # write_month_to_db can reapply them after per-month replacement.
            with _db_engine.connect() as conn:
                _uc_exp = conn.execute(_text(
                    "SELECT tx_hash, category, label, place, amount, report_month, tx_date "
                    "FROM transactions WHERE tx_type='expense' AND user_corrected=1"
                )).fetchall()
                conn.execute(_text("DELETE FROM transactions WHERE tx_type='expense'"))
                conn.commit()

        months_written = 0
        for month, group in combined_expenses.groupby('_month'):
            if pd.isna(month):
                continue

            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop).sort_values('Transaction Date')

            # Restore user-set labels/categories from DB (user_corrected rows survive re-agg)
            # Note: write_month_to_db handles this automatically via its user_corrected logic.

            # Mirror Investment Transfer rows to the transfers pipeline
            if 'category' in output_df.columns:
                inv_mask = output_df['category'].astype(str).str.strip().isin(['Investment', 'Investment Transfer'])
                inv_rows = output_df[inv_mask].copy()
                if not inv_rows.empty:
                    t = pd.DataFrame({
                        'Transaction Date': inv_rows['Transaction Date'].values,
                        'Place':            inv_rows['Place'].values,
                        'Amount':           inv_rows['Amount'].values,
                        'Direction':        'Out',
                        'Statement':        inv_rows['Statement'].values if 'Statement' in inv_rows.columns else 'Manual',
                    })
                    category_promoted_transfers.append(t)
                    if debug:
                        print(f"  Promoted {len(inv_rows)} Investment Transfer expense(s) to transfers for {month}")

            # Write to DB
            if _db_engine is not None:
                try:
                    n = write_month_to_db(_db_engine, month, expenses_df=output_df)
                    months_written += 1
                    if debug:
                        print(f"  Wrote {n} expense rows for {month} to DB")
                except Exception as exc:
                    print(f"  ⚠  DB write for {month} expenses failed: {exc}")
            else:
                months_written += 1

        print(f"\n✓ Processed expenses for {months_written} month(s)")

        # Reapply user corrections that existed before the global wipe.
        # Try by tx_hash first; fall back to (tx_date, place, amount) because
        # the hash changes when report_month changes (cross-month transaction
        # moved by aggregate re-grouping).
        if _db_engine is not None and _uc_exp:
            applied = 0
            with _db_engine.connect() as conn:
                for uc in _uc_exp:
                    tx_hash, cat, lbl, place, amt, rmonth, tx_date = uc
                    res = conn.execute(_text(
                        "UPDATE transactions SET "
                        "  category=COALESCE(:cat, category), "
                        "  label=COALESCE(:lbl, label), "
                        "  place=COALESCE(:pl, place), "
                        "  amount=COALESCE(:amt, amount), "
                        "  user_corrected=1 "
                        "WHERE tx_hash=:h"
                    ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'h': tx_hash})
                    if res.rowcount == 0:
                        # Hash mismatch — tx changed report_month; restore by tx_date+place+amount
                        if tx_date:
                            conn.execute(_text(
                                "UPDATE transactions SET "
                                "  category=COALESCE(:cat, category), "
                                "  label=COALESCE(:lbl, label), "
                                "  user_corrected=1 "
                                "WHERE tx_date=:d "
                                "  AND UPPER(place)=UPPER(:pl) "
                                "  AND ROUND(amount,2)=ROUND(:amt,2)"
                            ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'd': tx_date})
                        else:
                            conn.execute(_text(
                                "UPDATE transactions SET "
                                "  category=COALESCE(:cat, category), "
                                "  label=COALESCE(:lbl, label), "
                                "  user_corrected=1 "
                                "WHERE report_month=:m "
                                "  AND UPPER(place)=UPPER(:pl) "
                                "  AND ROUND(amount,2)=ROUND(:amt,2)"
                            ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'm': rmonth})
                    applied += 1
                conn.commit()
            if debug:
                print(f"  Re-applied {applied} user-corrected expense row(s)")
    else:
        print("\n⚠ No expense data found")

    # ── Process income ────────────────────────────────────────────────────────
    income_return_transfers = []
    merchant_cat_map = _build_merchant_category_map(
        pd.concat(all_expenses, ignore_index=True) if all_expenses else pd.DataFrame()
    )
    if all_income:
        combined_income = pd.concat(all_income, ignore_index=True)
        _grp_cols_inc = [c for c in ['Transaction Date', 'Place', 'Amount', 'Statement']
                         if c in combined_income.columns]
        if 'source_statement' in combined_income.columns and _grp_cols_inc:
            _src_nunique_inc = combined_income.groupby(_grp_cols_inc, sort=False)['source_statement'].transform(
                lambda x: x.fillna('').nunique()
            )
            if (_src_nunique_inc > 1).any():
                combined_income = combined_income.sort_values(
                    'source_statement', ascending=False, na_position='last', kind='stable'
                )
                _cross_src_inc = _src_nunique_inc > 1
                _to_drop_inc   = _cross_src_inc & combined_income.duplicated(subset=_grp_cols_inc, keep='first')
                combined_income = combined_income[~_to_drop_inc].reset_index(drop=True)
        # No further dedup — same reasoning as expenses above.

        if debug:
            print(f"\n  Combined {len(combined_income)} unique income transactions")

        combined_income = _auto_classify_income(combined_income)

        combined_income['_parsed_date'] = pd.to_datetime(
            combined_income['Transaction Date'], format='mixed', errors='coerce'
        )
        combined_income['_month'] = combined_income['_parsed_date'].dt.strftime('%Y-%m')

        if _db_engine is not None:
            # Snapshot all user-corrected income rows BEFORE the global wipe.
            with _db_engine.connect() as conn:
                _uc_inc = conn.execute(_text(
                    "SELECT tx_hash, category, label, place, amount, report_month, tx_date "
                    "FROM transactions WHERE tx_type='income' AND user_corrected=1"
                )).fetchall()
                conn.execute(_text("DELETE FROM transactions WHERE tx_type='income'"))
                conn.commit()

        months_written = 0
        for month, group in combined_income.groupby('_month'):
            if pd.isna(month):
                continue

            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop).sort_values('Transaction Date')

            if 'category' not in output_df.columns:
                output_df['category'] = ''
            elif output_df['category'].dtype != object:
                output_df['category'] = output_df['category'].astype(object).fillna('')
            output_df = _categorize_reimbursements(output_df, merchant_cat_map)

            # Mirror Investment Return + platform rows to transfers (Direction=In)
            is_tagged   = output_df['category'].astype(str).str.strip() == 'Investment Return' if 'category' in output_df.columns else pd.Series(False, index=output_df.index)
            is_platform = output_df['Place'].astype(str).str.lower().apply(
                lambda p: any(kw in p for kw in _INVESTMENT_PLATFORM_KEYWORDS)
            )
            ret_rows = output_df[is_tagged | is_platform].copy()
            if not ret_rows.empty:
                t = pd.DataFrame({
                    'Transaction Date': ret_rows['Transaction Date'].values,
                    'Place':            ret_rows['Place'].values,
                    'Amount':           ret_rows['Amount'].values,
                    'Direction':        'In',
                    'Statement':        ret_rows['Statement'].values if 'Statement' in ret_rows.columns else 'Manual',
                })
                income_return_transfers.append(t)
                if debug:
                    print(f"  Mirrored {len(ret_rows)} investment income row(s) to transfers for {month}")

            # Write to DB
            if _db_engine is not None:
                try:
                    n = write_month_to_db(_db_engine, month, income_df=output_df)
                    months_written += 1
                    if debug:
                        print(f"  Wrote {n} income rows for {month} to DB")
                except Exception as exc:
                    print(f"  ⚠  DB write for {month} income failed: {exc}")
            else:
                months_written += 1

        print(f"✓ Processed income for {months_written} month(s)")

        # Reapply user corrections that existed before the global wipe.
        # Try by tx_hash first; fall back to (tx_date, place, amount) because
        # the hash changes when tx_type changes (e.g. expense→income).
        if _db_engine is not None and _uc_inc:
            applied = 0
            with _db_engine.connect() as conn:
                for uc in _uc_inc:
                    tx_hash, cat, lbl, place, amt, rmonth, tx_date = uc
                    res = conn.execute(_text(
                        "UPDATE transactions SET "
                        "  category=COALESCE(:cat, category), "
                        "  label=COALESCE(:lbl, label), "
                        "  place=COALESCE(:pl, place), "
                        "  amount=COALESCE(:amt, amount), "
                        "  user_corrected=1 "
                        "WHERE tx_hash=:h"
                    ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'h': tx_hash})
                    if res.rowcount == 0:
                        if tx_date:
                            conn.execute(_text(
                                "UPDATE transactions SET "
                                "  category=COALESCE(:cat, category), "
                                "  label=COALESCE(:lbl, label), "
                                "  user_corrected=1 "
                                "WHERE tx_date=:d "
                                "  AND UPPER(place)=UPPER(:pl) "
                                "  AND ROUND(amount,2)=ROUND(:amt,2)"
                            ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'd': tx_date})
                        else:
                            conn.execute(_text(
                                "UPDATE transactions SET "
                                "  category=COALESCE(:cat, category), "
                                "  label=COALESCE(:lbl, label), "
                                "  user_corrected=1 "
                                "WHERE report_month=:m "
                                "  AND UPPER(place)=UPPER(:pl) "
                                "  AND ROUND(amount,2)=ROUND(:amt,2)"
                            ), {'cat': cat, 'lbl': lbl, 'pl': place, 'amt': amt, 'm': rmonth})
                    applied += 1
                conn.commit()
            if debug:
                print(f"  Re-applied {applied} user-corrected income row(s)")
    else:
        print("\n⚠ No income data found")

    # ── Process investment transfers ──────────────────────────────────────────
    all_transfers = []
    if category_promoted_transfers:
        all_transfers.extend(category_promoted_transfers)
    if income_return_transfers:
        all_transfers.extend(income_return_transfers)

    # NOTE: Do NOT read existing transfers from DB here.
    # category_promoted_transfers (from Investment-categorised expenses) and
    # income_return_transfers (from investment income) are freshly derived each
    # run and are the complete source of truth for the transfers table.
    # Reading old DB rows back and merging them would double-count on every run.

    if all_transfers and _db_engine is not None:
        combined_transfers = pd.concat(all_transfers, ignore_index=True)
        _tr_dedup_cols = ['Transaction Date', 'Place', 'Amount', 'Direction', 'Statement']
        _tr_dedup_cols = [c for c in _tr_dedup_cols if c in combined_transfers.columns]
        combined_transfers = combined_transfers.drop_duplicates(subset=_tr_dedup_cols, keep='first')
        combined_transfers['_parsed_date'] = pd.to_datetime(
            combined_transfers['Transaction Date'], format='mixed', errors='coerce'
        )
        combined_transfers['_month'] = combined_transfers['_parsed_date'].dt.strftime('%Y-%m')
        with _db_engine.connect() as conn:
            conn.execute(_text("DELETE FROM transfers"))
            conn.commit()
        months_saved = 0
        for month, group in combined_transfers.groupby('_month'):
            if pd.isna(month):
                continue
            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop).sort_values('Transaction Date')
            try:
                rows_list = [
                    {
                        'tx_date':   str(r.get('Transaction Date', '')),
                        'place':     str(r.get('Place', '')),
                        'amount':    float(r.get('Amount', 0) or 0),
                        'direction': str(r.get('Direction', 'Out')),
                        'statement': str(r.get('Statement', '')),
                    }
                    for _, r in output_df.iterrows()
                ]
                write_transfers_to_db(_db_engine, month, rows_list)
                months_saved += 1
                if debug:
                    total = output_df['Amount'].sum() if 'Amount' in output_df.columns else 0
                    print(f"  Wrote {len(rows_list)} transfers for {month} to DB (${total:.2f})")
            except Exception as exc:
                print(f"  ⚠  DB write for {month} transfers failed: {exc}")
        print(f"✓ Processed investment transfers for {months_saved} month(s)")
    elif all_transfers:
        if debug:
            print("\n  (DB unavailable — transfer rows not persisted)")

    print(f"\n✓ Aggregation complete — data written to DB")
    print("="*70)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Aggregate transactions by calendar month (not statement month)'
    )
    parser.add_argument(
        '--statements-dir',
        type=str,
        default='src/ui/data/statements',
        help='Directory containing monthly folders (default: src/ui/data/statements)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output to see detailed progress'
    )
    
    args = parser.parse_args()
    
    # Get statements directory
    if Path(args.statements_dir).is_absolute():
        statements_dir = Path(args.statements_dir)
    else:
        statements_dir = Path(__file__).parent.parent / args.statements_dir
    
    # Run aggregation
    aggregate_by_transaction_month(debug=args.debug)


if __name__ == '__main__':
    main()
