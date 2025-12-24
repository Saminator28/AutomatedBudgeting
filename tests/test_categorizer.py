"""
Unit tests for AI categorization system.
Tests transaction categorization without requiring LLM.
"""

import unittest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai_classification.categorizer import TransactionCategorizer


class TestCategorization(unittest.TestCase):
    """Test transaction categorization logic."""
    
    def setUp(self):
        """Initialize categorizer for tests."""
        self.categorizer = TransactionCategorizer(use_llm=False)
    
    def test_grocery_categorization(self):
        """Test grocery store categorization."""
        test_cases = [
            "CASH WISE",
            "TARGET",
            "WALMART",
            "ALDI",
            "HY-VEE"
        ]
        
        for place in test_cases:
            category = self.categorizer.categorize_transaction(place, 50.00)
            self.assertEqual(category, "Groceries", f"Failed for {place}")
    
    def test_dining_categorization(self):
        """Test restaurant categorization."""
        test_cases = [
            "PANDA EXPRESS",
            "MCDONALD'S",
            "STARBUCKS",
            "CHIPOTLE",
            "SUBWAY"
        ]
        
        for place in test_cases:
            category = self.categorizer.categorize_transaction(place, 15.00)
            self.assertEqual(category, "Dining", f"Failed for {place}")
    
    def test_transportation_categorization(self):
        """Test transportation categorization."""
        test_cases = [
            "CASEY'S",
            "SHELL",
            "BP",
            "SPEEDWAY",
            "EXXON"
        ]
        
        for place in test_cases:
            category = self.categorizer.categorize_transaction(place, 40.00)
            self.assertEqual(category, "Transportation", f"Failed for {place}")
    
    def test_entertainment_categorization(self):
        """Test entertainment categorization."""
        test_cases = [
            "MICROSOFT XBOX",
            "NETFLIX",
            "SPOTIFY",
            "AMC THEATERS"
        ]
        
        for place in test_cases:
            category = self.categorizer.categorize_transaction(place, 20.00)
            self.assertEqual(category, "Entertainment", f"Failed for {place}")
    
    def test_pattern_learning(self):
        """Test that categorizer learns from new patterns."""
        # Add a new pattern
        self.categorizer.add_pattern("NEW TEST STORE", "Shopping")
        
        # Verify it's categorized correctly
        category = self.categorizer.categorize_transaction("NEW TEST STORE", 25.00)
        self.assertEqual(category, "Shopping")
    
    def test_uncategorized_handling(self):
        """Test handling of unknown merchants."""
        unknown_place = "COMPLETELY UNKNOWN MERCHANT XYZ123"
        category = self.categorizer.categorize_transaction(unknown_place, 30.00)
        
        # Should return None or "Uncategorized"
        self.assertIn(category, [None, "Uncategorized", ""])


class TestCategoryValidation(unittest.TestCase):
    """Test category validation and correction."""
    
    def setUp(self):
        """Initialize categorizer for tests."""
        self.categorizer = TransactionCategorizer(use_llm=False)
    
    def test_valid_categories(self):
        """Test that valid categories are accepted."""
        valid_categories = [
            "Groceries",
            "Dining",
            "Transportation",
            "Utilities",
            "Healthcare",
            "Shopping",
            "Entertainment",
            "Rent",
            "Insurance"
        ]
        
        for category in valid_categories:
            is_valid = self.categorizer.is_valid_category(category)
            self.assertTrue(is_valid, f"Should accept {category}")
    
    def test_invalid_categories_rejected(self):
        """Test that invalid categories are rejected."""
        invalid_categories = [
            "InvalidCategory",
            "Random123",
            "NotACategory"
        ]
        
        for category in invalid_categories:
            is_valid = self.categorizer.is_valid_category(category)
            self.assertFalse(is_valid, f"Should reject {category}")
    
    def test_fuzzy_category_matching(self):
        """Test fuzzy matching for typos and abbreviations."""
        test_cases = [
            ("food", "Dining"),
            ("grocerys", "Groceries"),
            ("util", "Utilities"),
            ("car", "Transportation"),
            ("rent/mortgage", "Rent")
        ]
        
        for typo, expected in test_cases:
            corrected = self.categorizer.correct_category(typo)
            self.assertEqual(corrected, expected, f"Failed to correct {typo}")


class TestIncomeDetection(unittest.TestCase):
    """Test income vs expense detection."""
    
    def setUp(self):
        """Initialize categorizer for tests."""
        self.categorizer = TransactionCategorizer(use_llm=False)
    
    def test_income_keywords(self):
        """Test detection of income transactions."""
        income_places = [
            "PAYROLL",
            "MOBILE DEPOSIT",
            "DIRECT DEPOSIT",
            "SALARY",
            "INTEREST EARNED"
        ]
        
        for place in income_places:
            is_income = self.categorizer.is_income(place)
            self.assertTrue(is_income, f"Should detect {place} as income")
    
    def test_expense_keywords(self):
        """Test that expenses are not marked as income."""
        expense_places = [
            "WALMART",
            "TARGET",
            "MCDONALD'S",
            "SHELL GAS"
        ]
        
        for place in expense_places:
            is_income = self.categorizer.is_income(place)
            self.assertFalse(is_income, f"Should not detect {place} as income")


if __name__ == '__main__':
    unittest.main()
