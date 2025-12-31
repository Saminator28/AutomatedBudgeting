#!/usr/bin/env python3
"""
Process Monthly Bank Statements

Processes all bank statements organized by month or a specific month.

Usage:
    python process_monthly.py                    # Process all months
    python process_monthly.py --month 2024-11    # Process specific month
    python process_monthly.py --month latest     # Process latest month only
"""

import argparse
import sys
from pathlib import Path
import requests
from datetime import datetime
import pandas as pd
import re
import json
from difflib import get_close_matches

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from bankai.parser.hybrid_parser import HybridPDFParser
from ai_classification.categorizer import TransactionCategorizer


def find_cross_statement_transfers(all_transactions: pd.DataFrame, date_tolerance_days: int = 2) -> pd.DataFrame:
    """
    Find transactions that are likely transfers between accounts by matching amounts.
    
    Args:
        all_transactions: DataFrame with all transactions from all statements
        date_tolerance_days: Days +/- to search for matching amounts
        
    Returns:
        DataFrame of transactions marked as potential transfers
    """
    if all_transactions.empty or 'Source' not in all_transactions.columns:
        return pd.DataFrame()
    
    potential_transfers = []
    
    # Convert dates for comparison
    all_transactions['_parsed_date'] = pd.to_datetime(
        all_transactions['Transaction Date'], 
        format='%m/%d/%Y',
        errors='coerce'
    )
    
    # Group by amount to find potential matches
    for amount in all_transactions['Amount'].unique():
        if pd.isna(amount) or amount <= 0:
            continue
        
        # Find all transactions with this amount
        matching_txns = all_transactions[all_transactions['Amount'] == amount].copy()
        
        if len(matching_txns) < 2:
            continue  # Need at least 2 transactions to be a transfer
        
        # Check if they're from different sources (accounts)
        sources = matching_txns['Source'].unique()
        if len(sources) < 2:
            continue  # Same account, not a cross-account transfer
        
        # Check if dates are close (within tolerance)
        for idx1, row1 in matching_txns.iterrows():
            for idx2, row2 in matching_txns.iterrows():
                if idx1 >= idx2:
                    continue  # Skip same row and duplicates
                
                if row1['Source'] == row2['Source']:
                    continue  # Same source, not a cross-account transfer
                
                date1 = row1['_parsed_date']
                date2 = row2['_parsed_date']
                
                if pd.isna(date1) or pd.isna(date2):
                    continue
                
                # Check if dates are within tolerance
                date_diff = abs((date1 - date2).days)
                if date_diff <= date_tolerance_days:
                    # Found a potential transfer!
                    potential_transfers.append({
                        'amount': amount,
                        'date_diff_days': date_diff,
                        'source1': row1['Source'],
                        'source2': row2['Source'],
                        'date1': row1['Transaction Date'],
                        'date2': row2['Transaction Date'],
                        'place1': row1['Place'],
                        'place2': row2['Place'],
                        'idx1': idx1,
                        'idx2': idx2
                    })
    
    return pd.DataFrame(potential_transfers)


def get_monthly_directories(statements_dir: Path) -> list:
    """Get all monthly directories sorted chronologically."""
    monthly_dirs = []
    
    for item in statements_dir.iterdir():
        if item.is_dir() and item.name.count('-') == 1:
            try:
                # Validate format YYYY-MM
                year, month = item.name.split('-')
                if len(year) == 4 and len(month) == 2:
                    monthly_dirs.append(item)
            except ValueError:
                continue
    
    # Sort chronologically
    monthly_dirs.sort(key=lambda x: x.name)
    return monthly_dirs


def load_valid_categories():
    """Load valid category names from category_patterns.json."""
    config_path = Path(__file__).parent.parent / 'config' / 'category_patterns.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            return list(config.get('categories', {}).keys())
    except Exception as e:
        print(f"⚠ Warning: Could not load categories from config: {e}")
        return []


def add_place_to_category_patterns(place: str, category: str):
    """Add a place name to the category's keyword list in category_patterns.json."""
    config_path = Path(__file__).parent.parent / 'config' / 'category_patterns.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        if 'categories' not in config:
            config['categories'] = {}
        
        if category not in config['categories']:
            config['categories'][category] = []
        
        # Normalize the place name (lowercase, cleaned)
        place_normalized = place.lower().strip()
        
        # Check if already exists (case-insensitive)
        existing_keywords = [k.lower() for k in config['categories'][category]]
        if place_normalized not in existing_keywords:
            config['categories'][category].append(place_normalized)
            
            # Save back to file with pretty formatting
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            return True
        return False
    except Exception as e:
        print(f"  ⚠ Warning: Could not add '{place}' to category '{category}': {e}")
        return False


def validate_and_correct_category(category: str, valid_categories: list, use_llm: bool = False) -> tuple:
    """
    Validate and correct a category name, fixing typos and variations.
    
    Args:
        category: The category to validate/correct
        valid_categories: List of valid category names
        use_llm: Whether to use LLM for ambiguous cases
        
    Returns:
        Tuple of (corrected_category, is_valid)
        - corrected_category: The corrected category name or "Uncategorized"
        - is_valid: True if category was valid/correctable, False if flagged as invalid
    """
    if pd.isna(category) or not category or str(category).strip() == '':
        return "Uncategorized", True
    
    category = str(category).strip()
    
    # Exact match (case-insensitive)
    for valid_cat in valid_categories:
        if category.lower() == valid_cat.lower():
            return valid_cat, True
    
    # If LLM is available, use it as primary with pattern cross-reference
    if use_llm:
        print(f"  [Validating '{category}' with LLM...]")
        llm_result = llm_correct_category(category, valid_categories)
        
        # Also try fuzzy matching for cross-reference
        pattern_matches = get_close_matches(category.lower(), [c.lower() for c in valid_categories], n=1, cutoff=0.7)
        pattern_result = None
        if pattern_matches:
            for valid_cat in valid_categories:
                if valid_cat.lower() == pattern_matches[0]:
                    pattern_result = valid_cat
                    break
        
        # If both agree, high confidence
        if llm_result and pattern_result and llm_result == pattern_result:
            print(f"  [LLM + Pattern] '{category}' → '{llm_result}' ✓✓ (cross-referenced)")
            return llm_result, True
        
        # If LLM succeeded, use it (primary)
        if llm_result:
            if pattern_result and pattern_result != llm_result:
                print(f"  [LLM] '{category}' → '{llm_result}' (pattern suggested: {pattern_result})")
            return llm_result, True
        
        # If pattern matching succeeded but LLM failed
        if pattern_result:
            print(f"  [Pattern fallback] '{category}' → '{pattern_result}'")
            return pattern_result, True
    else:
        # No LLM - use pattern matching only
        matches = get_close_matches(category.lower(), [c.lower() for c in valid_categories], n=1, cutoff=0.7)
        if matches:
            for valid_cat in valid_categories:
                if valid_cat.lower() == matches[0]:
                    print(f"  [Pattern match] '{category}' → '{valid_cat}'")
                    return valid_cat, True
        
        # Invalid category - flag for user to fix
        print(f"  ❌ INVALID CATEGORY: '{category}' does not match any valid category")
        print(f"     Valid categories: {', '.join(valid_categories[:5])}...")
        return category, False
    
    # Last resort: could not map
    print(f"  ⚠ Could not map category '{category}' to valid category - using 'Uncategorized'")
    return "Uncategorized", True


