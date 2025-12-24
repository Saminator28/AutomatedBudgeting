"""
Unit tests for statement parser transaction line parsing.
Tests the core parsing logic without requiring PDF processing.
"""

import unittest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bankai.parser.statement_parser import StatementParser


class TestTransactionLineParsing(unittest.TestCase):
    """Test transaction line parsing with various formats."""
    
    def setUp(self):
        """Initialize parser for tests."""
        self.parser = StatementParser()
    
    def test_basic_transaction_with_reference(self):
        """Test parsing transaction with reference number (Scheels Visa format)."""
        line = "11/14/2025 00093726600007415068 PANDA EXPRESS #3268 GRAND FORKS ND 13.68"
        result = self.parser.parse_transaction_line(line)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['Transaction Date'], '11/14/2025')
        self.assertIn('PANDA EXPRESS', result['Place'])
        self.assertEqual(result['Credits'], 13.68)
    
    def test_transaction_without_reference(self):
        """Test parsing transaction without reference number (Stearns Bank format)."""
        line = "11/05/2025 MOBILE DEPOSIT 3478.28"
        result = self.parser.parse_transaction_line(line)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['Transaction Date'], '11/05/2025')
        self.assertEqual(result['Place'], 'MOBILE DEPOSIT')
        self.assertEqual(result['Credits'], 3478.28)
    
    def test_payroll_transaction(self):
        """Test parsing payroll transaction."""
        line = "11/14/2025 JOHN DEERE WORLD PAYROLL 2550.82"
        result = self.parser.parse_transaction_line(line)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['Transaction Date'], '11/14/2025')
        self.assertIn('PAYROLL', result['Place'])
        self.assertEqual(result['Credits'], 2550.82)
    
    def test_debit_transaction(self):
        """Test parsing debit transaction (negative amount)."""
        line = "11/03/2025 PRAIRIE PROPERTY -1220.00"
        result = self.parser.parse_transaction_line(line)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['Transaction Date'], '11/03/2025')
        self.assertIn('PRAIRIE PROPERTY', result['Place'])
        self.assertEqual(result['Debits'], 1220.00)
    
    def test_date_formats(self):
        """Test various date formats are parsed correctly."""
        test_cases = [
            "11/14/2025 TEST MERCHANT 10.00",
            "1/5/2025 TEST MERCHANT 10.00",
            "12/31/2025 TEST MERCHANT 10.00"
        ]
        
        for line in test_cases:
            result = self.parser.parse_transaction_line(line)
            self.assertIsNotNone(result, f"Failed to parse: {line}")
            self.assertIn('Transaction Date', result)
    
    def test_invalid_lines_rejected(self):
        """Test that invalid lines return None."""
        invalid_lines = [
            "This is not a transaction line",
            "No date here MERCHANT 10.00",
            "11/14/2025",  # Date only, no merchant
            ""  # Empty line
        ]
        
        for line in invalid_lines:
            result = self.parser.parse_transaction_line(line)
            self.assertIsNone(result, f"Should reject: {line}")
    
    def test_amount_extraction(self):
        """Test various amount formats are extracted correctly."""
        test_cases = [
            ("11/14/2025 MERCHANT 10.00", 10.00),
            ("11/14/2025 MERCHANT 1234.56", 1234.56),
            ("11/14/2025 MERCHANT 0.50", 0.50),
            ("11/14/2025 MERCHANT -50.00", 50.00),  # Debit becomes positive
        ]
        
        for line, expected_amount in test_cases:
            result = self.parser.parse_transaction_line(line)
            self.assertIsNotNone(result)
            amount = result.get('Credits') or result.get('Debits')
            self.assertEqual(amount, expected_amount)


class TestBankDetection(unittest.TestCase):
    """Test bank pattern detection from text."""
    
    def setUp(self):
        """Initialize parser for tests."""
        self.parser = StatementParser()
    
    def test_detect_stearns_bank(self):
        """Test detection of Stearns Bank from header text."""
        header_text = "STEARNS BANK N.A. STATEMENT"
        bank = self.parser._detect_bank_from_text(header_text)
        self.assertEqual(bank, "Stearns Bank")
    
    def test_detect_scheels_visa(self):
        """Test detection of Scheels Visa from header text."""
        header_text = "SCHEELS VISA ACCOUNT STATEMENT"
        bank = self.parser._detect_bank_from_text(header_text)
        self.assertEqual(bank, "Scheels Visa")
    
    def test_unknown_bank(self):
        """Test handling of unknown bank."""
        header_text = "RANDOM UNKNOWN BANK"
        bank = self.parser._detect_bank_from_text(header_text)
        self.assertEqual(bank, "Unknown")


if __name__ == '__main__':
    unittest.main()
