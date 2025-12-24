#!/usr/bin/env python3
"""
Manually Add Transaction

Add a manual debt/expense entry to the monthly transactions CSV.

Usage:
    python add_transaction.py --date 11/25/2025 --place "Grocery Store" --amount 45.50
    python add_transaction.py --date 11/25/2025 --place "Grocery Store" --amount 45.50 --statement "Cash"
    python add_transaction.py --month 2025-11  # Interactive mode for specific month
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import re


def get_month_from_date(date_str):
    """Extract YYYY-MM from a date string."""
    try:
        # Parse various date formats
        for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y']:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime('%Y-%m')
            except ValueError:
                continue
        return None
    except:
        return None


def validate_date(date_str):
    """Validate and normalize date format to MM/DD/YYYY."""
    try:
        for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y', '%m/%d', '%m-%d']:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                # If year not provided, use current year
                if fmt in ['%m/%d', '%m-%d']:
                    date_obj = date_obj.replace(year=datetime.now().year)
                return date_obj.strftime('%m/%d/%Y')
            except ValueError:
                continue
        return None
    except:
        return None


def validate_amount(amount_str):
    """Validate and clean amount."""
    try:
        # Remove $ and commas
        clean_amount = amount_str.replace('$', '').replace(',', '').strip()
        amount = float(clean_amount)
        if amount <= 0:
            return None
        return amount
    except:
        return None


def add_transaction_interactive(month_dir):
    """Interactive mode to add transactions."""
    print(f"\n{'='*60}")
    print(f"Add Transaction to {month_dir.name}")
    print(f"{'='*60}\n")
    
    transactions = []
    
    while True:
        print("\nEnter transaction details (or 'done' to finish):")
        
        # Date
        date_input = input("Date (MM/DD/YYYY or MM/DD): ").strip()
        if date_input.lower() == 'done':
            break
        
        date = validate_date(date_input)
        if not date:
            print("❌ Invalid date format. Use MM/DD/YYYY or MM/DD")
            continue
        
        # Place
        place = input("Place/Merchant: ").strip()
        if not place:
            print("❌ Place cannot be empty")
            continue
        
        # Amount
        amount_input = input("Amount ($): ").strip()
        amount = validate_amount(amount_input)
        if amount is None:
            print("❌ Invalid amount. Must be a positive number")
            continue
        
        # Statement/Source (optional)
        statement = input("Statement/Source (optional, default 'Manual'): ").strip()
        if not statement:
            statement = "Manual"
        
        transactions.append({
            'Transaction Date': date,
            'Place': place,
            'Amount': amount,
            'Statement': statement
        })
        
        print(f"✓ Added: {date} | {place} | ${amount:.2f} | {statement}")
    
    return transactions


def add_transaction(month, date, place, amount, statement="Manual"):
    """Add a transaction to the monthly CSV."""
    statements_dir = Path(__file__).parent.parent / 'statements'
    
    # Determine month directory
    if month:
        month_dir = statements_dir / month
    elif date:
        month_str = get_month_from_date(date)
        if not month_str:
            print("❌ Error: Could not determine month from date")
            return False
        month_dir = statements_dir / month_str
    else:
        print("❌ Error: Must provide either --month or --date")
        return False
    
    # Create month directory if it doesn't exist
    month_dir.mkdir(parents=True, exist_ok=True)
    
    csv_file = month_dir / 'transactions.csv'
    
    # Validate inputs
    if date:
        date = validate_date(date)
        if not date:
            print("❌ Error: Invalid date format. Use MM/DD/YYYY")
            return False
    
    if amount is not None:
        amount = validate_amount(str(amount))
        if amount is None:
            print("❌ Error: Invalid amount. Must be a positive number")
            return False
    
    # Check if CSV exists
    if csv_file.exists():
        df = pd.read_csv(csv_file)
    else:
        df = pd.DataFrame(columns=['Transaction Date', 'Place', 'Amount', 'Statement'])
    
    # Add new transaction(s)
    if date and place and amount:
        # Command-line mode: single transaction
        new_row = pd.DataFrame([{
            'Transaction Date': date,
            'Place': place,
            'Amount': amount,
            'Statement': statement
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        print(f"\n✓ Added transaction:")
        print(f"  Date: {date}")
        print(f"  Place: {place}")
        print(f"  Amount: ${amount:.2f}")
        print(f"  Statement: {statement}")
    else:
        # Interactive mode: multiple transactions
        new_transactions = add_transaction_interactive(month_dir)
        if new_transactions:
            new_df = pd.DataFrame(new_transactions)
            df = pd.concat([df, new_df], ignore_index=True)
        else:
            print("\nNo transactions added.")
            return False
    
    # Sort by date
    def parse_date_for_sort(date_str):
        try:
            return pd.to_datetime(date_str, format='%m/%d/%Y', errors='coerce')
        except:
            return pd.NaT
    
    df['_sort_date'] = df['Transaction Date'].apply(parse_date_for_sort)
    df = df.sort_values('_sort_date', na_position='last')
    df = df.drop('_sort_date', axis=1)
    
    # Save
    df.to_csv(csv_file, index=False)
    print(f"\n✓ Saved to {csv_file}")
    print(f"  Total transactions: {len(df)}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Manually add expense transactions to monthly CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add single transaction
  python add_transaction.py --date 11/25/2025 --place "Grocery Store" --amount 45.50
  
  # Add with custom statement source
  python add_transaction.py --date 11/25/2025 --place "Coffee Shop" --amount 5.75 --statement "Cash"
  
  # Interactive mode for a specific month
  python add_transaction.py --month 2025-11
  
  # Interactive mode (will prompt for month)
  python add_transaction.py
        """
    )
    
    parser.add_argument('--month', help='Month directory (YYYY-MM format)')
    parser.add_argument('--date', help='Transaction date (MM/DD/YYYY or MM/DD)')
    parser.add_argument('--place', help='Place/Merchant name')
    parser.add_argument('--amount', type=str, help='Transaction amount')
    parser.add_argument('--statement', default='Manual', help='Statement/Source (default: Manual)')
    
    args = parser.parse_args()
    
    # If no arguments, go interactive
    if not args.month and not args.date:
        print("\nNo arguments provided. Starting interactive mode...")
        month_input = input("Enter month (YYYY-MM): ").strip()
        if month_input:
            args.month = month_input
        else:
            print("❌ Month is required")
            return 1
    
    success = add_transaction(
        month=args.month,
        date=args.date,
        place=args.place,
        amount=args.amount,
        statement=args.statement
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
