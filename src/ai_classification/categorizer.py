"""
Transaction Categorization Module

Uses merchant history and AI to classify transactions into budget categories.
Category list is loaded from the config_categories database table.
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
import os
import re
import json
from pathlib import Path
import requests

_OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')

# Ollama is accessed directly via REST API (no SDK dependency)


class TransactionCategorizer:
    """Categorize transactions using pattern matching and AI."""
    
    def __init__(self, config_path: str = None, use_llm: bool = True, llm_host: str = None, merchant_history=None):
        """
        Initialize the categorizer.
        
        Args:
            config_path: Path to custom patterns file (optional, rarely needed)
            use_llm: Whether to use LLM for verification and fallback categorization (always True now)
            llm_host: Ollama server URL
            merchant_history: MerchantHistory instance for learning from past corrections (recommended)
        """
        llm_host = llm_host or _OLLAMA_HOST
        # Load valid categories and subcategories from config_categories DB table
        self.subcategories = {}   # parent → [subcategories]
        self.sub_to_parent = {}  # subcategory → parent
        try:
            from src.database.session import get_engine as _get_cat_engine
            from sqlalchemy import text as _cat_text
            with _get_cat_engine().connect() as _conn:
                _rows = _conn.execute(_cat_text(
                    'SELECT name, parent FROM config_categories ORDER BY sort_order, name'
                )).fetchall()
            valid_categories = [r[0] for r in _rows]
            for _name, _parent in _rows:
                if _parent:
                    self.subcategories.setdefault(_parent, []).append(_name)
                    self.sub_to_parent[_name] = _parent
            self.categories = {cat: [] for cat in valid_categories}
        except Exception:
            self.categories = {}
        
        # Optional patterns for keyword matching (rarely needed with merchant history)
        if config_path:
            pattern_categories = self._load_categories(config_path)
            # Merge with valid categories
            for cat, patterns in pattern_categories.items():
                if cat in self.categories:
                    self.categories[cat] = patterns
        
        self.use_llm = True  # Always use LLM
        self.llm_host = llm_host
        self.llm_available = False
        self.merchant_history = merchant_history  # Merchant history for learning
        
        # Load LLM model from config (no defaults)
        llm_config_path = Path(__file__).parent.parent.parent / 'config' / 'llm_models.json'
        if not llm_config_path.exists():
            raise FileNotFoundError(f"LLM config not found: {llm_config_path}")
        
        with open(llm_config_path, 'r') as f:
            llm_config = json.load(f)
        
        # Categorization uses primary_model only — ensembling is overkill
        # for a simple list-pick task and causes timeouts on large batches.
        self.llm_model = llm_config.get('primary_model')
        if not self.llm_model:
            raise ValueError("primary_model not specified in config/llm_models.json")
        
        # Verify model exists (don't fail if unavailable, just warn)
        self.llm_available = self._check_llm_availability()
    
    def _load_categories(self, config_path) -> dict:
        """Load category patterns from JSON file."""
        with open(config_path, 'r') as f:
            data = json.load(f)
            return data.get('categories', {})
    
    def _check_llm_availability(self) -> bool:
        """Check if Ollama LLM is available and the specified model exists."""
        try:
            response = requests.get(f"{self.llm_host}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                available_models = [m['name'] for m in models]
                
                # Check if our model is available
                if any(self.llm_model in name for name in available_models):
                    print(f"✓ LLM categorization enabled ({self.llm_model})")
                    return True
                else:
                    print(f"⚠ Model '{self.llm_model}' not found locally — attempting auto-pull...")
                    from statement_parser.llm_utils import ensure_model_pulled
                    pulled = ensure_model_pulled(self.llm_model, self.llm_host)
                    if pulled:
                        print(f"✓ LLM categorization enabled ({self.llm_model})")
                        return True
                    print(f"❌ Could not pull '{self.llm_model}' — falling back to pattern matching")
                    return False
        except Exception as e:
            print(f"❌ Cannot connect to Ollama at {self.llm_host}")
            return False

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
        
        result = self._get_category_from_model(merchant, amount, self.llm_model)
        
        if not result:
            print(f"  [LLM] Failed to categorize: {merchant}")
        
        return result

    def _extract_category_from_thinking(self, thinking_text: str) -> str:
        """
        Scan a thinking field for a valid category name.
        Handles reasoning models that write their answer mid-thought rather
        than to content.  Checks every line (not just the last few) and
        recognises common answer-prefix patterns.
        """
        valid_lower = {cat.lower(): cat for cat in self.categories.keys()
                       if cat not in self.subcategories}  # leaf categories only
        prefixes = ('answer:', 'category:', 'the category is:', 'the category:',
                    'so the answer is:', 'so the category is:', 'i would say:',
                    'my answer:', 'final answer:')

        # Scan reversed so the last mention wins (model may reconsider)
        for line in reversed(thinking_text.split('\n')):
            line = line.strip().strip('*').strip('_')
            if not line:
                continue

            # Check each period/semicolon-delimited clause in the line so we
            # don't miss "...blah blah. So the category is: Dining"
            clauses = [c.strip() for c in re.split(r'[.;]', line) if c.strip()]
            for clause in reversed(clauses):
                candidate = clause
                for prefix in prefixes:
                    if clause.lower().startswith(prefix):
                        candidate = clause[len(prefix):].strip().strip('"').strip("'")
                        break

                # Strip trailing punctuation
                candidate = candidate.strip('.,!?').strip()

                if candidate.lower() in valid_lower:
                    return valid_lower[candidate.lower()]

        return ''

    def _get_category_from_model(self, merchant: str, amount: float, model: str) -> Optional[str]:
        """Get category from a specific model."""
        # Only offer LEAF categories to the LLM — parent categories (those that have
        # subcategories) must never be chosen; the LLM should always pick the specific child.
        leaf_cats = [cat for cat in self.categories.keys() if cat not in self.subcategories]
        categories_numbered = "\n".join([f"{i+1}. {cat}" for i, cat in enumerate(leaf_cats)])

        # Disambiguation hints: explain what each parent group covers so the
        # model understands which leaf to pick.
        dynamic_hints = []
        for parent, subs in self.subcategories.items():
            subs_str = ', '.join(f'"{s}"' for s in subs)
            dynamic_hints.append(
                f'- For anything that is "{parent}", choose one of its specific subcategories: {subs_str}.'
            )
        subcategory_hints = "\n".join(dynamic_hints)

        # Create prompt demanding exact match with examples
        amount_context = f" (${amount:.2f})" if amount else ""
        prompt = f"""Task: Categorize this merchant into ONE category from the list below.

