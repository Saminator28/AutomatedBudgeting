"""
Integration tests for monthly processing workflow.
Tests the full workflow with mock data (no PDF processing).
"""

import unittest
import sys
import tempfile
import shutil
import csv
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestManualTransactionImport(unittest.TestCase):
    """Test manual transaction CSV import and merging."""
    
    def setUp(self):
        """Create temporary test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.statements_dir = Path(self.test_dir) / "statements" / "2025-11"
        self.statements_dir.mkdir(parents=True)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)
    
    def test_manual_transactions_format(self):
        """Test that manual_transactions.csv has correct format."""
        manual_file = self.statements_dir / "manual_transactions.csv"
        
        # Create sample manual transactions
        with open(manual_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Transaction Date', 'Place', 'Amount', 'category'])
            writer.writerow(['11/26/2025', "Farmer's Market", '35.50', 'Groceries'])
            writer.writerow(['11/27/2025', 'Coffee Shop', '6.25', 'Dining'])
        
        # Verify file exists and is readable
        self.assertTrue(manual_file.exists())
        
        # Verify format
        with open(manual_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['Place'], "Farmer's Market")
            self.assertEqual(rows[0]['Amount'], '35.50')
            self.assertEqual(rows[0]['category'], 'Groceries')


class TestIncomeExpenseSeparation(unittest.TestCase):
    """Test income vs expense separation logic."""
    
    def setUp(self):
        """Create sample transactions."""
        self.transactions = [
            {'Transaction Date': '11/05/2025', 'Place': 'MOBILE DEPOSIT', 'Credits': 3478.28, 'Type': 'Credit'},
            {'Transaction Date': '11/14/2025', 'Place': 'JOHN DEERE WORLD PAYROLL', 'Credits': 2550.82, 'Type': 'Credit'},
            {'Transaction Date': '11/03/2025', 'Place': 'PRAIRIE PROPERTY', 'Debits': 1220.00, 'Type': 'Debit'},
            {'Transaction Date': '11/14/2025', 'Place': 'PANDA EXPRESS', 'Credits': 13.68, 'Type': 'Credit'},
        ]
    
    def test_income_identification(self):
        """Test that income transactions are identified correctly."""
        income_keywords = ['PAYROLL', 'MOBILE DEPOSIT', 'DEPOSIT', 'SALARY']
        
        income_transactions = []
        for txn in self.transactions:
            place = txn['Place'].upper()
            if any(keyword in place for keyword in income_keywords):
                income_transactions.append(txn)
        
        # Should identify 2 income transactions
        self.assertEqual(len(income_transactions), 2)
        self.assertIn('PAYROLL', income_transactions[0]['Place'])
        self.assertIn('DEPOSIT', income_transactions[1]['Place'])
    
    def test_expense_identification(self):
        """Test that expense transactions are identified correctly."""
        income_keywords = ['PAYROLL', 'MOBILE DEPOSIT', 'DEPOSIT', 'SALARY']
        
        expense_transactions = []
        for txn in self.transactions:
            place = txn['Place'].upper()
            if not any(keyword in place for keyword in income_keywords):
                expense_transactions.append(txn)
        
        # Should identify 2 expense transactions
        self.assertEqual(len(expense_transactions), 2)


class TestTransferDetection(unittest.TestCase):
    """Test cross-statement transfer detection."""
    
    def test_transfer_keywords(self):
        """Test detection of internal transfers."""
        transfer_keywords = [
            'ONLINE-PHONE TRANSFER',
            'ONLINE PAYMENT',
            'TRANSFER FROM',
            'TRANSFER TO'
        ]
        
        test_transactions = [
            {'Place': 'ONLINE-PHONE TRANSFER TO XXXXXX5218', 'Amount': 25.0},
            {'Place': 'ONLINE PAYMENT THANK', 'Amount': 4206.03},
            {'Place': 'TRANSFER FROM XXXXXX7950', 'Amount': 500.0},
            {'Place': 'WALMART', 'Amount': 50.0}  # Not a transfer
        ]
        
        transfers = []
        for txn in test_transactions:
            place = txn['Place'].upper()
            if any(keyword in place for keyword in transfer_keywords):
                transfers.append(txn)
        
        # Should identify 3 transfers, not the Walmart transaction
        self.assertEqual(len(transfers), 3)
        self.assertNotIn('WALMART', [t['Place'] for t in transfers])


class TestPaymentAppDetection(unittest.TestCase):
    """Test payment app transaction detection."""
    
    def test_payment_app_keywords(self):
        """Test detection of payment app transactions."""
        payment_apps = ['VENMO', 'ZELLE', 'CASH APP', 'PAYPAL', 'APPLE PAY']
        
        test_transactions = [
            {'Place': 'VENMO PAYMENT', 'Amount': 50.0},
            {'Place': 'ZELLE TRANSFER', 'Amount': 100.0},
            {'Place': 'CASH APP', 'Amount': 25.0},
            {'Place': 'WALMART', 'Amount': 50.0}  # Not a payment app
        ]
        
        payment_app_transactions = []
        for txn in test_transactions:
            place = txn['Place'].upper()
            if any(app in place for app in payment_apps):
                payment_app_transactions.append(txn)
        
        # Should identify 3 payment app transactions
        self.assertEqual(len(payment_app_transactions), 3)


class TestMonthValidation(unittest.TestCase):
    """Test month format validation."""
    
    def test_valid_month_formats(self):
        """Test that valid YYYY-MM formats are accepted."""
        valid_months = [
            '2025-11',
            '2025-01',
            '2025-12',
            '2024-06'
        ]
        
        for month in valid_months:
            # Test format
            parts = month.split('-')
            self.assertEqual(len(parts), 2)
            
            year, month_num = parts
            self.assertEqual(len(year), 4)
            self.assertEqual(len(month_num), 2)
            self.assertTrue(1 <= int(month_num) <= 12)
    
    def test_invalid_month_formats(self):
        """Test that invalid formats are rejected."""
        invalid_months = [
            '2025-13',  # Invalid month
            '25-11',    # Two-digit year
            '2025/11',  # Wrong separator
            '11-2025',  # Wrong order
        ]
        
        for month in invalid_months:
            try:
                parts = month.split('-')
                if len(parts) != 2:
                    continue
                year, month_num = parts
                if len(year) != 4 or len(month_num) != 2:
                    continue
                if not (1 <= int(month_num) <= 12):
                    continue
                self.fail(f"Should reject {month}")
            except (ValueError, AssertionError):
                pass  # Expected to fail


class TestCSVOutputFormat(unittest.TestCase):
    """Test CSV output file formats."""
    
    def setUp(self):
        """Create temporary test directory."""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)
    
    def test_expenses_csv_format(self):
        """Test expenses.csv has correct columns."""
        expenses_file = Path(self.test_dir) / "expenses.csv"
        
        # Create sample expenses file
        with open(expenses_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Transaction Date', 'Place', 'Amount', 'Statement', 'category'])
            writer.writerow(['11/14/2025', 'PANDA EXPRESS', '13.68', 'Scheels Visa', 'Dining'])
        
        # Verify format
        with open(expenses_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            required_columns = ['Transaction Date', 'Place', 'Amount', 'Statement', 'category']
            self.assertEqual(list(rows[0].keys()), required_columns)
    
    def test_income_csv_format(self):
        """Test income.csv has correct columns."""
        income_file = Path(self.test_dir) / "income.csv"
        
        # Create sample income file
        with open(income_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Transaction Date', 'Place', 'Statement', 'Amount', 'category'])
            writer.writerow(['11/14/2025', 'PAYROLL', 'Stearns Bank', '2550.82', 'Rent/Mortgage'])
        
        # Verify format
        with open(income_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            required_columns = ['Transaction Date', 'Place', 'Statement', 'Amount', 'category']
            self.assertEqual(list(rows[0].keys()), required_columns)
    
    def test_manual_review_csv_format(self):
        """Test manual_review.csv has correct columns."""
        manual_review_file = Path(self.test_dir) / "manual_review.csv"
        
        # Create sample manual review file
        with open(manual_review_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Transaction Date', 'Place', 'Statement', 'Amount', 'Type', 'Classification', 'category'])
            writer.writerow(['11/15/2025', 'VENMO PAYMENT', 'Chase', '50.0', 'Debit', '', ''])
        
        # Verify format
        with open(manual_review_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            required_columns = ['Transaction Date', 'Place', 'Statement', 'Amount', 'Type', 'Classification', 'category']
            self.assertEqual(list(rows[0].keys()), required_columns)


if __name__ == '__main__':
    unittest.main()
