"""
Example Usage Script

Demonstrates how to use the automated budgeting tool.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from bankai.parser.statement_parser import StatementParser
from ai_classification.categorizer import TransactionCategorizer


def example_basic_usage():
    """Basic example: Convert PDF to Excel."""
    print("Example 1: Basic PDF to Excel Conversion")
    print("-" * 50)
    
    # Initialize parser
    parser = StatementParser()
    
    # Process a statement
    parser.bankstatement2csv(
        pdf='statements/your_statement.pdf',
        output_file='output.xlsx',
        visualize=False
    )
    
    print("\n✅ Done! Check output.xlsx for results.\n")


def example_with_categorization():
    """Advanced example: Convert and categorize transactions."""
    import pandas as pd
    
    print("Example 2: With Transaction Categorization")
    print("-" * 50)
    
    # Step 1: Parse the statement
    parser = StatementParser()
    parser.bankstatement2csv(
        pdf='statements/your_statement.pdf',
        output_file='transactions_raw.xlsx'
    )
    
    # Step 2: Load the extracted data
    df = pd.read_excel('transactions_raw.xlsx')
    
    # Step 3: Categorize transactions
    categorizer = TransactionCategorizer()
    
    # Assuming your DataFrame has a 'raw_text' column with transaction descriptions
    if 'raw_text' in df.columns:
        df = categorizer.categorize_dataframe(df, description_column='raw_text')
        
        # Step 4: Generate category summary
        if 'amount' in df.columns:
            summary = categorizer.get_category_summary(df, amount_column='amount')
            print("\nCategory Summary:")
            print(summary)
        
        # Step 5: Save categorized results
        df.to_excel('transactions_categorized.xlsx', index=False)
        print("\n✅ Saved categorized transactions to transactions_categorized.xlsx\n")


def example_custom_categories():
    """Example: Add custom category patterns."""
    print("Example 3: Custom Categories")
    print("-" * 50)
    
    categorizer = TransactionCategorizer()
    
    # Add custom category
    categorizer.add_custom_category(
        category_name='Fitness',
        keywords=['gym', 'fitness', 'yoga', 'workout', 'planet fitness', '24 hour fitness']
    )
    
    # Test categorization
    test_descriptions = [
        "PLANET FITNESS MEMBERSHIP",
        "STARBUCKS COFFEE",
        "WHOLE FOODS MARKET"
    ]
    
    for desc in test_descriptions:
        category = categorizer.categorize_transaction(desc)
        print(f"{desc:40} -> {category}")
    
    print()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Automated Budgeting Tool - Usage Examples")
    print("="*60 + "\n")
    
    # Run examples
    # Uncomment the example you want to run:
    
    # example_basic_usage()
    # example_with_categorization()
    example_custom_categories()
    
    print("="*60)