VALID CATEGORIES (choose EXACTLY one of these):
{categories_numbered}

Merchant to categorize: {merchant}{amount_context}

DISAMBIGUATION HINTS (use these to pick the right category when in doubt):
- "Alcohol/Bar": Breweries, taprooms, wineries, distilleries, bars, pubs, liquor stores — any place where the primary product is alcohol (even if food is also served).
- "Dining": Restaurants, cafes, fast food, coffee shops — places where the primary purpose is eating a meal.
- "Groceries": Grocery stores, supermarkets, and warehouse clubs — but NOT liquor stores.
- "Subscriptions": Streaming services, software subscriptions, and memberships — NOT gym memberships (use "Entertainment").
- "Shopping": General retail — use this when no more specific category fits.
{subcategory_hints}

Examples of CORRECT responses:
- Dining
- Shopping  
- Healthcare
- Subscriptions

Examples of INCORRECT responses (DO NOT USE):
- "Food & Dining" (wrong - use "Dining")
- "Health & Wellness" (wrong - use "Healthcare")
- "Electronics" (wrong - use "Shopping")
- "Software" (wrong - use "Subscriptions")

RESPOND WITH ONLY THE CATEGORY NAME FROM THE LIST ABOVE.
No explanations, no variations, just copy-paste the exact category.

