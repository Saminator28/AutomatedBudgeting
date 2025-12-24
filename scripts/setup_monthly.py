#!/usr/bin/env python3
"""
Setup Monthly Directory Structure

Helps organize existing statements into monthly folders.
"""

import sys
from pathlib import Path
import shutil
import re


def extract_date_from_filename(filename: str):
    """Try to extract a date from the filename."""
    # Look for patterns like 2024-12-16 or statement_2025-12-16
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}"
    return None


def main():
    statements_dir = Path(__file__).parent.parent / "statements"
    
    if not statements_dir.exists():
        print("Creating statements directory...")
        statements_dir.mkdir()
    
    # Find all PDF files in the statements directory (not in subdirectories)
    pdf_files = [f for f in statements_dir.glob("*.pdf")]
    
    if not pdf_files:
        print("\n✅ No PDF files found in statements/ directory to organize.")
        print("\nTo add a new month:")
        print("  1. Create directory: statements/YYYY-MM/")
        print("  2. Put your PDF in that folder")
        print("  3. Run: python process_monthly.py")
        print("\nExample:")
        print("  mkdir -p statements/2024-12")
        print("  mv statement.pdf statements/2024-12/")
        print("  python process_monthly.py --month 2024-12")
        return
    
    print(f"\nFound {len(pdf_files)} PDF file(s) in statements/")
    print("="*60)
    
    for pdf_file in pdf_files:
        print(f"\nFile: {pdf_file.name}")
        
        # Try to extract date from filename
        month_dir = extract_date_from_filename(pdf_file.name)
        
        if month_dir:
            print(f"  Detected month: {month_dir}")
        else:
            print("  Enter month (YYYY-MM format, or 'skip'): ", end='')
            month_dir = input().strip()
            
            if month_dir.lower() == 'skip':
                print("  Skipped.")
                continue
        
        # Create monthly directory
        target_dir = statements_dir / month_dir
        target_dir.mkdir(exist_ok=True)
        
        # Move file
        target_file = target_dir / pdf_file.name
        
        if target_file.exists():
            print(f"  ⚠ File already exists: {target_file}")
            print("  Overwrite? (y/n): ", end='')
            response = input().strip().lower()
            if response != 'y':
                print("  Skipped.")
                continue
        
        shutil.move(str(pdf_file), str(target_file))
        print(f"  ✅ Moved to: {target_dir}/")
    
    print("\n" + "="*60)
    print("✅ Organization complete!")
    print("\nYour structure:")
    for month_dir in sorted(statements_dir.glob("*/")):
        print(f"  {month_dir.name}/")
        for pdf in month_dir.glob("*.pdf"):
            print(f"    - {pdf.name}")
    
    print("\nTo process all months:")
    print("  python process_monthly.py")
    print("\nTo process specific month:")
    print("  python process_monthly.py --month 2024-12")


if __name__ == '__main__':
    main()
