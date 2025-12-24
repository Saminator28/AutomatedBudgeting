"""
Tests for configuration files and pattern matching.
"""

import unittest
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBankPatterns(unittest.TestCase):
    """Test bank pattern configuration."""
    
    def setUp(self):
        """Load bank patterns configuration."""
        config_path = Path(__file__).parent.parent / "config" / "bank_patterns.json"
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def test_config_format(self):
        """Test that bank_patterns.json has correct structure."""
        self.assertIn('patterns', self.config)
        self.assertIsInstance(self.config['patterns'], dict)
    
    def test_known_banks_configured(self):
        """Test that known banks are in configuration."""
        patterns = self.config['patterns']
        
        # Test some expected banks
        known_banks = ['STEARNS', 'SCHEELS']
        for bank in known_banks:
            self.assertIn(bank, patterns, f"{bank} should be configured")
    
    def test_pattern_matching(self):
        """Test that pattern matching works correctly."""
        patterns = self.config['patterns']
        
        test_cases = [
            ('STEARNS BANK N.A.', 'STEARNS'),
            ('SCHEELS VISA CARD', 'SCHEELS'),
        ]
        
        for text, expected_key in test_cases:
            # Simulate pattern matching
            matched = None
            for key in patterns.keys():
                if key.upper() in text.upper():
                    matched = key
                    break
            
            self.assertEqual(matched, expected_key, f"Failed to match {text}")


class TestIncomeKeywords(unittest.TestCase):
    """Test income keyword configuration."""
    
    def setUp(self):
        """Load income keywords configuration."""
        config_path = Path(__file__).parent.parent / "config" / "income_keywords.json"
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def test_config_format(self):
        """Test that income_keywords.json has correct structure."""
        self.assertIn('income_keywords', self.config)
        self.assertIsInstance(self.config['income_keywords'], list)
    
    def test_common_income_keywords(self):
        """Test that common income keywords are present."""
        keywords = self.config['income_keywords']
        
        expected_keywords = ['PAYROLL', 'DEPOSIT', 'SALARY']
        for keyword in expected_keywords:
            # Case-insensitive check
            found = any(keyword.upper() in k.upper() for k in keywords)
            self.assertTrue(found, f"{keyword} should be in income keywords")


class TestCategoryPatterns(unittest.TestCase):
    """Test category pattern configuration."""
    
    def setUp(self):
        """Load category patterns configuration."""
        config_path = Path(__file__).parent.parent / "config" / "category_patterns.json"
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def test_config_format(self):
        """Test that category_patterns.json has correct structure."""
        self.assertIn('valid_categories', self.config)
        self.assertIn('patterns', self.config)
        self.assertIsInstance(self.config['valid_categories'], list)
        self.assertIsInstance(self.config['patterns'], dict)
    
    def test_valid_categories(self):
        """Test that valid categories are defined."""
        categories = self.config['valid_categories']
        
        expected_categories = [
            'Groceries',
            'Dining',
            'Transportation',
            'Utilities',
            'Healthcare',
            'Shopping',
            'Entertainment'
        ]
        
        for category in expected_categories:
            self.assertIn(category, categories, f"{category} should be valid")
    
    def test_patterns_format(self):
        """Test that patterns have correct format."""
        patterns = self.config['patterns']
        
        for place, category in patterns.items():
            self.assertIsInstance(place, str)
            self.assertIsInstance(category, str)
            self.assertIn(category, self.config['valid_categories'],
                         f"{category} for {place} is not a valid category")


class TestPaymentAppConfig(unittest.TestCase):
    """Test payment app configuration."""
    
    def setUp(self):
        """Load payment app configuration."""
        config_path = Path(__file__).parent.parent / "config" / "payment_apps.json"
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def test_config_format(self):
        """Test that payment_apps.json has correct structure."""
        self.assertIn('payment_apps', self.config)
        self.assertIsInstance(self.config['payment_apps'], list)
    
    def test_common_payment_apps(self):
        """Test that common payment apps are configured."""
        apps = self.config['payment_apps']
        
        expected_apps = ['VENMO', 'ZELLE', 'CASH APP', 'PAYPAL']
        for app in expected_apps:
            # Case-insensitive check
            found = any(app.upper() in a.upper() for a in apps)
            self.assertTrue(found, f"{app} should be in payment apps")


if __name__ == '__main__':
    unittest.main()
