#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggregate Monthly Transactions by Calendar Month

Reads all expenses.csv and income.csv files from statements/*/ directories,
groups transactions by their actual calendar month (from Transaction Date),
and saves to monthly_reports/expenses_YYYY-MM.csv and income_YYYY-MM.csv.

This allows viewing all expenses for YYYY-MM together, even if they appeared
in different statement months (e.g., Oct statement, Nov statement, Dec statement).

Usage:
    python aggregate_monthly.py                  # Aggregate all transactions
    python aggregate_monthly.py --debug          # Show detailed progress
"""

import sys
import argparse
from pathlib import Path
import pandas as pd

# TODO: Move this list to config/investment_platforms.json and load it at startup
# so platforms can be added/removed without a code change or container rebuild.
# See docs/FUTURE_FEATURES.md — Technical Debt > High Priority (database-backed merchant metadata).
_INVESTMENT_PLATFORM_KEYWORDS = [
    'investment', 'brokerage', 'trading', 'portfolio', 'securities', 'fund',
    'robinhood', 'edward jones', 'cash app', 'vanguard', 'fidelity', 'schwab',
    'ameritrade', 'webull', 'acorns', 'stash', 'betterment', 'wealthfront', 'sofi',
]

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


def _restore_user_labels(new_df: pd.DataFrame, existing_file: Path) -> pd.DataFrame:
    """Overwrite auto-classified labels with any user-set labels saved in an existing CSV."""
    if not existing_file.exists() or 'Label' not in new_df.columns:
        return new_df
    try:
        existing = pd.read_csv(existing_file)
        if 'Label' not in existing.columns:
            return new_df
        label_map = {}
        for _, row in existing.iterrows():
            try:
                key = (
                    str(row.get('Transaction Date', '')).strip(),
                    str(row.get('Place', '')).strip().upper(),
                    round(float(row.get('Amount', 0)), 2),
                )
                lbl = str(row.get('Label', '')).strip()
                if lbl:
                    label_map[key] = lbl
            except Exception:
                continue
        if not label_map:
            return new_df
        def _restore(row):
            try:
                key = (
                    str(row.get('Transaction Date', '')).strip(),
                    str(row.get('Place', '')).strip().upper(),
                    round(float(row.get('Amount', 0)), 2),
                )
                return label_map.get(key, row.get('Label', 'recurring'))
            except Exception:
                return row.get('Label', 'recurring')
        new_df = new_df.copy()
        new_df['Label'] = new_df.apply(_restore, axis=1)
    except Exception:
        pass
    return new_df


def _restore_user_categories(new_df: pd.DataFrame, existing_file: Path, debug: bool = False) -> pd.DataFrame:
    """
    Overwrite AI-assigned categories with any user-edited categories saved in an
    existing monthly_reports CSV.  Keyed on (Transaction Date, Place, Amount) so
    it survives re-aggregation when new statement months are added.
    Only restores rows where the existing category is non-empty and not
    'Uncategorized', so genuinely new transactions still get AI-classified.
    """
    if not existing_file.exists() or 'category' not in new_df.columns:
        return new_df
    try:
        existing = pd.read_csv(existing_file)
        if 'category' not in existing.columns:
            return new_df
        # Build map: (date, place_upper, amount) -> category
        # Only include rows explicitly corrected by the user (user_corrected=True).
        # AI-assigned categories from prior runs are NOT restored so that improved
        # merchant history can override them on the next re-aggregate.
        cat_map = {}
        for _, row in existing.iterrows():
            try:
                # Skip rows not explicitly corrected by the user
                user_corrected = row.get('user_corrected', False)
                if str(user_corrected).strip().lower() not in ('true', '1', 'yes'):
                    continue
                cat = str(row.get('category', '')).strip()
                # Skip blank / Uncategorized / summary rows
                if not cat or cat.lower() in ('uncategorized', 'nan', ''):
                    continue
                place = str(row.get('Place', '')).strip()
                if place.startswith('---') or place.startswith('Total:') or place == 'GRAND TOTAL':
                    continue
                key = (
                    str(row.get('Transaction Date', '')).strip(),
                    place.upper(),
                    round(float(row.get('Amount', 0)), 2),
                )
                cat_map[key] = cat
            except Exception:
                continue
        if not cat_map:
            return new_df
        restored = 0
        def _restore_cat(row):
            nonlocal restored
            try:
                key = (
                    str(row.get('Transaction Date', '')).strip(),
                    str(row.get('Place', '')).strip().upper(),
                    round(float(row.get('Amount', 0)), 2),
                )
                saved = cat_map.get(key)
                if saved:
                    restored += 1
                    return saved
            except Exception:
                pass
            return row.get('category', 'Uncategorized')
        new_df = new_df.copy()
        new_df['category'] = new_df.apply(_restore_cat, axis=1)
        if debug and restored:
            print(f"     Restored {restored} user-edited category(ies) from {existing_file.name}")
    except Exception:
        pass
    return new_df


def aggregate_by_transaction_month(statements_dir: Path, debug: bool = False):
    """
    Aggregate all expenses and income by their actual transaction month.
    
    Args:
        statements_dir: Path to statements directory
        debug: Print debug information
    """
    if debug:
        print("\n" + "="*70)
        print("Aggregating transactions by calendar month...")
        print("="*70)
    
    # statements_dir is already src/ui/data/statements; monthly_reports is its sibling
    reports_dir = statements_dir.parent / 'monthly_reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect all expenses and income
    all_expenses = []
    all_income = []
    
    for month_dir in sorted(statements_dir.glob('*')):
        if not month_dir.is_dir():
            continue
        
        # Read expenses
        expenses_file = month_dir / 'expenses.csv'
        if expenses_file.exists():
            try:
                df = pd.read_csv(expenses_file)
                if not df.empty:
                    # Filter out summary rows (expense breakdown)
                    if 'Place' in df.columns:
                        df = df[~df['Place'].astype(str).str.contains(
                            'EXPENSE BREAKDOWN|Total:|GRAND TOTAL',
                            case=False, na=False, regex=True
                        )]
                    
                    if not df.empty:
                        all_expenses.append(df)
                        if debug:
                            print(f"  Read {len(df)} expenses from {month_dir.name}")
            except Exception as e:
                if debug:
                    print(f"  Warning: Could not read {expenses_file}: {e}")
        
        # Read income
        income_file = month_dir / 'income.csv'
        if income_file.exists():
            try:
                df = pd.read_csv(income_file)
                if not df.empty:
                    all_income.append(df)
                    if debug:
                        print(f"  Read {len(df)} income from {month_dir.name}")
            except Exception as e:
                if debug:
                    print(f"  Warning: Could not read {income_file}: {e}")
    
    # Process expenses
    category_promoted_transfers = []  # rows reclassified as Investment Transfer
    if all_expenses:
        combined_expenses = pd.concat(all_expenses, ignore_index=True)
        
        # Remove duplicates (same transaction appearing in multiple statements)
        # Use all columns except Source/Statement for duplicate detection
        dedup_cols = [col for col in combined_expenses.columns if col not in ['Source', 'Statement']]
        combined_expenses = combined_expenses.drop_duplicates(subset=dedup_cols, keep='first')
        
        if debug:
            print(f"\n  Combined {len(combined_expenses)} unique expenses")

        # Auto-classify expenses as 'recurring' or 'one-time'
        combined_expenses = _auto_classify_expenses(combined_expenses)

        # Parse transaction dates and extract year-month
        # Handle both 2-digit and 4-digit year formats (MM/DD/YY and MM/DD/YYYY)
        combined_expenses['_parsed_date'] = pd.to_datetime(
            combined_expenses['Transaction Date'],
            format='mixed',
            errors='coerce'
        )
        combined_expenses['_month'] = combined_expenses['_parsed_date'].dt.strftime('%Y-%m')
        
        # Collect rows promoted to transfers via the 'Investment Transfer' category
        # (defined before this block so it's always accessible)

        # Group by month and save
        months_saved = 0
        for month, group in combined_expenses.groupby('_month'):
            if pd.isna(month):
                continue
            
            # Remove temporary columns and Place_Original
            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop)
            
            # Sort by date within month
            output_df = output_df.sort_values('Transaction Date')

            # Restore any user-set labels (overrides auto-classification)
            output_file = reports_dir / f'expenses_{month}.csv'
            output_df = _restore_user_labels(output_df, output_file)
            # Restore any user-edited categories (overrides AI re-classification on re-aggregation)
            output_df = _restore_user_categories(output_df, output_file, debug=debug)
            # Mirror 'Investment Transfer' (or legacy 'Investment') rows → transfers pipeline
            # Rows stay in expenses AND are copied to transfers; removing the category re-moves them
            if 'category' in output_df.columns:
                inv_mask = output_df['category'].astype(str).str.strip().isin(['Investment', 'Investment Transfer'])
                inv_rows = output_df[inv_mask].copy()
                # Do NOT remove from output_df — keep them in expenses too
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

            # Add expense breakdown summary at the end
            if 'category' in output_df.columns:
                # Calculate totals BEFORE adding summary rows
                grand_total = round(output_df['Amount'].sum(), 2)
                category_totals = output_df.groupby('category')['Amount'].sum().sort_values(ascending=False)
                
                # Get all columns except 'category' for summary rows
                base_columns = [col for col in output_df.columns if col != 'category']
                
                # Create summary rows WITHOUT the category column
                summary_rows = []
                
                # Header row
                header_dict = {col: '' for col in base_columns}
                header_dict['Place'] = '--- EXPENSE BREAKDOWN ---'
                summary_rows.append(header_dict)
                
                # Category total rows
                for cat, total in category_totals.items():
                    row_dict = {col: '' for col in base_columns}
                    row_dict['Place'] = f'Total: {cat}'
                    row_dict['Amount'] = round(total, 2)
                    summary_rows.append(row_dict)
                
                # Grand total row
                grand_dict = {col: '' for col in base_columns}
                grand_dict['Place'] = 'GRAND TOTAL'
                grand_dict['Amount'] = grand_total
                summary_rows.append(grand_dict)
                
                # Append summary to expenses
                summary_df = pd.DataFrame(summary_rows)
                output_with_summary = pd.concat([output_df, summary_df], ignore_index=True)
                
                # Save to monthly_reports
                output_file = reports_dir / f'expenses_{month}.csv'
                output_with_summary.to_csv(output_file, index=False)
                months_saved += 1
                
                if debug:
                    print(f"  Saved {len(output_df)} expenses + breakdown to {output_file.name} (${grand_total:.2f})")
            else:
                # No category column, save without summary
                output_file = reports_dir / f'expenses_{month}.csv'
                output_df.to_csv(output_file, index=False)
                months_saved += 1
                
                if debug:
                    total_amount = output_df['Amount'].sum() if 'Amount' in output_df.columns else 0
                    print(f"  Saved {len(output_df)} expenses to {output_file.name} (${total_amount:.2f})")
        
        print(f"\n✓ Saved expenses for {months_saved} month(s)")
    else:
        print("\n⚠ No expense data found")
    
    # Process income
    income_return_transfers = []  # income rows marked as Investment Return → Direction=In
    # Build merchant→category map from all expenses so reimbursements can be auto-categorized
    merchant_cat_map = _build_merchant_category_map(
        pd.concat(all_expenses, ignore_index=True) if all_expenses else pd.DataFrame()
    )
    if all_income:
        combined_income = pd.concat(all_income, ignore_index=True)
        
        # Remove duplicates
        dedup_cols = [col for col in combined_income.columns if col not in ['Source', 'Statement']]
        combined_income = combined_income.drop_duplicates(subset=dedup_cols, keep='first')
        
        if debug:
            print(f"\n  Combined {len(combined_income)} unique income transactions")

        # Auto-classify income as 'recurring' or 'bonus'
        combined_income = _auto_classify_income(combined_income)

        # Parse transaction dates and extract year-month
        # Handle both 2-digit and 4-digit year formats (MM/DD/YY and MM/DD/YYYY)
        combined_income['_parsed_date'] = pd.to_datetime(
            combined_income['Transaction Date'],
            format='mixed',
            errors='coerce'
        )
        combined_income['_month'] = combined_income['_parsed_date'].dt.strftime('%Y-%m')
        
        # Group by month and save
        months_saved = 0
        for month, group in combined_income.groupby('_month'):
            if pd.isna(month):
                continue
            
            # Remove temporary columns and Place_Original
            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop)
            
            # Sort by date within month
            output_df = output_df.sort_values('Transaction Date')

            # Restore any user-set labels (overrides auto-classification)
            output_file = reports_dir / f'income_{month}.csv'
            output_df = _restore_user_labels(output_df, output_file)
            # Auto-categorize reimbursements using expense merchant history
            if 'category' not in output_df.columns:
                output_df['category'] = ''
            elif output_df['category'].dtype != object:
                # Can happen when statements/income.csv has a category column with all-NaN
                # values (e.g. written by classify_manual_review), causing pandas to infer float64
                output_df['category'] = output_df['category'].astype(object).fillna('')
            output_df = _categorize_reimbursements(output_df, merchant_cat_map)
            # Restore any user-edited categories (wins over auto-categorization)
            output_df = _restore_user_categories(output_df, output_file, debug=debug)

            # Restore any Investment Return category from existing monthly report
            if output_file.exists():
                try:
                    existing = pd.read_csv(output_file)
                    if 'category' in existing.columns:
                        cat_map = {}
                        for _, row in existing.iterrows():
                            try:
                                key = (str(row.get('Transaction Date','')).strip(),
                                       str(row.get('Place','')).strip().upper(),
                                       round(float(row.get('Amount',0)),2))
                                if str(row.get('category','')).strip():
                                    cat_map[key] = str(row['category']).strip()
                            except Exception:
                                continue
                        if cat_map:
                            if 'category' not in output_df.columns:
                                output_df['category'] = ''
                            for idx, row in output_df.iterrows():
                                try:
                                    key = (str(row.get('Transaction Date','')).strip(),
                                           str(row.get('Place','')).strip().upper(),
                                           round(float(row.get('Amount',0)),2))
                                    if key in cat_map:
                                        output_df.at[idx, 'category'] = cat_map[key]
                                except Exception:
                                    continue
                except Exception:
                    pass

            # Mirror Investment Return rows and investment platform income → transfers (Direction=In)
            is_tagged    = output_df['category'].astype(str).str.strip() == 'Investment Return' if 'category' in output_df.columns else pd.Series(False, index=output_df.index)
            is_platform  = output_df['Place'].astype(str).str.lower().apply(
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

            # Save to monthly_reports
            output_df.to_csv(output_file, index=False)
            months_saved += 1
            
            if debug:
                total_amount = output_df['Amount'].sum() if 'Amount' in output_df.columns else 0
                print(f"  Saved {len(output_df)} income to {output_file.name} (${total_amount:.2f})")
        
        print(f"✓ Saved income for {months_saved} month(s)")
    else:
        print("\n⚠ No income data found")

    # Process investment transfers
    all_transfers = []
    # Include rows promoted from the 'Investment Transfer' category during expense processing
    if category_promoted_transfers:
        all_transfers.extend(category_promoted_transfers)
    # Include income rows marked as Investment Return (Direction=In)
    if income_return_transfers:
        all_transfers.extend(income_return_transfers)
    for month_dir in sorted(statements_dir.glob('*')):
        if not month_dir.is_dir():
            continue
        transfers_file = month_dir / 'transfers.csv'
        if transfers_file.exists():
            try:
                df = pd.read_csv(transfers_file)
                if not df.empty:
                    all_transfers.append(df)
                    if debug:
                        print(f"  Read {len(df)} transfers from {month_dir.name}")
            except Exception as e:
                if debug:
                    print(f"  Warning: Could not read {transfers_file}: {e}")

    if all_transfers:
        combined_transfers = pd.concat(all_transfers, ignore_index=True)
        dedup_cols = [col for col in combined_transfers.columns if col not in ['Source', 'Statement']]
        combined_transfers = combined_transfers.drop_duplicates(subset=dedup_cols, keep='first')

        combined_transfers['_parsed_date'] = pd.to_datetime(
            combined_transfers['Transaction Date'],
            format='mixed',
            errors='coerce'
        )
        combined_transfers['_month'] = combined_transfers['_parsed_date'].dt.strftime('%Y-%m')

        months_saved = 0
        for month, group in combined_transfers.groupby('_month'):
            if pd.isna(month):
                continue
            cols_to_drop = ['_parsed_date', '_month']
            if 'Place_Original' in group.columns:
                cols_to_drop.append('Place_Original')
            output_df = group.drop(columns=cols_to_drop)
            output_df = output_df.sort_values('Transaction Date')
            output_file = reports_dir / f'transfers_{month}.csv'
            output_df.to_csv(output_file, index=False)
            months_saved += 1
            if debug:
                total = output_df['Amount'].sum() if 'Amount' in output_df.columns else 0
                print(f"  Saved {len(output_df)} transfers to {output_file.name} (${total:.2f})")

        print(f"✓ Saved investment transfers for {months_saved} month(s)")
    else:
        if debug:
            print("\n  (No investment transfer data found — re-process statements to capture them)")

    print(f"\n✓ Monthly reports saved to: {reports_dir}")
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
    
    if not statements_dir.exists():
        print(f"Error: Statements directory not found: {statements_dir}")
        sys.exit(1)
    
    # Run aggregation
    aggregate_by_transaction_month(statements_dir, debug=args.debug)


if __name__ == '__main__':
    main()
