#!/usr/bin/env python3
"""
Automated Budgeting Tool - Main Entry Point

This script processes bank/credit card statements (PDF) and converts them
into structured data for budgeting analysis.

Usage:
    python main.py --pdf path/to/statement.pdf
    python main.py --pdf statements/statement.pdf --output results.xlsx
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bankai.parser.statement_parser import StatementParser


def main():
    """Main function to run the budgeting tool."""
    parser = argparse.ArgumentParser(
        description='Convert bank statements (PDF) to structured data'
    )
    parser.add_argument(
        '--pdf',
        type=str,
        required=True,
        help='Path to the PDF bank statement'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='output.xlsx',
        help='Output filename (default: output.xlsx)'
    )
    parser.add_argument(
        '--visualize',
        action='store_true',
        help='Visualize table detection results'
    )
    parser.add_argument(
        '--use-llm',
        action='store_true',
        help='Use LLM (GPT-4) for enhanced place name cleaning (requires OPENAI_API_KEY)'
    )
    
    args = parser.parse_args()
    
    # Validate PDF file exists
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)
    
    print(f"Processing: {args.pdf}")
    print("-" * 50)
    
    # Initialize parser with optional LLM cleaning
    statement_parser = StatementParser(
        clean_place_names=True,
        use_llm_cleaning=args.use_llm
    )
    
    # Process the statement
    try:
        statement_parser.bankstatement2csv(
            pdf=str(pdf_path),
            output_file=args.output,
            visualize=args.visualize
        )
        print(f"\n✅ Success! Output saved to: {args.output}")
        
    except Exception as e:
        print(f"\n❌ Error processing statement: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