Your answer:"""
        
        try:
            result = ''

            resp = requests.post(
                f'{self.llm_host}/api/chat',
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                    'think': False,
                    'options': {
                        'temperature': 0.1,
                        'num_predict': 1024,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
            response = resp.json()

            msg = response.get('message', {})
            result = (msg.get('content') or '').strip()
            thinking_text = (msg.get('thinking') or '').strip()

            # Check if result is actually reasoning text
            if result and any(phrase in result[:100].lower() for phrase in
                              ['okay, the user', 'let me think', 'let me look', 'i need to']):
                result = ''

            # Fallback: scan entire thinking field for a valid category name
            if not result and thinking_text:
                result = self._extract_category_from_thinking(thinking_text)
            
            if result:
                # Clean up result
                result = result.strip('"').strip("'").strip()
                
                # Take only first line
                if '\n' in result:
                    result = result.split('\n')[0].strip()
                
                # Remove common prefixes
                prefixes = ['answer:', 'category:', 'the category is:', 'i would categorize this as:']
                for prefix in prefixes:
                    if result.lower().startswith(prefix):
                        result = result[len(prefix):].strip()
                        break
                
                # Validate the category is in our list AND is a leaf (not a parent)
                if result in self.categories and result not in self.subcategories:
                    return result
                
                # Try case-insensitive match — also reject parents
                for valid_category in self.categories.keys():
                    if result.lower() == valid_category.lower() and valid_category not in self.subcategories:
                        return valid_category
                
                # Invalid category - try to find closest leaf match
                result_lower = result.lower()
                for valid_category in self.categories.keys():
                    if valid_category in self.subcategories:
                        continue  # skip parents
                    if result_lower in valid_category.lower() or valid_category.lower() in result_lower:
                        print(f"  [LLM] Mapped invalid '{result}' to '{valid_category}' for {merchant}")
                        return valid_category
                
                # No close match found
                print(f"  [LLM] Invalid category '{result}' for {merchant} from model {model} - no valid match found")
                return None
                
        except Exception as e:
            print(f"  [LLM] Error calling {model} for {merchant}: {type(e).__name__}: {str(e)}")
        
        return None

    def _categorize_batch_with_llm(
        self,
        merchants_amounts: List[tuple],
        batch_size: int = 8,
    ) -> Dict[str, Optional[str]]:
        """
        Send *batch_size* merchants to the LLM in a single call instead of one
        call per transaction.  On Ryzen 5/7 hardware a batch of 8 completes in
        roughly the same wall-clock time as 1–2 individual calls.

        Args:
            merchants_amounts: list of (merchant_name, amount_or_None) tuples
            batch_size: max items per LLM call (keep ≤ 10 for slower hardware)

        Returns:
            dict mapping merchant_name → category (or None on failure)
        """
        if not self.llm_available or not merchants_amounts:
            return {}

        leaf_cats = [cat for cat in self.categories.keys() if cat not in self.subcategories]
        categories_list = "\n".join(f"- {cat}" for cat in leaf_cats)

        results: Dict[str, Optional[str]] = {}

        # Process in chunks of batch_size
        for chunk_start in range(0, len(merchants_amounts), batch_size):
            chunk = merchants_amounts[chunk_start: chunk_start + batch_size]

            # Build numbered merchant list
            merchant_lines = "\n".join(
                f"{i + 1}. {merchant}"
                + (f" (${amount:.2f})" if amount else "")
                for i, (merchant, amount) in enumerate(chunk)
            )

            prompt = f"""Categorize each merchant into exactly one category from the list.
Reply with ONLY numbered lines: "N. CategoryName"
No explanations. No extra text. One line per merchant.

VALID CATEGORIES:
{categories_list}

MERCHANTS:
{merchant_lines}

