"""
Transaction Categorization Module

Uses AI to classify transactions into budget categories.
Loads category patterns from config/category_patterns.json for easy customization.
"""

import pandas as pd
from typing import List, Dict, Optional
import re
import json
from pathlib import Path
import requests


class TransactionCategorizer:
    """Categorize transactions using pattern matching and AI."""
    
    def __init__(self, config_path: str = None, use_llm: bool = False, llm_host: str = "http://localhost:11434"):
        """
        Initialize the categorizer.
        
        Args:
            config_path: Path to category_patterns.json file (optional)
            use_llm: Whether to use LLM for verification and fallback categorization
            llm_host: Ollama server URL
        """
        if config_path:
            self.categories = self._load_categories(config_path)
        else:
            # Try to load from default location
            try:
                default_path = Path(__file__).parent.parent.parent / 'config' / 'category_patterns.json'
                self.categories = self._load_categories(default_path)
            except FileNotFoundError:
                print("⚠ Warning: config/category_patterns.json not found. Using built-in patterns.")
                self.categories = self._get_default_patterns()
        
        self.use_llm = use_llm
        self.llm_host = llm_host
        self.llm_available = False
        
        if self.use_llm:
            self.llm_available = self._check_llm_availability()
    
    def _load_categories(self, config_path) -> dict:
        """Load category patterns from JSON file."""
        with open(config_path, 'r') as f:
            data = json.load(f)
            return data.get('categories', {})
    
    def _get_default_patterns(self) -> dict:
        """Fallback default patterns if config file not found."""
        return {
            'Groceries': ['walmart', 'target', 'kroger', 'grocery', 'supermarket'],
            'Dining': ['restaurant', 'cafe', 'coffee', 'pizza', 'food'],
            'Transportation': ['gas', 'fuel', 'uber', 'lyft', 'parking'],
            'Utilities': ['electric', 'power', 'water', 'internet', 'phone'],
            'Shopping': ['amazon', 'ebay', 'store', 'shop'],
            'Healthcare': ['pharmacy', 'cvs', 'walgreens', 'medical', 'doctor'],
        }
    
    def _check_llm_availability(self) -> bool:
        """Check if Ollama LLM is available."""
        try:
            response = requests.get(f"{self.llm_host}/api/tags", timeout=2)
            if response.status_code == 200:
                print("✓ LLM categorization enabled (Ollama connected)")
                return True
        except:
            pass
        print("⚠ LLM categorization disabled (Ollama not available)")
        return False
    
    def _categorize_with_llm(self, merchant: str, amount: float = None) -> Optional[str]:
        """
        Use LLM to categorize a transaction.
        
        Args:
            merchant: Merchant name
            amount: Optional transaction amount for context
            
        Returns:
            Category name or None if LLM fails
        """
        if not self.llm_available:
            return None
        
        # Build category list for prompt
        category_list = ", ".join(self.categories.keys())
        
        # Create prompt
        amount_context = f" Amount: ${amount:.2f}." if amount else ""
        prompt = f"""Categorize this transaction into ONE of these budget categories: {category_list}

Merchant: {merchant}{amount_context}

Respond with ONLY the category name, nothing else. If none fit well, respond with "Uncategorized"."""
        
        try:
            response = requests.post(
                f"{self.llm_host}/api/generate",
                json={
                    "model": "dolphin-mistral:latest",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 20
                    }
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                category = result.get("response", "").strip()
                
                # Validate the category is in our list
                if category in self.categories:
                    return category
                
                # Try case-insensitive match
                for valid_category in self.categories.keys():
                    if category.lower() == valid_category.lower():
                        return valid_category
                
        except Exception as e:
            pass
        
        return None
    
    def categorize_transaction(
        self, 
        description: str,
        amount: float = None
    ) -> str:
        """
        Categorize a single transaction based on its description.
        Uses keyword matching first, then LLM fallback if enabled.
        
        Args:
            description: Transaction description text
            amount: Optional transaction amount for LLM context
            
        Returns:
            Category name or 'Uncategorized'
        """
        description_lower = description.lower()
        
        # First, try keyword matching
        for category, patterns in self.categories.items():
            for pattern in patterns:
                if pattern.lower() in description_lower:
                    return category
        
        # If uncategorized and LLM is enabled, try LLM
        if self.use_llm and self.llm_available:
            llm_category = self._categorize_with_llm(description, amount)
            if llm_category:
                return llm_category
        
        return 'Uncategorized'
    
    def categorize_dataframe(
        self,
        df: pd.DataFrame,
        description_column: str = 'Merchant',
        amount_column: str = 'Amount'
    ) -> pd.DataFrame:
        """
        Add category column to a DataFrame of transactions.
        
        Args:
            df: DataFrame with transactions
            description_column: Name of column containing merchant names
            amount_column: Name of column containing amounts (for LLM context)
            
        Returns:
            DataFrame with added 'category' column
        """
        if description_column not in df.columns:
            raise ValueError(f"Column '{description_column}' not found in DataFrame")
        
        # Categorize with or without amount column
        if amount_column in df.columns and self.use_llm:
            df['category'] = df.apply(
                lambda row: self.categorize_transaction(
                    row[description_column], 
                    row[amount_column]
                ), 
                axis=1
            )
        else:
            df['category'] = df[description_column].apply(self.categorize_transaction)
        
        return df
    
    def add_custom_category(
        self,
        category_name: str,
        keywords: List[str]
    ):
        """
        Add a custom category with keywords.
        
        Args:
            category_name: Name of the category
            keywords: List of keywords to match
        """
        self.categories[category_name] = keywords
    
    def get_category_summary(
        self,
        df: pd.DataFrame,
        amount_column: str = 'amount'
    ) -> pd.DataFrame:
        """
        Get spending summary by category.
        
        Args:
            df: DataFrame with categorized transactions
            amount_column: Name of column containing amounts
            
        Returns:
            DataFrame with category spending summary
        """
        if 'category' not in df.columns:
            raise ValueError("DataFrame must have 'category' column. Run categorize_dataframe first.")
        
        if amount_column not in df.columns:
            raise ValueError(f"Column '{amount_column}' not found in DataFrame")
        
        summary = df.groupby('category')[amount_column].agg([
            ('total', 'sum'),
            ('count', 'count'),
            ('average', 'mean')
        ]).round(2)
        
        summary = summary.sort_values('total', ascending=False)
        
        return summary
    
    def get_uncategorized_transactions(
        self,
        df: pd.DataFrame,
        merchant_column: str = 'Merchant'
    ) -> pd.DataFrame:
        """
        Get all transactions that were not categorized.
        
        Args:
            df: DataFrame with categorized transactions
            merchant_column: Name of column containing merchant names
            
        Returns:
            DataFrame with uncategorized transactions
        """
        if 'category' not in df.columns:
            raise ValueError("DataFrame must have 'category' column. Run categorize_dataframe first.")
        
        return df[df['category'] == 'Uncategorized'].copy()
    
    def print_categorization_report(
        self,
        df: pd.DataFrame,
        merchant_column: str = 'Merchant',
        month: str = None
    ):
        """
        Print a report of categorization results for a specific month.
        
        Args:
            df: DataFrame with categorized transactions
            merchant_column: Name of column containing merchant names
            month: Optional month identifier (e.g., '2025-11') to display in report
        """
        if 'category' not in df.columns:
            raise ValueError("DataFrame must have 'category' column. Run categorize_dataframe first.")
        
        total_count = len(df)
        uncategorized = df[df['category'] == 'Uncategorized']
        uncategorized_count = len(uncategorized)
        categorized_count = total_count - uncategorized_count
        
        print("\n" + "="*60)
        if month:
            print(f"CATEGORIZATION REPORT - {month}")
        else:
            print("CATEGORIZATION REPORT")
        print("="*60)
        print(f"Total transactions: {total_count}")
        print(f"Categorized: {categorized_count} ({categorized_count/total_count*100:.1f}%)")
        print(f"Uncategorized: {uncategorized_count} ({uncategorized_count/total_count*100:.1f}%)")
        
        if self.use_llm and self.llm_available:
            print("LLM enhancement: ✓ Enabled (used for uncategorized items)")
        elif self.use_llm and not self.llm_available:
            print("LLM enhancement: ✗ Unavailable (Ollama not running)")
        
        if uncategorized_count > 0:
            print("\n⚠ UNCATEGORIZED TRANSACTIONS:")
            print("-" * 60)
            # Get unique merchants that weren't categorized
            unique_merchants = uncategorized[merchant_column].unique()
            for i, merchant in enumerate(sorted(unique_merchants), 1):
                count = len(uncategorized[uncategorized[merchant_column] == merchant])
                print(f"  {i}. {merchant} ({count} transaction{'s' if count > 1 else ''})")
            
            if self.use_llm and self.llm_available:
                print("\n💡 Note: LLM was unable to categorize these items.")
                print("  Add keywords to config/category_patterns.json for faster matching next time.")
            else:
                print("\n💡 To categorize these:")
                print("  1. Check the merchant names above")
                print("  2. Edit config/category_patterns.json")
                print("  3. Add lowercase keywords to appropriate categories")
                print("  4. Re-run with --force --categorize to update")
                if not self.llm_available:
                    print("  OR: Start Ollama and use --llm for AI-powered categorization")
        else:
            print("\n✓ All transactions successfully categorized!")
        
        print("="*60 + "\n")


# Future enhancement: GPT-based categorizer
class GPTCategorizer:
    """
    Advanced categorizer using GPT API.
    
    NOTE: Requires OpenAI API key and is currently a placeholder.
    To use: Set OPENAI_API_KEY environment variable and implement the methods.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize GPT categorizer.
        
        Args:
            api_key: OpenAI API key (or load from environment)
        """
        self.api_key = api_key
        # TODO: Initialize OpenAI client
        pass
    
    def categorize_transaction(self, description: str, amount: float = None) -> str:
        """
        Categorize transaction using GPT.
        
        Args:
            description: Transaction description
            amount: Transaction amount (optional, helps with context)
            
        Returns:
            Category name
        """
        # TODO: Implement GPT-based categorization
        raise NotImplementedError("GPT categorization not yet implemented")