def llm_correct_category(category: str, valid_categories: list) -> str:
    """Use LLM to understand user intent and map to the correct category."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "dolphin-mistral",
                "prompt": f"""A user wrote "{category}" as a transaction category. This may be misspelled, abbreviated, or use different wording.

Your task: Determine which valid category best matches what the user meant.

Valid categories:
{chr(10).join('- ' + cat for cat in valid_categories)}

Think about:
- Common misspellings (e.g., "gifs" → "Gifts & Charity", "restaurnt" → "Dining")
- Abbreviations (e.g., "util" → "Utilities", "groceriesw" → "Groceries")
- Alternative words (e.g., "donation" → "Gifts & Charity", "food" → "Dining", "car" → "Auto Maintenance")
- Partial words or typos

Respond with ONLY the exact category name from the list above. No explanation, no other text.

Best match:""",
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 30
                }
            },
            timeout=30  # Increased timeout for category correction
        )
        
        if response.status_code == 200:
            result = response.json()
            suggested = result.get('response', '').strip()
            
            # Remove any trailing punctuation or extra whitespace
            suggested = suggested.rstrip('.,;:!?').strip()
            
            # Debug: show what LLM returned
            print(f"  [LLM] '{category}' → '{suggested}'", end='')
            
            # Validate that LLM returned an exact match (case-insensitive)
            for valid_cat in valid_categories:
                if suggested.lower().strip() == valid_cat.lower().strip():
                    print(f" ✓")
                    return valid_cat
            
            print(f" ✗ (no match)")
        
    except Exception as e:
        # Log LLM errors for debugging
        print(f"  [LLM Error for '{category}']: {str(e)}")
    
    return None


def process_month(month_dir: Path, parser: HybridPDFParser, use_llm: bool = False, force: bool = False, manual_only: bool = False):
    """Process all PDF statements in a monthly directory.
    
    Args:
        manual_only: If True, only process manual_review.csv without reprocessing PDFs
    """
    
    def parse_date_for_sort(date_str):
        """Parse date string to datetime for sorting."""
        try:
            return pd.to_datetime(date_str, format='%m/%d/%Y', errors='coerce')
        except:
            return pd.NaT
    
    month_name = month_dir.name
    print(f"\n{'='*70}")
    print(f"Processing Month: {month_name}")
    print(f"{'='*70}")
    
    # Load previously classified transactions from manual review BEFORE force cleanup
    manual_review_file = month_dir / 'manual_review.csv'
    previously_classified_income = []
    previously_classified_expenses = []
    valid_categories = load_valid_categories()
    
    if manual_review_file.exists():
        try:
            prev_manual_review = pd.read_csv(manual_review_file)
            if 'Classification' in prev_manual_review.columns:
                # Separate classified from unclassified
                classified = prev_manual_review[prev_manual_review['Classification'].notna()]
                
                if not classified.empty:
                    # Validate and correct categories for classified transactions
                    if 'category' in classified.columns:
                        corrected_categories = []
                        corrections_made = []
                        invalid_categories = []
                        places_added = []
                        
                        for idx, row in classified.iterrows():
                            original_category = row.get('category', 'Uncategorized')
                            place = row.get('Place', 'unknown')
                            is_uncategorized_txn = row.get('_uncategorized', False)
                            # Handle CSV reading - empty string or False means not uncategorized
                            if is_uncategorized_txn == '' or pd.isna(is_uncategorized_txn):
                                is_uncategorized_txn = False
                            else:
                                is_uncategorized_txn = bool(is_uncategorized_txn)
                            
                            corrected_category, is_valid = validate_and_correct_category(
                                original_category, 
                                valid_categories, 
                                use_llm=use_llm
                            )
                            
                            # Track invalid categories for user to fix
                            if not is_valid:
                                invalid_categories.append({
                                    'place': place,
                                    'invalid_category': original_category
                                })
                            
                            # Track if category was corrected
                            if str(original_category).strip() != '' and corrected_category != original_category:
                                corrections_made.append({
                                    'place': place,
                                    'original': original_category,
                                    'corrected': corrected_category
                                })
                            
                            # Add to patterns ONLY if it was an uncategorized transaction (not payment app)
                            # Payment apps need manual review every time
                            if is_uncategorized_txn and is_valid and corrected_category != 'Uncategorized':
                                if add_place_to_category_patterns(place, corrected_category):
                                    places_added.append({'place': place, 'category': corrected_category})
                            
                            corrected_categories.append(corrected_category)
                        
                        # Update the category column with corrected values
                        classified = classified.copy()
                        classified['category'] = corrected_categories
                        
                        # Mark these as manually categorized to prevent re-categorization
                        classified['_manual_category'] = True
                        
                        # Drop the marker column before saving
                        classified = classified.drop('_uncategorized', axis=1, errors='ignore')
                        
                        # Log corrections
                        if corrections_made:
                            print(f"\n📝 Category Corrections:")
                            for correction in corrections_made:
                                print(f"  ✓ '{correction['original']}' → '{correction['corrected']}' ({correction['place']})")
                        
                        # Warn about invalid categories
                        if invalid_categories:
                            print(f"\n❌ INVALID CATEGORIES FOUND - Please fix these in manual_review.csv:")
                            for invalid in invalid_categories:
                                print(f"  ✗ '{invalid['invalid_category']}' for '{invalid['place']}'")
                        
                        # Log places added to patterns
                        if places_added:
                            print(f"\n📚 Added {len(places_added)} place(s) to category_patterns.json:")
                            for item in places_added[:5]:  # Show first 5
                                print(f"  + '{item['place']}' → {item['category']}")
                            if len(places_added) > 5:
                                print(f"  ... and {len(places_added) - 5} more")
                    
                    # Split by classification
                    income_classified = classified[classified['Classification'].str.upper() == 'INCOME']
                    expense_classified = classified[classified['Classification'].str.upper() == 'EXPENSE']
                    
                    if not income_classified.empty:
                        previously_classified_income = income_classified.to_dict('records')
                        print(f"📥 Found {len(previously_classified_income)} transaction(s) classified as INCOME")
                    
                    if not expense_classified.empty:
                        previously_classified_expenses = expense_classified.to_dict('records')
                        print(f"📥 Found {len(previously_classified_expenses)} transaction(s) classified as EXPENSE")
        except Exception as e:
            print(f"⚠ Warning: Could not read previous manual_review.csv: {e}")
    
    # If manual-only mode, just update the files and return
    if manual_only:
        has_work = False
        
        # Load existing expenses and income files
        output_file = month_dir / "expenses.csv"
        income_file = month_dir / 'income.csv'
        
        expenses_df = pd.DataFrame()
        income_df = pd.DataFrame()
        
        if output_file.exists():
            expenses_df = pd.read_csv(output_file)
        if income_file.exists():
            income_df = pd.read_csv(income_file)
        
        # Process manual_transactions.csv if it exists
        manual_file = month_dir / 'manual_transactions.csv'
        if manual_file.exists():
            has_work = True
            try:
                # Extract expected year and month from directory name
                expected_year, expected_month = map(int, month_dir.name.split('-'))
                
                # Read manual transactions, filter out comments
                with open(manual_file, 'r') as f:
                    lines = [line for line in f if not line.strip().startswith('#')]
                
                if len(lines) > 1:  # More than just header
                    from io import StringIO
                    manual_df = pd.read_csv(StringIO(''.join(lines)))
                    
                    if not manual_df.empty:
                        # Normalize dates in manual entries
                        def normalize_manual_date(date_str):
                            if pd.isna(date_str):
                                return None
                            date_str = str(date_str).strip()
                            try:
                                for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%m/%d/%y', '%m-%d-%y', '%m/%d', '%m-%d']:
                                    try:
                                        from datetime import datetime as dt
                                        date_obj = dt.strptime(date_str, fmt)
                                        if fmt in ['%m/%d', '%m-%d']:
                                            date_obj = date_obj.replace(year=dt.now().year)
                                        return date_obj.strftime('%m/%d/%Y')
                                    except ValueError:
                                        continue
                            except:
                                pass
                            return None
                        
                        original_count = len(manual_df)
                        manual_df['Transaction Date'] = manual_df['Transaction Date'].apply(normalize_manual_date)
                        manual_df = manual_df[manual_df['Transaction Date'].notna()]
                        
                        # Validate dates are in correct month
                        wrong_month_indices = []
                        for idx, date_str in enumerate(manual_df['Transaction Date']):
                            if pd.notna(date_str):
                                try:
                                    from datetime import datetime as dt
                                    date_obj = dt.strptime(date_str, '%m/%d/%Y')
                                    if date_obj.year != expected_year or date_obj.month != expected_month:
                                        wrong_month_indices.append(idx)
                                except:
                                    pass
                        
                        if wrong_month_indices:
                            print(f"  ⚠ Skipped {len(wrong_month_indices)} manual transaction(s) with dates outside {month_dir.name}")
                            manual_df = manual_df.drop(manual_df.index[wrong_month_indices])
                        
                        if not manual_df.empty:
                            # Validate and correct categories for manual transactions
                            if 'category' in manual_df.columns:
                                corrected_categories = []
                                corrections_made = []
                                invalid_categories = []
                                places_added = []
                                
                                for idx, row in manual_df.iterrows():
                                    original_category = row.get('category', 'Uncategorized')
                                    place = row.get('Place', 'unknown')
                                    
                                    corrected_category, is_valid = validate_and_correct_category(
                                        original_category, 
                                        valid_categories, 
                                        use_llm=use_llm
                                    )
                                    
                                    # Track invalid categories for user to fix
                                    if not is_valid:
                                        invalid_categories.append({
                                            'place': place,
                                            'invalid_category': original_category
                                        })
                                    
                                    # Track if category was corrected
                                    if str(original_category).strip() != '' and corrected_category != original_category:
                                        corrections_made.append({
                                            'place': place,
                                            'original': original_category,
                                            'corrected': corrected_category
                                        })
                                    
                                    # Add place to category patterns if valid
                                    if is_valid and corrected_category != 'Uncategorized':
                                        if add_place_to_category_patterns(place, corrected_category):
                                            places_added.append({'place': place, 'category': corrected_category})
                                    
                                    corrected_categories.append(corrected_category)
                                
                                # Update the category column with corrected values
                                manual_df = manual_df.copy()
                                manual_df['category'] = corrected_categories
                                
                                # Log corrections
                                if corrections_made:
                                    print(f"\n📝 Manual Transaction Category Corrections:")
                                    for correction in corrections_made:
                                        print(f"  ✓ '{correction['original']}' → '{correction['corrected']}' ({correction['place']})")
                                
                                # Warn about invalid categories
                                if invalid_categories:
                                    print(f"\n❌ INVALID CATEGORIES FOUND - Please fix these in manual_transactions.csv:")
                                    for invalid in invalid_categories:
                                        print(f"  ✗ '{invalid['invalid_category']}' for '{invalid['place']}'")
                                
                                # Log places added to patterns
                                if places_added:
                                    print(f"\n📚 Added {len(places_added)} place(s) to category_patterns.json:")
                                    for item in places_added[:5]:  # Show first 5
                                        print(f"  + '{item['place']}' → {item['category']}")
                                    if len(places_added) > 5:
                                        print(f"  ... and {len(places_added) - 5} more")
                            
                            # Merge manual transactions with expenses
                            if not expenses_df.empty:
                                expenses_df = pd.concat([expenses_df, manual_df], ignore_index=True)
                            else:
                                expenses_df = manual_df
                            
                            # Sort by date
                            expenses_df['_sort_date'] = pd.to_datetime(expenses_df['Transaction Date'], format='%m/%d/%Y', errors='coerce')
                            expenses_df = expenses_df.sort_values('_sort_date', na_position='last')
                            expenses_df = expenses_df.drop('_sort_date', axis=1)
                            
                            print(f"\n✓ Merged {len(manual_df)} manual transaction(s) from manual_transactions.csv")
            except Exception as e:
                print(f"  ⚠ Warning: Could not import manual transactions: {e}")
        
        # Process manual_review.csv classified transactions
        if previously_classified_income or previously_classified_expenses:
            has_work = True
        
        # Add classified transactions from manual_review.csv
        if previously_classified_expenses:
            prev_exp_df = pd.DataFrame(previously_classified_expenses)
            prev_exp_df = prev_exp_df.drop(['Classification', 'Type', '_manual_category'], axis=1, errors='ignore')
            if not expenses_df.empty:
                expenses_df = pd.concat([expenses_df, prev_exp_df], ignore_index=True)
            else:
                expenses_df = prev_exp_df
            
            # Sort by date
            expenses_df['_sort_date'] = pd.to_datetime(expenses_df['Transaction Date'], format='%m/%d/%Y', errors='coerce')
            expenses_df = expenses_df.sort_values('_sort_date', na_position='last')
            expenses_df = expenses_df.drop('_sort_date', axis=1)
            
            expenses_df.to_csv(output_file, index=False)
        
        if previously_classified_income:
            prev_inc_df = pd.DataFrame(previously_classified_income)
            prev_inc_df = prev_inc_df.drop(['Classification', 'Type', '_manual_category'], axis=1, errors='ignore')
            if not income_df.empty:
                income_df = pd.concat([income_df, prev_inc_df], ignore_index=True)
            else:
                income_df = prev_inc_df
            
            # Sort by date
            income_df['_sort_date'] = pd.to_datetime(income_df['Transaction Date'], format='%m/%d/%Y', errors='coerce')
            income_df = income_df.sort_values('_sort_date', na_position='last')
            income_df = income_df.drop('_sort_date', axis=1)
            
            income_df.to_csv(income_file, index=False)
        
        # Update manual_review.csv to remove classified transactions
        if manual_review_file.exists():
            try:
                manual_review_df = pd.read_csv(manual_review_file)
                # Keep only unclassified transactions
                unclassified = manual_review_df[(manual_review_df['Classification'].isna()) | 
                                               (manual_review_df['Classification'] == '')]
                if not unclassified.empty:
                    unclassified.to_csv(manual_review_file, index=False)
                    print(f"✓ {len(unclassified)} unclassified transaction(s) remain in manual_review.csv")
                else:
                    # All classified - remove the file
                    manual_review_file.unlink()
                    print(f"✓ All transactions classified - removed manual_review.csv")
            except Exception as e:
                print(f"⚠ Warning: Could not update manual_review.csv: {e}")
        
        # Check if any work was done
        if not has_work:
            print(f"✓ No manual transactions or classified items to process")
            return True
        
        # Save updated files
        if not expenses_df.empty:
            expenses_df.to_csv(output_file, index=False)
            print(f"✓ Updated expenses.csv with {len(expenses_df)} transaction(s)")
        
        if not income_df.empty:
            income_df.to_csv(income_file, index=False)
            print(f"✓ Updated income.csv with {len(income_df)} transaction(s)")
        
        # Summary
        if previously_classified_income or previously_classified_expenses:
            total_moved = len(previously_classified_income) + len(previously_classified_expenses)
            print(f"\n✓ Moved {total_moved} manually classified transaction(s):")
            if previously_classified_income:
                print(f"  - {len(previously_classified_income)} to income.csv")
            if previously_classified_expenses:
                print(f"  - {len(previously_classified_expenses)} to expenses.csv")
        
        return True
    
    # Check if expenses.csv already exists
    output_file = month_dir / "expenses.csv"
    if output_file.exists() and not force:
        print(f"✓ expenses.csv already exists - skipping")
        print(f"  (use --force to reprocess)")
        return True
    
    # If forcing reprocess, remove all generated CSVs
    if force:
        files_to_remove = []
        
        # Remove main output files
        if output_file.exists():
            files_to_remove.append(("expenses.csv", output_file))
        
        income_file = month_dir / 'income.csv'
        if income_file.exists():
            files_to_remove.append(("income.csv", income_file))
        
        manual_review_file = month_dir / 'manual_review.csv'
        if manual_review_file.exists():
            files_to_remove.append(("manual_review.csv", manual_review_file))
        
        # Remove all rejected CSVs from previous processing
        rejected_files = list(month_dir.glob("*_rejected.csv"))
        for rejected_file in rejected_files:
            files_to_remove.append((rejected_file.name, rejected_file))
        
        if files_to_remove:
            for file_name, file_path in files_to_remove:
                file_path.unlink()
            print(f"🗑️  Removed {len(files_to_remove)} existing file(s) (expenses, income, manual_review, rejected)")
    
    # Find all PDF files in the directory
    pdf_files = sorted(list(month_dir.glob("*.pdf")))
    
    if not pdf_files:
        print(f"⚠ No PDF files found in {month_name}")
        return False
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    
    # Process each PDF and collect all transactions
    all_month_transactions = []
    
    for pdf_file in pdf_files:
        print(f"\nProcessing: {pdf_file.name}")
        print("-" * 70)
        
        try:
            # Use hybrid parser - returns (income_df, expenses_df, bank_name, is_bank_account)
            income_df, expenses_df, bank_name, is_bank_account = parser.parse_pdf(pdf_file)
            
            # Combine income and expenses into single df for compatibility with old code
            df_list = []
            if not income_df.empty:
                income_df['Type'] = 'Income'
                df_list.append(income_df)
            if not expenses_df.empty:
                expenses_df['Type'] = 'Expense'
                df_list.append(expenses_df)
            
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
                df['_is_bank_account'] = is_bank_account
                df['Statement'] = bank_name
                all_month_transactions.append(df)
                
                account_type = "bank account" if is_bank_account else "credit card"
                print(f"✅ Extracted {len(df)} transactions from {bank_name} ({account_type})")
                print(f"   {len(income_df)} income, {len(expenses_df)} expenses")
            else:
                print(f"⚠ No transactions found in {pdf_file.name}")
            
        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {str(e)}")
            continue
    
    # Combine all transactions from all PDFs
    if all_month_transactions:
        combined_df = pd.concat(all_month_transactions, ignore_index=True)
        
        # Normalize date formats to MM/DD/YYYY
        def normalize_date(date_str):
            """Normalize various date formats to MM/DD/YYYY."""
            if pd.isna(date_str):
                return date_str
            
            date_str = str(date_str).strip()
            
            # Fix malformed dates like "41/03/2025" -> "11/03/2025"
            if date_str.startswith('4'):
                date_str = '1' + date_str[1:]
            
            # Handle MM-DD format (from credit cards)
            if '-' in date_str and '/' not in date_str:
                parts = date_str.split('-')
                if len(parts) == 2:
                    return f"{parts[0]}/{parts[1]}/2025"
            
            # Handle MM/DD/YYYY format (already correct)
            if '/' in date_str and len(date_str.split('/')) == 3:
                return date_str
            
            # Handle MM/DD format
            if '/' in date_str and len(date_str.split('/')) == 2:
                return f"{date_str}/2025"
            
            return date_str
        
        combined_df['Transaction Date'] = combined_df['Transaction Date'].apply(normalize_date)
        
        # Clean up place names further
        def clean_place(place):
            """Additional cleaning for place names."""
            if pd.isna(place):
                return place
            
            place = str(place)
            
            # Remove dates in format MM/DD/YY or MM/DD/YYYY from descriptions
            place = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}\b', '', place)
            
            # Remove trailing " At" or "At" patterns
            place = re.sub(r'\s+At\s*$', '', place, flags=re.IGNORECASE)
            
            # Remove reference numbers at the end (alphanumeric strings like A1132850D)
            place = re.sub(r'\s+[A-Z0-9]{8,}\s*$', '', place)
            
            # Remove "External F" or similar patterns
            place = re.sub(r'\s+External\s+[A-Z]\s+', ' ', place, flags=re.IGNORECASE)
            
            # Remove long alphanumeric codes (payment references like 3D08D350E05969)
            place = re.sub(r'\s+[0-9A-Z]{10,}', '', place)
            
            # Remove "Web_Pay" suffix
            place = re.sub(r'\s+Web_Pay.*$', '', place, flags=re.IGNORECASE)
            
            # Remove "Online Pmt" or "Payments" with trailing codes
            place = re.sub(r'\s+(Online Pmt|Payments).*$', '', place, flags=re.IGNORECASE)
            
            # Remove "WEB PMTS" and trailing codes
            place = re.sub(r'\s+WEB PMTS.*$', '', place, flags=re.IGNORECASE)
            
            # Clean up account masks (XXXXXX followed by digits)
            place = re.sub(r'XXXXXX\d+', '', place)
            place = re.sub(r'Xxxxxx\d+', '', place)
            
            # Remove "To" prefix for transfers
            place = re.sub(r'^(Online-Phone Transfer To|ONLINE-PHONE TRANSFER TO)\s+', '', place, flags=re.IGNORECASE)
            
            # Clean up extra spaces
            place = re.sub(r'\s+', ' ', place).strip()
            
            # Generic pattern-based standardization
            place_upper = place.upper()
            
            # Credit card payments - make generic
            if 'BANKCARD' in place_upper or 'BANK CARD' in place_upper or 'CARD CTR' in place_upper:
                if 'ONLINE' in place_upper or 'PMT' in place_upper or 'PAYMENT' in place_upper:
                    return 'Credit Card Payment'
            
            # Auto loans/financing - keep company name but clean
            if 'AUTO FINANCE' in place_upper or 'AUTO LOAN' in place_upper:
                # Extract company name (first word(s) before AUTO)
                match = re.match(r'^([\w\s]+?)\s+(AUTO|CAR)\s+(FINANCE|LOAN|FINANCING)', place, re.IGNORECASE)
                if match:
                    company = match.group(1).strip().title()
                    return f"{company} Auto Loan"
            
            # Generic loan payments
            if re.search(r'\bLOAN\s+PYMT\b|\bLOAN\s+PAYMENT\b', place_upper):
                # Extract company name
                match = re.match(r'^([\w\s]+?)\s+LOAN', place, re.IGNORECASE)
                if match:
                    company = match.group(1).strip().title()
                    return f"{company} Loan Payment"
            
            # Clean up common financial institution patterns
            place = re.sub(r'\b(Financia|Financial)\b', 'Financial', place, flags=re.IGNORECASE)
            
            return place
        
        combined_df['Place'] = combined_df['Place'].apply(clean_place)
        
        # Remove transactions with empty/null place names
        combined_df = combined_df[combined_df['Place'].notna() & (combined_df['Place'].str.strip() != '')]
        
        # Parse dates for sorting
        def parse_date(date_str):
            """Try to parse date string to datetime for sorting."""
            try:
                return pd.to_datetime(date_str, format='%m/%d/%Y', errors='coerce')
            except:
                return pd.NaT
        
        combined_df['_sort_date'] = combined_df['Transaction Date'].apply(parse_date)
        
        # Sort by date
        combined_df = combined_df.sort_values('_sort_date', na_position='last')
        
        # Remove temporary sort column
        combined_df = combined_df.drop('_sort_date', axis=1)
        
        # Filter to only show expenses (debits/money spent)
        # Remove Beginning Balance, Ending Balance, Interest, transfers in, etc.
        if 'Place' in combined_df.columns:
            combined_df = combined_df[
                ~combined_df['Place'].str.contains(
                    'Beginning Balance|Ending Balance|Interest|ONE TRANSFER FROM|TRANSFER FROM|Payment Thank|Online Payment',
                    case=False, na=False, regex=True
                )
            ]
        
        # Drop Balance column - we only care about money spent
        if 'Balance' in combined_df.columns:
            combined_df = combined_df.drop('Balance', axis=1)
        
        # Split into three DataFrames: expenses, income, and payment apps
        # The hybrid parser already separated them, but we need to handle payment apps
        
        expenses_df = pd.DataFrame()
        income_df = pd.DataFrame()
        payment_apps_df = pd.DataFrame()
        
        # Load payment app keywords
        payment_app_keywords = ['VENMO', 'ZELLE', 'CASH APP', 'CASHAPP', 'APPLE PAY', 'PAYPAL']
        
        # Separate expenses and income from combined_df based on Type column
        expenses_rows = combined_df[combined_df['Type'] == 'Expense'].copy() if 'Type' in combined_df.columns else combined_df.copy()
        income_rows = combined_df[combined_df['Type'] == 'Income'].copy() if 'Type' in combined_df.columns else pd.DataFrame()
        
        # Check for payment apps in expenses
        if not expenses_rows.empty:
            payment_mask = expenses_rows['Place'].str.upper().str.contains(
                '|'.join(payment_app_keywords), na=False, regex=True
            )
            payment_apps_df = expenses_rows[payment_mask].copy()
            expenses_df = expenses_rows[~payment_mask].copy()
        
        if not income_rows.empty:
            income_df = income_rows.copy()
        
        # Drop Type column as it was only for internal use
        expenses_df = expenses_df.drop('Type', axis=1, errors='ignore')
        income_df = income_df.drop('Type', axis=1, errors='ignore')
        payment_apps_df = payment_apps_df.drop('Type', axis=1, errors='ignore')
        
        # Add previously classified expenses
        if previously_classified_expenses:
            prev_exp_df = pd.DataFrame(previously_classified_expenses)
            prev_exp_df = prev_exp_df.drop(['Classification', 'Type', '_manual_category'], axis=1, errors='ignore')
            if not expenses_df.empty:
                expenses_df = pd.concat([expenses_df, prev_exp_df], ignore_index=True)
            else:
                expenses_df = prev_exp_df
        
        # Add previously classified income
        if previously_classified_income:
            prev_inc_df = pd.DataFrame(previously_classified_income)
            prev_inc_df = prev_inc_df.drop(['Classification', 'Type', '_manual_category'], axis=1, errors='ignore')
            if not income_df.empty:
                income_df = pd.concat([income_df, prev_inc_df], ignore_index=True)
            else:
                income_df = prev_inc_df
        
        # Add Classification column for payment apps
        if not payment_apps_df.empty:
            if 'Classification' not in payment_apps_df.columns:
                payment_apps_df['Classification'] = ''
        
        # Add any unclassified transactions from previous manual_review.csv
        if manual_review_file.exists():
            try:
                prev_manual_review = pd.read_csv(manual_review_file)
                if 'Classification' in prev_manual_review.columns:
                    # Keep only unclassified transactions
                    unclassified = prev_manual_review[(prev_manual_review['Classification'].isna()) | 
                                                     (prev_manual_review['Classification'] == '')]
                    if not unclassified.empty:
                        if not payment_apps_df.empty:
                            payment_apps_df = pd.concat([payment_apps_df, unclassified], ignore_index=True)
                        else:
                            payment_apps_df = unclassified
            except Exception as e:
                pass  # Silently continue if can't read previous file
        
        # Filter out rows with no amount (shouldn't happen, but safety check)
        if not expenses_df.empty and 'Amount' in expenses_df.columns:
            expenses_df = expenses_df[expenses_df['Amount'].notna()]
        if not income_df.empty and 'Amount' in income_df.columns:
            income_df = income_df[income_df['Amount'].notna()]
        if not payment_apps_df.empty and 'Amount' in payment_apps_df.columns:
            payment_apps_df = payment_apps_df[payment_apps_df['Amount'].notna()]
        
        # Use expenses_df as the main combined_df for the rest of processing
        combined_df = expenses_df
        
        # Add Source column (use Statement column for cross-referencing)
        if 'Statement' in combined_df.columns:
            combined_df['Source'] = combined_df['Statement']
        
        # Cross-reference amounts to find inter-account transfers
        print(f"\n{'='*70}")
        print("Cross-referencing transactions for inter-account transfers...")
        potential_transfers = find_cross_statement_transfers(combined_df, date_tolerance_days=2)
        
        if not potential_transfers.empty:
            print(f"  ✓ Found {len(potential_transfers)} potential inter-account transfer pair(s):")
            matched_pairs = set()
            for _, transfer in potential_transfers.iterrows():
                # Only remove if both sides of the transfer are present
                idx1 = transfer['idx1']
                idx2 = transfer['idx2']
                # Ensure both indices are valid and not already matched
                if idx1 not in matched_pairs and idx2 not in matched_pairs:
                    matched_pairs.add(idx1)
                    matched_pairs.add(idx2)
                    print(f"    - ${transfer['amount']:.2f}: {transfer['source1']} ({transfer['date1']}) ↔ {transfer['source2']} ({transfer['date2']}) [{transfer['date_diff_days']} day(s) apart]")
                    print(f"      • {transfer['place1']} ↔ {transfer['place2']}")
            # Remove only matched transfer pairs
            if matched_pairs:
                original_count = len(combined_df)
                combined_df = combined_df.drop(list(matched_pairs))
                combined_df = combined_df.reset_index(drop=True)
                print(f"  ✓ Removed {original_count - len(combined_df)} cross-account transfer transaction(s)")
        else:
            print(f"  ✓ No cross-account transfers detected")
        print(f"{'='*70}")
        
        # Remove temporary columns
        combined_df = combined_df.drop('Source', axis=1, errors='ignore')
        combined_df = combined_df.drop('_parsed_date', axis=1, errors='ignore')
        
        # Final column order: Date, Place, Amount, Statement
        ordered_cols = ['Transaction Date', 'Place', 'Amount', 'Statement']
        # Keep only columns that exist
        ordered_cols = [col for col in ordered_cols if col in combined_df.columns]
        # Add any other columns not yet included
        other_cols = [col for col in combined_df.columns if col not in ordered_cols]
        combined_df = combined_df[ordered_cols + other_cols]
                # Check for manual transactions and merge them in
        manual_file = month_dir / 'manual_transactions.csv'
        if manual_file.exists():
            try:
                # Extract expected year and month from directory name
                expected_year, expected_month = map(int, month_dir.name.split('-'))
                
                # Read manual transactions, filter out comments
                with open(manual_file, 'r') as f:
                    lines = [line for line in f if not line.strip().startswith('#')]
                
                if len(lines) > 1:  # More than just header
                    from io import StringIO
                    manual_df = pd.read_csv(StringIO(''.join(lines)))
                    
                    if not manual_df.empty:
                        # Normalize dates in manual entries
                        def normalize_manual_date(date_str):
                            if pd.isna(date_str):
                                return None
                            date_str = str(date_str).strip()
                            try:
                                for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%m/%d/%y', '%m-%d-%y', '%m/%d', '%m-%d']:
                                    try:
                                        from datetime import datetime as dt
                                        date_obj = dt.strptime(date_str, fmt)
                                        if fmt in ['%m/%d', '%m-%d']:
                                            date_obj = date_obj.replace(year=dt.now().year)
                                        return date_obj.strftime('%m/%d/%Y')
                                    except ValueError:
                                        continue
                            except:
                                pass
                            return None
                        
                        original_count = len(manual_df)
                        manual_df['Transaction Date'] = manual_df['Transaction Date'].apply(normalize_manual_date)
                        manual_df = manual_df[manual_df['Transaction Date'].notna()]
                        
                        # Validate dates are in correct month
                        wrong_month_indices = []
                        for idx, date_str in enumerate(manual_df['Transaction Date']):
                            if pd.notna(date_str):
                                try:
                                    from datetime import datetime as dt
                                    date_obj = dt.strptime(date_str, '%m/%d/%Y')
                                    if date_obj.year != expected_year or date_obj.month != expected_month:
                                        wrong_month_indices.append(idx)
                                except:
                                    pass
                        
                        if wrong_month_indices:
                            print(f"  ⚠ Skipped {len(wrong_month_indices)} manual transaction(s) with dates outside {month_dir.name}")
                            manual_df = manual_df.drop(manual_df.index[wrong_month_indices])
                        
                        if not manual_df.empty:
                            # Validate and correct categories for manual transactions
                            if 'category' in manual_df.columns:
                                corrected_categories = []
                                corrections_made = []
                                invalid_categories = []
                                places_added = []
                                
                                for idx, row in manual_df.iterrows():
                                    original_category = row.get('category', 'Uncategorized')
                                    place = row.get('Place', 'unknown')
                                    
                                    corrected_category, is_valid = validate_and_correct_category(
                                        original_category, 
                                        valid_categories, 
                                        use_llm=use_llm
                                    )
                                    
                                    # Track invalid categories for user to fix
                                    if not is_valid:
                                        invalid_categories.append({
                                            'place': place,
                                            'invalid_category': original_category
                                        })
                                    
                                    # Track if category was corrected
                                    if str(original_category).strip() != '' and corrected_category != original_category:
                                        corrections_made.append({
                                            'place': place,
                                            'original': original_category,
                                            'corrected': corrected_category
                                        })
                                    
                                    # Add place to category patterns if valid
                                    if is_valid and corrected_category != 'Uncategorized':
                                        if add_place_to_category_patterns(place, corrected_category):
                                            places_added.append({'place': place, 'category': corrected_category})
                                    
                                    corrected_categories.append(corrected_category)
                                
                                # Update the category column with corrected values
                                manual_df = manual_df.copy()
                                manual_df['category'] = corrected_categories
                                
                                # Mark these as manually categorized to preserve their categories
                                manual_df['_manual_category'] = True
                                
                                # Log corrections
                                if corrections_made:
                                    print(f"\n📝 Manual Transaction Category Corrections:")
                                    for correction in corrections_made:
                                        print(f"  ✓ '{correction['original']}' → '{correction['corrected']}' ({correction['place']})")
                                
                                # Warn about invalid categories
                                if invalid_categories:
                                    print(f"\n❌ INVALID CATEGORIES FOUND - Please fix these in manual_transactions.csv:")
                                    for invalid in invalid_categories:
                                        print(f"  ✗ '{invalid['invalid_category']}' for '{invalid['place']}'")
                                
                                # Log places added to patterns
                                if places_added:
                                    print(f"\n📚 Added {len(places_added)} place(s) to category_patterns.json:")
                                    for item in places_added[:5]:  # Show first 5
                                        print(f"  + '{item['place']}' → {item['category']}")
                                    if len(places_added) > 5:
                                        print(f"  ... and {len(places_added) - 5} more")
                            
                            # Merge manual transactions
                            combined_df = pd.concat([combined_df, manual_df], ignore_index=True)
                            
                            # Re-sort by date
                            combined_df['_sort_date'] = combined_df['Transaction Date'].apply(parse_date_for_sort)
                            combined_df = combined_df.sort_values('_sort_date', na_position='last')
                            combined_df = combined_df.drop('_sort_date', axis=1)
                            
                            print(f"  ✓ Merged {len(manual_df)} manual transaction(s)")
            except Exception as e:
                print(f"  ⚠ Warning: Could not import manual transactions: {e}")
        
        # Categorize expenses (always enabled)
        print(f"\n{'='*70}")
        print("Categorizing expenses...")
        categorizer = TransactionCategorizer(use_llm=use_llm)
        
        # Separate manually categorized transactions to preserve their categories
        manual_expenses = combined_df[combined_df.get('_manual_category', False) == True].copy() if '_manual_category' in combined_df.columns else pd.DataFrame()
        auto_expenses = combined_df[combined_df.get('_manual_category', False) != True] if '_manual_category' in combined_df.columns else combined_df
        
        # Categorize only the auto expenses
        auto_expenses = categorizer.categorize_dataframe(
            auto_expenses,
            description_column='Place',
            amount_column='Amount'
        )
        
        # Merge back manually categorized transactions
        if not manual_expenses.empty:
            combined_df = pd.concat([auto_expenses, manual_expenses], ignore_index=True)
            # Drop the flag column
            combined_df = combined_df.drop('_manual_category', axis=1, errors='ignore')
        else:
            combined_df = auto_expenses
        
        # Print report
        categorizer.print_categorization_report(
            combined_df,
            merchant_column='Place',
            month=month_dir.name
        )
        
        
        # Categorize manual review transactions if we have any
        if not payment_apps_df.empty:
            print(f"\nCategorizing manual review transactions...")
            payment_apps_df = categorizer.categorize_dataframe(
                payment_apps_df,
                description_column='Place',
                amount_column='Amount'
            )
            print(f"✓ Categorized {len(payment_apps_df)} manual review transaction(s)")
        
        # Extract uncategorized transactions from expenses and add to manual review
        if 'category' in combined_df.columns:
            uncategorized_expenses = combined_df[combined_df['category'] == 'Uncategorized'].copy()
            if not uncategorized_expenses.empty:
                # Remove uncategorized from expenses
                combined_df = combined_df[combined_df['category'] != 'Uncategorized']
                
                # Add Classification column if not present
                if 'Classification' not in uncategorized_expenses.columns:
                    uncategorized_expenses['Classification'] = ''
                
                # Mark as uncategorized (not payment app) so we can add to patterns later
                uncategorized_expenses['_uncategorized'] = True
                
                # Merge with payment apps for manual review
                if not payment_apps_df.empty:
                    payment_apps_df = pd.concat([payment_apps_df, uncategorized_expenses], ignore_index=True)
                else:
                    payment_apps_df = uncategorized_expenses
                
                print(f"\n📋 Added {len(uncategorized_expenses)} uncategorized expense(s) to manual review")
        
        
        # Save combined results
        print(f"\n{'='*70}")
        print(f"Combining transactions from {len(pdf_files)} statement(s)")
        
        # Save expenses
        combined_df.to_csv(output_file, index=False)
        print(f"✓ Saved {len(combined_df)} expense(s) to {output_file}")
        
        # Save income
        if not income_df.empty:
            income_file = month_dir / 'income.csv'
            
            # Sort by date
            income_df['_sort_date'] = pd.to_datetime(income_df['Transaction Date'], format='%m/%d/%Y', errors='coerce')
            income_df = income_df.sort_values('_sort_date', na_position='last')
            income_df = income_df.drop('_sort_date', axis=1)
            
            income_df.to_csv(income_file, index=False)
            print(f"✓ Saved {len(income_df)} income transaction(s) to {income_file}")
        
        # Save manual review transactions (payment apps + uncategorized)
        if not payment_apps_df.empty:
            manual_review_file = month_dir / 'manual_review.csv'
            payment_apps_df.to_csv(manual_review_file, index=False)
            print(f"✓ Saved {len(payment_apps_df)} transaction(s) to {manual_review_file} for manual review")
            print(f"  ℹ  To classify: Edit manual_review.csv and set Classification to 'Income' or 'Expense'")
            print(f"  ℹ  Next run will automatically move classified transactions to the correct file")
        else:
            print(f"  (No transactions require manual review)")
        
        # Report on previously classified transactions
        if previously_classified_income or previously_classified_expenses:
            total_moved = len(previously_classified_income) + len(previously_classified_expenses)
            print(f"\n✓ Moved {total_moved} manually classified transaction(s):")
            if previously_classified_income:
                print(f"  - {len(previously_classified_income)} to income.csv")
            if previously_classified_expenses:
                print(f"  - {len(previously_classified_expenses)} to expenses.csv")
        
        print(f"{'='*70}")
        
        return True
    else:
        print(f"\n❌ No transactions extracted from any PDFs in {month_name}")
        return False


def check_llm_availability(host="http://localhost:11434"):
    """Check if Ollama LLM is available."""
    try:
        response = requests.get(f"{host}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def main():
    """Main function."""
    parser_args = argparse.ArgumentParser(
        description='Process bank statements organized by month. By default, processes all months that don\'t have transactions.csv'
    )
    parser_args.add_argument(
        '--month',
        type=str,
        help='Process specific month only (YYYY-MM format or "latest")'
    )
    parser_args.add_argument(
        '--statements-dir',
        type=str,
        default='statements',
        help='Directory containing monthly folders (default: statements)'
    )
    parser_args.add_argument(
        '--force',
        action='store_true',
        default=True,
        help='Force reprocessing even if CSV already exists (default: enabled)'
    )
    parser_args.add_argument(
        '--no-force',
        action='store_false',
        dest='force',
        help='Skip processing if CSV already exists'
    )
    parser_args.add_argument(
        '--manual-only',
        action='store_true',
        help='Only process manual_review.csv classifications without reprocessing PDFs (lightweight mode)'
    )
    
    args = parser_args.parse_args()
    
    # Get statements directory (relative to project root, not script location)
    if Path(args.statements_dir).is_absolute():
        statements_dir = Path(args.statements_dir)
    else:
        statements_dir = Path(__file__).parent.parent / args.statements_dir
    
    if not statements_dir.exists():
        print(f"Error: Statements directory not found: {statements_dir}")
        sys.exit(1)
    
    # Check if LLM is available
    print("Checking for LLM availability...")
    use_llm = check_llm_availability()
    if use_llm:
        print("✓ Ollama LLM detected - will use AI for enhanced categorization")
    else:
        print("⚠ Ollama LLM not available - using pattern matching only")
        print("  (Install Ollama and run 'ollama pull dolphin-mistral' for better categorization)")
    
    # Initialize parser once
    print("Initializing hybrid parser...")
    statement_parser = HybridPDFParser()
    
    # Get monthly directories
    monthly_dirs = get_monthly_directories(statements_dir)
    
    if not monthly_dirs:
        print(f"\nNo monthly directories found in {statements_dir}")
        print("\nExpected format: YYYY-MM (e.g., 2024-11, 2024-12)")
        print("\nExample structure:")
        print("  statements/")
        print("    2024-11/")
        print("      statement.pdf")
        print("    2024-12/")
        print("      statement.pdf")
        sys.exit(1)
    
    print(f"\nFound {len(monthly_dirs)} monthly director(ies):")
    for d in monthly_dirs:
        print(f"  - {d.name}")
    
    # Determine which months to process
    if args.month:
        if args.month.lower() == 'latest':
            # Process only the latest month
            months_to_process = [monthly_dirs[-1]]
            print(f"\nProcessing latest month: {months_to_process[0].name}")
        else:
            # Process specific month
            month_dir = statements_dir / args.month
            if not month_dir.exists():
                print(f"\nError: Month directory not found: {args.month}")
                sys.exit(1)
            months_to_process = [month_dir]
            print(f"\nProcessing specific month: {args.month}")
    else:
        # Process all months
        months_to_process = monthly_dirs
        print(f"\nProcessing all {len(months_to_process)} month(s)")
    
    # Process each month
    success_count = 0
    for month_dir in months_to_process:
        success = process_month(month_dir, statement_parser, use_llm, args.force, args.manual_only)
        if success:
            success_count += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"Summary: Successfully processed {success_count}/{len(months_to_process)} month(s)")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