Your response:"""

            try:
                resp = requests.post(
                    f'{self.llm_host}/api/chat',
                    json={
                        'model':    self.llm_model,
                        'messages': [{'role': 'user', 'content': prompt}],
                        'stream':   False,
                        'think':    False,
                        'options':  {
                            'temperature': 0.0,
                            'num_predict': 256,
                            'stop':        ['<|end|>', '<|im_end|>', '\n\n\n'],
                        },
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                msg     = resp.json().get('message', {})
                content = (msg.get('content') or '').strip()
                # Strip any residual thinking tags
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

                # Parse "N. CategoryName" lines
                for line in content.split('\n'):
                    line = line.strip()
                    m = re.match(r'^(\d+)[.)]\s*(.+)$', line)
                    if not m:
                        continue
                    idx = int(m.group(1)) - 1
                    if idx < 0 or idx >= len(chunk):
                        continue
                    merchant, _ = chunk[idx]
                    cat_raw     = m.group(2).strip().strip('"').strip("'")
                    # Validate against leaf categories (case-insensitive)
                    matched = next(
                        (c for c in leaf_cats if c.lower() == cat_raw.lower()),
                        None
                    )
                    # Partial match fallback
                    if not matched:
                        matched = next(
                            (c for c in leaf_cats
                             if cat_raw.lower() in c.lower() or c.lower() in cat_raw.lower()),
                            None
                        )
                    if matched:
                        results[merchant] = matched

            except Exception as exc:
                print(f"  [LLM batch] chunk starting at {chunk_start} failed: {exc}")

        return results

    def categorize_transaction(
        self,
        description: str,
        amount: float = None
    ) -> str:
        """
        Categorize a single transaction based on its description.
        Priority: 1) Merchant History 2) Keyword matching 3) LLM fallback
        
        Args:
            description: Transaction description text
            amount: Optional transaction amount for LLM context
            
        Returns:
            Category name or 'Uncategorized'
        """
        description_lower = description.lower()
        
        # PRIORITY 1: Check merchant history (learned from past corrections)
        if self.merchant_history:
            historical_category = self.merchant_history.get_category(description)
            if historical_category:
                # If history returned a parent category, refine to subcategory via LLM
                if historical_category in self.subcategories and self.llm_available:
                    refined = self._categorize_with_llm(description, amount)
                    if refined and refined in self.subcategories[historical_category]:
                        return refined
                return historical_category
        
        # PRIORITY 2: Try keyword matching from patterns
        for category, patterns in self.categories.items():
            for pattern in patterns:
                if pattern.lower() in description_lower:
                    return category
        
        # PRIORITY 3: If uncategorized and LLM is available, try LLM
        if self.llm_available:
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

        Applies merchant-history and keyword rules first (no LLM cost), then
        batches any remaining uncategorized rows through the LLM in groups of 8
        instead of one call per transaction.  Individual LLM fallback is used
        for any row the batch call cannot resolve.

        Args:
            df: DataFrame with transactions
            description_column: Name of column containing merchant names
            amount_column: Name of column containing amounts (for LLM context)
            
        Returns:
            DataFrame with added 'category' column
        """
        if description_column not in df.columns:
            raise ValueError(f"Column '{description_column}' not found in DataFrame")

        has_amount = amount_column in df.columns
        df = df.copy()

        # ── Pass 1: merchant-history + keyword matching (no LLM) ─────────────
        def _non_llm(row):
            merchant = row[description_column]
            merchant_lower = str(merchant).lower()
            # Merchant history
            if self.merchant_history:
                hist_cat = self.merchant_history.get_category(merchant)
                if hist_cat and hist_cat not in self.subcategories:
                    return hist_cat
            # Keyword patterns
            for category, patterns in self.categories.items():
                for pattern in patterns:
                    if pattern.lower() in merchant_lower:
                        return category
            return None  # needs LLM

        df['category'] = df.apply(_non_llm, axis=1)

        # ── Pass 2: batch LLM for uncategorized rows ──────────────────────────
        if self.llm_available:
            needs_llm = df['category'].isna()
            if needs_llm.any():
                uncategorized_idx = df.index[needs_llm].tolist()
                merchants_amounts = [
                    (
                        df.at[idx, description_column],
                        float(df.at[idx, amount_column]) if has_amount else None,
                    )
                    for idx in uncategorized_idx
                ]
                batch_results = self._categorize_batch_with_llm(merchants_amounts)

                still_missing = []
                for idx in uncategorized_idx:
                    merchant = df.at[idx, description_column]
                    if merchant in batch_results and batch_results[merchant]:
                        df.at[idx, 'category'] = batch_results[merchant]
                    else:
                        still_missing.append(idx)

                # ── Pass 3: individual fallback for any batch misses ──────────
                for idx in still_missing:
                    merchant = df.at[idx, description_column]
                    amount   = float(df.at[idx, amount_column]) if has_amount else None
                    cat      = self._categorize_with_llm(merchant, amount)
                    if cat:
                        df.at[idx, 'category'] = cat

        df['category'] = df['category'].fillna('Uncategorized')
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
            month: Optional month identifier (e.g., 'YYYY-MM') to display in report
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
        
        if self.llm_available:
            print("LLM enhancement: ✓ Enabled (used for uncategorized items)")
        else:
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
                print("  Edit the category in the 'All Transactions' tab — the system learns from your corrections!")
            else:
                print("\n💡 To categorize these:")
                print("  Edit the category in the 'All Transactions' tab in the dashboard.")
                print("  The system learns from your corrections and auto-categorizes matching merchants next time.")
                if not self.llm_available:
                    print("  OR: Run 'make ollama-serve' then re-process for AI-powered categorization")
        else:
            print("\n✓ All transactions successfully categorized!")
        
        print("="*60 + "\n")
