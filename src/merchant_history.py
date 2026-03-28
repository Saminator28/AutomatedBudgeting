"""
Merchant History Learning Module

Automatically learns merchant categorizations from previous months' expenses.
This allows the system to learn from your manual corrections over time.
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional, Dict, Tuple
import re


class MerchantHistory:
    """Learn and retrieve merchant categorizations from historical data."""
    
    def __init__(self, statements_dir: Path, min_confidence: int = 2, exclude_month: str = None):
        """
        Initialize merchant history from all previous expenses.csv files.
        
        Args:
            statements_dir: Path to statements directory containing monthly folders
            min_confidence: Minimum number of occurrences to trust a categorization
            exclude_month: Month to exclude (and all months after) in YYYY-MM format (current month being processed)
        """
        self.statements_dir = Path(statements_dir)
        self.min_confidence = min_confidence
        self.exclude_month = exclude_month
        self.merchant_categories = {}  # normalized_key -> category
        self.merchant_confidence = {}  # normalized_key -> count
        self.merchant_history = defaultdict(Counter)  # normalized_key -> {category: count}
        self.merchant_name_spellings = defaultdict(Counter)  # normalized_key -> {spelling: count}
        self.merchant_report_spellings = defaultdict(Counter)  # normalized_key -> {spelling: count} from monthly_reports
        
        self._load_history()
    
    @staticmethod
    def _normalize_key(name: str) -> str:
        """
        Canonical key for merchant matching.
        Strips apostrophes/punctuation, store numbers, and extra whitespace
        so variants like "Merchant's", "Merchants", "MERCHANTS #3370" all map to "merchants".
        """
        s = name.lower()
        # Remove apostrophes and common punctuation that varies between statements
        s = re.sub(r"['\.\-,]", '', s)
        # Remove store/location numbers (e.g. "#3370", "#117", "1696")
        s = re.sub(r'#\d+', '', s)
        s = re.sub(r'\b\d{3,}\b', '', s)
        # Collapse whitespace
        s = ' '.join(s.split())
        return s
    
    def _load_history(self):
        """Load all historical expenses from the SQLite DB to build merchant→category history.

        The DB reflects any UI corrections the user made after parsing. The raw
        statements/YYYY-MM/expenses.csv files are kept only as parser artifacts and are
        deliberately NOT read here, so corrected categories are never overridden by stale
        parser output.
        """
        total_transactions = 0

        try:
            import sys
            sys.path.insert(0, str(self.statements_dir.parent.parent))
            from src.database.session import get_engine
            from sqlalchemy import text as _text
            eng = get_engine()
            with eng.connect() as conn:
                rows = conn.execute(_text(
                    "SELECT place, category, report_month FROM transactions "
                    "WHERE tx_type='expense' AND category IS NOT NULL AND category != '' "
                    "ORDER BY report_month"
                )).fetchall()
            for place, category, report_month in rows:
                if not place or not category:
                    continue
                if self.exclude_month and report_month and report_month >= self.exclude_month:
                    continue
                if str(category).lower() in ['uncategorized', 'nan']:
                    continue
                place_normalized = self._normalize_key(str(place).strip())
                self.merchant_history[place_normalized][category] += 1
                self.merchant_name_spellings[place_normalized][str(place).strip()] += 1
                self.merchant_report_spellings[place_normalized][str(place).strip()] += 1
                total_transactions += 1
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning(f"merchant_history: DB read failed — {exc}")

        for merchant, category_counts in self.merchant_history.items():
            if not category_counts:
                continue
            total_count = sum(category_counts.values())
            most_common_category, _ = category_counts.most_common(1)[0]
            if total_count >= self.min_confidence:
                self.merchant_categories[merchant] = most_common_category
                self.merchant_confidence[merchant] = total_count

        if self.merchant_categories:
            print(f"  📚 Loaded merchant history: {len(self.merchant_categories)} merchants from {total_transactions} transactions")
            high_confidence = sum(1 for c in self.merchant_confidence.values() if c >= 5)
            if high_confidence > 0:
                print(f"     High confidence (5+ occurrences): {high_confidence}")
    
    def get_canonical_name(self, merchant_name: str) -> Optional[str]:
        """
        Return the most-seen spelling of this merchant from historical expenses.
        Useful to override LLM-cleaned names with the user's preferred/corrected spelling.

        Args:
            merchant_name: Any variant of the merchant name (raw, LLM-cleaned, etc.)

        Returns:
            The most commonly seen spelling from past expenses.csv files, or None if unknown.
        """
        if not merchant_name:
            return None

        key = self._normalize_key(str(merchant_name).strip())

        # 1. Exact match in monthly_reports spellings (user-visible, highest priority).
        #    These are the names as the user saw and potentially corrected them in the UI.
        spellings = self.merchant_report_spellings.get(key)
        if spellings:
            return spellings.most_common(1)[0][0]

        # 2. Prefix match in monthly_reports spellings.
        #    Handles the case where the corrected name is shorter (e.g. 'Royall Liquors'
        #    in monthly_reports vs 'Royall Liquors Roundup' in statements).
        fallback_key = self._prefix_match_key_in(key, self.merchant_report_spellings)
        if fallback_key:
            spellings = self.merchant_report_spellings.get(fallback_key)
            if spellings:
                return spellings.most_common(1)[0][0]

        # 3. Exact match in statement spellings (fallback).
        spellings = self.merchant_name_spellings.get(key)
        if spellings:
            return spellings.most_common(1)[0][0]

        # 4. Prefix match in statement spellings.
        fallback_key = self._prefix_match_key(key)
        if fallback_key:
            spellings = self.merchant_name_spellings.get(fallback_key)
            if spellings:
                return spellings.most_common(1)[0][0]

        return None

    def _prefix_match_key_in(self, normalized_lookup: str, spellings_dict) -> Optional[str]:
        """Like _prefix_match_key but searches the keys of a given spellings dict."""
        candidates = []
        lookup_no_location = re.sub(r'\b[a-z]{2}\b$', '', normalized_lookup).strip()
        lookup_nospace = normalized_lookup.replace(' ', '')
        for key in spellings_dict:
            key_nospace = key.replace(' ', '')
            if normalized_lookup.startswith(key + ' ') or normalized_lookup == key:
                candidates.append((key, self.merchant_confidence.get(key, 0)))
            elif lookup_nospace.startswith(key_nospace) and len(key_nospace) >= 6:
                candidates.append((key, self.merchant_confidence.get(key, 0)))
            elif lookup_no_location and lookup_no_location.startswith(key + ' '):
                candidates.append((key, self.merchant_confidence.get(key, 0)))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (len(x[0]), x[1]), reverse=True)
        return candidates[0][0]

    def _prefix_match_key(self, normalized_lookup: str) -> Optional[str]:
        """
        Fallback: find the best history key that is a prefix of the normalized lookup.
        Handles cases where the LLM fails to split a concatenated name like
        'royalliquorsroundup' — 'royal liquors' is a valid prefix match.

        Also handles the reverse: lookup is a short form ('royal liquors') that
        matches a longer history key ('royal liquors roundup') — a prefix of
        the history key matches the lookup.

        Returns the matching history key with the highest confidence, or None.
        """
        candidates = []
        # Strip trailing location words (state codes, city fragments) from lookup
        lookup_no_location = re.sub(r'\b[a-z]{2}\b$', '', normalized_lookup).strip()
        # Also try without spaces (handles 'royalliquorsroundup' → match 'royal liquors')
        lookup_nospace = normalized_lookup.replace(' ', '')

        for key in self.merchant_categories:
            key_nospace = key.replace(' ', '')
            # History key is a prefix of lookup (e.g. "royal liquors" ⊆ "royal liquors roundup")
            if normalized_lookup.startswith(key + ' ') or normalized_lookup == key:
                candidates.append((key, self.merchant_confidence.get(key, 0)))
            # Lookup starts with history key when spaces stripped
            # (e.g. "royalliquorsroundup" starts with "royalliquors")
            elif lookup_nospace.startswith(key_nospace) and len(key_nospace) >= 6:
                candidates.append((key, self.merchant_confidence.get(key, 0)))
            # Location-stripped lookup matches key prefix
            elif lookup_no_location and lookup_no_location.startswith(key + ' '):
                candidates.append((key, self.merchant_confidence.get(key, 0)))

        if not candidates:
            return None
        # Pick the longest matching key (most specific), break ties by confidence
        candidates.sort(key=lambda x: (len(x[0]), x[1]), reverse=True)
        return candidates[0][0]

    def get_category(self, merchant_name: str) -> Optional[str]:
        """
        Get the historical category for a merchant.
        
        Args:
            merchant_name: The merchant/place name to lookup
            
        Returns:
            Category name if found in history, None otherwise
        """
        if not merchant_name:
            return None
        
        # Normalize for matching
        merchant_normalized = self._normalize_key(str(merchant_name).strip())

        # Exact match
        if merchant_normalized in self.merchant_categories:
            return self.merchant_categories[merchant_normalized]

        # Prefix/substring fallback for concatenated or extended names
        fallback_key = self._prefix_match_key(merchant_normalized)
        if fallback_key:
            return self.merchant_categories[fallback_key]

        return None
    
    def get_confidence(self, merchant_name: str) -> int:
        """
        Get the confidence level (number of occurrences) for a merchant.
        
        Args:
            merchant_name: The merchant/place name to lookup
            
        Returns:
            Number of times this merchant was seen with this category
        """
        if not merchant_name:
            return 0
        
        merchant_normalized = self._normalize_key(str(merchant_name).strip())
        return self.merchant_confidence.get(merchant_normalized, 0)
    
    def get_all_categories(self, merchant_name: str) -> Dict[str, int]:
        """
        Get all historical categories for a merchant with their counts.
        Useful for detecting when user changed their mind about categorization.
        
        Args:
            merchant_name: The merchant/place name to lookup
            
        Returns:
            Dictionary of {category: count} or empty dict
        """
        if not merchant_name:
            return {}
        
        merchant_normalized = self._normalize_key(str(merchant_name).strip())
        return dict(self.merchant_history.get(merchant_normalized, {}))
    
    def get_stats(self) -> Dict:
        """Get statistics about merchant history."""
        return {
            'total_merchants': len(self.merchant_categories),
            'high_confidence': sum(1 for c in self.merchant_confidence.values() if c >= 5),
            'medium_confidence': sum(1 for c in self.merchant_confidence.values() if 2 <= c < 5),
            'low_confidence': sum(1 for c in self.merchant_confidence.values() if c < 2),
        }
