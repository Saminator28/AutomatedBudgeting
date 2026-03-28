#!/usr/bin/env python3
"""
Clean PDF statement parser with LLM merchant name cleaning.
"""

import hashlib
import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json
import sys

from .llm_utils import clean_merchant_with_ensemble
from .pdf_extractor import extract_text_from_pdf, validate_transactions

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# US + Canadian state/province abbreviations — stripped from description tails before LLM
_STATE_ABBREVS = frozenset({
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI',
    'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT',
})


class StatementParser:
    """
    PDF statement parser with LLM merchant name cleaning.
    
    Features:
    - pdfplumber text extraction
    - Multi-line transaction parsing with date error correction
    - LLM merchant name cleaning with multi-model ensemble
    - Automatic bank detection and transaction classification
    """
    
    def __init__(self, config_dir: Path = None):
        """
        Initialize parser with config directory.
        
        Raises:
            ValueError: If primary_model is not specified in llm_models.json
        """
        if config_dir:
            self.config_dir = config_dir
        else:
            # Try to find config directory relative to this file
            self.config_dir = Path(__file__).parent.parent.parent / 'config'
            if not self.config_dir.exists():
                # If running from project root
                self.config_dir = Path('config')
        
        # Load keyword lists from DB (inline sqlite3, same pattern as detect_bank_name)
        import sqlite3 as _sqlite3
        from pathlib import Path as _KWPath
        _kw_db = _KWPath(__file__).parent.parent / 'ui' / 'data' / 'budget.db'
        try:
            # Ensure the DB and its tables exist before querying
            _db_root = _KWPath(__file__).parent.parent.parent
            import sys as _sys
            _sys.path.insert(0, str(_db_root))
            try:
                from src.database.session import init_db as _init_db
                _init_db()
            except Exception:
                pass  # init_db unavailable; DB may already exist or will fall through below
            _con = _sqlite3.connect(_kw_db)
            self.income_keywords   = [r[0].upper() for r in _con.execute('SELECT keyword FROM income_keywords').fetchall()]
            self.transfer_keywords = [r[0].upper() for r in _con.execute('SELECT keyword FROM transfer_keywords').fetchall()]
            self.payment_apps      = [r[0].upper() for r in _con.execute('SELECT keyword FROM payment_app_keywords').fetchall()]
            self.ignore_keywords   = [r[0].upper() for r in _con.execute('SELECT keyword FROM ignore_keywords').fetchall()]
            _con.close()
        except Exception as _kw_exc:
            print(f"⚠ Could not load keywords from DB ({_kw_exc}). Keyword matching will be limited.")
            self.income_keywords   = []
            self.transfer_keywords = []
            self.payment_apps      = []
            self.ignore_keywords   = []
        
        # Load LLM model configuration - STRICT VALIDATION (no defaults)
        llm_config_file = self.config_dir / 'llm_models.json'
        if not llm_config_file.exists():
            raise ValueError(
                f"❌ LLM configuration file not found: {llm_config_file}\n"
                f"   Please create config/llm_models.json with your model settings."
            )
        
        try:
            with open(llm_config_file) as f:
                llm_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"❌ Invalid JSON in {llm_config_file}: {e}")
        
        # REQUIRED: primary_model must be specified
        self.primary_model = llm_config.get('primary_model')
        if not self.primary_model:
            raise ValueError(
                f"❌ Primary LLM model not found in config!\n"
                f"   Please add 'primary_model' to {llm_config_file}\n"
                f"   Example: {{\"primary_model\": \"gpt-oss:20b\"}}"
            )
        
        # OPTIONAL: secondary_model for ensemble (skip cross-checking if not provided)
        self.secondary_model = llm_config.get('secondary_model')
        self.use_multi_model = llm_config.get('use_multi_model', True)
        
        # If secondary model not specified, disable multi-model
        if not self.secondary_model:
            self.use_multi_model = False
        
        print(f"  LLM Configuration:")
        print(f"    Primary model: {self.primary_model}")
        if self.secondary_model and self.use_multi_model:
            print(f"    Secondary model: {self.secondary_model} (ensemble enabled)")
        else:
            print(f"    Secondary model: None (single model mode)")
        
        # Historical cache for merchant names (improves consistency)
        self.merchant_cache = {}   # UPPER(cleaned) -> cleaned
        self.merchant_frequency = {}  # cleaned -> frequency count
        # Fingerprint caches built from statement + monthly_reports CSVs
        self.raw_to_clean_cache = {}   # normalize(Place_Original) -> Place
        self.clean_name_fp = {}        # normalize(Place) -> Place (for prefix lookup)
        self._load_user_corrections_from_csvs()  # Load from CSV files


    
    @staticmethod
    def _institution_fingerprint(header_text: str) -> str:
        """Stable 16-char hex key for the same account across statement months.

        Strips dates and dollar amounts (the only parts that change month-to-month)
        before hashing, so January and February statements for the same card produce
        the same key.
        """
        s = header_text
        # Strip dates: MM/DD/YY, MM/DD/YYYY
        s = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '', s)
        # Strip written dates: "January 2026", "Jan. 31, 2026" etc.
        s = re.sub(
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b',
            '', s, flags=re.IGNORECASE
        )
        # Strip dollar amounts
        s = re.sub(r'\$[\d,]+\.\d{2}', '', s)
        # Normalise whitespace; take first 1000 chars
        s = re.sub(r'\s+', ' ', s).strip()[:1000]
        return hashlib.md5(s.encode()).hexdigest()[:16]

    def _load_config(self, filename: str, key: str):
        """Load configuration from JSON file."""
        config_file = self.config_dir / filename
        if not config_file.exists():
            print(f"⚠ Config not found: {filename}")
            return {} if 'patterns' in key else []
        
        try:
            with open(config_file) as f:
                data = json.load(f)
                result = data.get(key, {})
                return result if result else ({} if 'patterns' in key else [])
        except Exception as e:
            print(f"⚠ Error loading {filename}: {e}")
            return {} if 'patterns' in key else []
    
    @staticmethod
    def _normalize_raw(s: str) -> str:
        """Strip all non-alphanumeric characters and lowercase — used as a fingerprint
        for matching raw transaction text against known merchant clean names.

        Key property: normalize("Royal Liquors Roundup") == "royalliquorsroundup",
        which is a prefix of normalize("ROYALLIQUORSROUNDUP SAL FARGO ND").
        normalize("Royall Liquors Roundup") == "royallliquorsroundup" (three l's),
        which is NOT a prefix — so the wrong LLM spelling never matches.
        """
        return re.sub(r'[^a-z0-9]', '', s.lower())

    @staticmethod
    def _presplit_merged_tokens(text: str) -> str:
        """Split all-uppercase tokens that look like concatenated words using wordninja.

        Targets tokens that are ALL-CAPS, contain no digits, and are ≥ 10 characters
        — the signature of a merged merchant name from a PDF with no inter-word spaces.

        Example:
          THECOFFEEHOUSE       → THE COFFEE HOUSE

        Tokens under the 10-char threshold (WALMART, WHOLEFDS …) are left
        alone — they are recognisable brand abbreviations, not concatenated phrases.
        Silently returns the original text unchanged if wordninja is not installed.
        """
        try:
            import wordninja as _wn
        except ImportError:
            return text

        parts = []
        for token in text.split():
            if re.match(r'^[A-Z]{10,}$', token):
                split_parts = _wn.split(token)
                parts.append(' '.join(p.upper() for p in split_parts))
            else:
                parts.append(token)
        return ' '.join(parts)

    @staticmethod
    def _strip_alpha_digit_suffix(text: str) -> str:
        """Remove account-number suffixes fused directly to a merchant prefix.

        Some PDFs encode merchant + transaction ID as one token with no separator:
          OIL10006676018  → OIL
          SP1234567890    → SP

        Pattern: 2+ uppercase letters immediately followed by 8+ digits.
        Tokens that do not match are returned unchanged (so '7ELEVEN' is safe).
        """
        _ALPHA_DIGITS = re.compile(r'^([A-Z]{2,})(\d{8,})$')
        parts = []
        for token in text.split():
            m = _ALPHA_DIGITS.match(token)
            parts.append(m.group(1) if m else token)
        return ' '.join(parts)

    def _load_user_corrections_from_csvs(self):
        """Load user's manual corrections from all statement CSVs with frequency tracking."""
        # Find statements directory relative to this file's location
        statements_dir = Path(__file__).parent.parent.parent / 'src' / 'ui' / 'data' / 'statements'
        
        if not statements_dir.exists():
            return
        
        corrections_loaded = 0
        csv_files_scanned = 0
        merchant_counts = {}
        from collections import Counter as _Counter, defaultdict as _defaultdict
        raw_to_clean_votes = _defaultdict(_Counter)  # normalize(Place_Original) -> {Place: count}
        
        # Scan all month directories
        for month_dir in sorted(statements_dir.glob('20*-*')):
            if not month_dir.is_dir():
                continue
            
            # Check both expenses.csv and income.csv
            for csv_file in ['expenses.csv', 'income.csv']:
                csv_path = month_dir / csv_file
                if not csv_path.exists():
                    continue
                
                try:
                    df = pd.read_csv(csv_path)
                    csv_files_scanned += 1
                    
                    # Count frequency of each merchant name
                    if 'Place' in df.columns:
                        for place in df['Place'].dropna():
                            place = str(place).strip()
                            if len(place) >= 3 and place != 'nan':
                                merchant_counts[place] = merchant_counts.get(place, 0) + 1
                                # Register clean-name fingerprint (statements, lower priority)
                                fp = self._normalize_raw(place)
                                if fp and fp not in self.clean_name_fp:
                                    self.clean_name_fp[fp] = place

                    # Build raw-original → clean-name vote table
                    if 'Place_Original' in df.columns and 'Place' in df.columns:
                        for raw, clean in zip(
                            df['Place_Original'].astype(str).str.strip(),
                            df['Place'].astype(str).str.strip()
                        ):
                            if raw and clean and raw != 'nan' and clean != 'nan' and len(clean) >= 3:
                                raw_to_clean_votes[self._normalize_raw(raw)][clean] += 1
                except Exception:
                    pass

        # Second pass: monthly_reports — these are user-corrected names (higher priority)
        monthly_reports_dir = statements_dir.parent / 'monthly_reports'
        if monthly_reports_dir.exists():
            for rpt_file in sorted(monthly_reports_dir.glob('expenses_????-??.csv')):
                try:
                    df_rpt = pd.read_csv(rpt_file)
                    if 'Place' in df_rpt.columns:
                        for place in df_rpt['Place'].dropna():
                            place = str(place).strip()
                            if len(place) >= 3 and place != 'nan':
                                merchant_counts[place] = merchant_counts.get(place, 0) + 1
                                # Monthly_reports names OVERRIDE statements in the fingerprint dict
                                fp = self._normalize_raw(place)
                                if fp:
                                    self.clean_name_fp[fp] = place
                except Exception:
                    pass

        # Resolve raw→clean cache: majority vote wins across all months
        self.raw_to_clean_cache = {
            fp: votes.most_common(1)[0][0]
            for fp, votes in raw_to_clean_votes.items()
            if votes
        }

        # Store unique merchants with frequency data
        for place, count in merchant_counts.items():
            cache_key = place.upper().strip()
            if cache_key not in self.merchant_cache or self.merchant_cache[cache_key] != place:
                self.merchant_cache[cache_key] = place
                corrections_loaded += 1
            self.merchant_frequency[place] = count
        
        if corrections_loaded > 0 and csv_files_scanned > 0:
            high_confidence = sum(1 for c in merchant_counts.values() if c >= 5)
            medium_confidence = sum(1 for c in merchant_counts.values() if 2 <= c < 5)
            low_confidence = sum(1 for c in merchant_counts.values() if c == 1)
            
            print(f"  Loaded {corrections_loaded} merchants from {csv_files_scanned} CSV files")
            print(f"     High confidence (5+ occurrences): {high_confidence}")
            print(f"     Medium confidence (2-4): {medium_confidence}")
            print(f"     Low confidence (1): {low_confidence}")
            print(f"     Raw→clean cache: {len(self.raw_to_clean_cache)} entries, "
                  f"name fingerprints: {len(self.clean_name_fp)}")
    
    def extract_statement_year(self, text: str) -> int:
        """Extract the statement year from PDF text."""
        text_lower = text.lower()
        
        patterns = [
            r'(?:billing cycle|statement).*?ending.*?\d{1,2}/\d{1,2}/(\d{4})',
            r'statement closing date.*?\d{1,2}/\d{1,2}/(\d{2,4})',
            r'statement date.*?\d{1,2}/\d{1,2}/(\d{4})',
            r'forbilling cycleending \d{1,2}/\d{1,2}/(\d{2})',
            r'for billing cycle ending \d{1,2}/\d{1,2}/(\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                year_str = match.group(1)
                if len(year_str) == 2:
                    return 2000 + int(year_str)
                else:
                    return int(year_str)
        
        # Use statement year passed from parse_pdf if available
        if hasattr(self, 'statement_year') and self.statement_year:
            return self.statement_year
        
        return datetime.now().year
    
    def is_credit_card(self, text: str) -> bool:
        """Determine if statement is credit-card or deposit-account using generic indicators."""
        text_upper = text.upper()

        bank_indicators = [
            'CHECKING', 'SAVINGS', 'ACCOUNT ACTIVITY', 'BEGINNING BALANCE',
            'ENDING BALANCE', 'AVAILABLE BALANCE', 'DEPOSIT',
        ]
        card_indicators = [
            'CREDIT CARD', 'CARD ACCOUNT', 'STATEMENT CLOSING',
            'MINIMUM PAYMENT DUE', 'PAYMENT DUE', 'PREVIOUS BALANCE',
            'NEW BALANCE', 'CREDIT LIMIT', 'INTEREST CHARGED',
        ]

        bank_score = sum(1 for marker in bank_indicators if marker in text_upper)
        card_score = sum(1 for marker in card_indicators if marker in text_upper)

        # Tie-breaks using common statement table headers
        if card_score == bank_score:
            if 'PURCHASE APR' in text_upper or 'LATE PAYMENT WARNING' in text_upper:
                card_score += 1
            if 'DAILY BALANCE' in text_upper or 'DIRECT DEPOSIT' in text_upper:
                bank_score += 1

        return card_score > bank_score
    
    def detect_bank_name(self, text: str) -> str:
        """Identify the issuing institution using the LLM with a DB-backed cache.

        The institution_cache table is keyed by a stable header fingerprint so the
        same account always returns the same name regardless of which month's
        statement is being parsed.
        """
        import sqlite3
        from pathlib import Path as _Path

        lines = text.split('\n')
        header_lines = [re.sub(r'\s+', ' ', ln).strip() for ln in lines[:80] if ln.strip()]
        header_text = ' '.join(header_lines)
        fp = self._institution_fingerprint(header_text)

        db_path = _Path(__file__).parent.parent / 'ui' / 'data' / 'budget.db'
        try:
            con = sqlite3.connect(db_path)
            row = con.execute(
                'SELECT institution_name FROM institution_cache WHERE header_fp=?', (fp,)
            ).fetchone()
            if row:
                if getattr(self, 'debug', False):
                    print(f'  [institution] DB cache hit: {repr(row[0])}')
                con.close()
                return row[0]
        except Exception:
            con = None

        # Not cached — ask the LLM
        from .llm_utils import detect_institution_with_llm
        name = detect_institution_with_llm(
            header_text,
            model=self.primary_model,
            debug=getattr(self, 'debug', False),
        )
        if name and con is not None:
            try:
                con.execute(
                    'INSERT OR REPLACE INTO institution_cache (header_fp, institution_name) VALUES (?,?)',
                    (fp, name)
                )
                con.commit()
            except Exception:
                pass

        if con is not None:
            con.close()

        if name:
            return name

        # Minimal fallback
        text_upper = text.upper()
        if any(n in text_upper for n in ['VISA', 'MASTERCARD', 'AMEX', 'DISCOVER', 'CREDIT CARD']):
            return 'Card Issuer'
        return 'Unknown Institution'
    
    def _fix_date_parsing_errors(self, date_str: str) -> str:
        """Fix common date parsing errors from PDF extraction."""
        if not date_str or '/' not in date_str:
            return date_str
        
        parts = date_str.split('/')
        if len(parts) < 2:
            return date_str
        
        try:
            month = int(parts[0])
            
            if month > 12:
                corrections = {
                    42: 12, 41: 11, 40: 10, 14: 11, 13: 11
                }
                
                if month in corrections:
                    corrected_month = corrections[month]
                    parts[0] = str(corrected_month).zfill(2 if month >= 10 else 1)
                    return '/'.join(parts)
                
                if month // 10 > 1:
                    second_digit = month % 10
                    if second_digit <= 2:
                        corrected_month = 10 + second_digit
                        parts[0] = str(corrected_month)
                        return '/'.join(parts)
        except (ValueError, IndexError):
            pass
        
        return date_str
    
    def _build_transaction(self, date: str, description: str, amounts: List[float]) -> Dict:
        """Build transaction dict from parsed components."""
        description = ' '.join(description.split()).strip()
        
        # Remove common bank marketing messages/slogans (before any other processing)
        marketing_patterns = [
            r"^I'M Ready When You Are!\s+",
            r"^We're Here For You!?\s+",
            r"^Thank You For Banking With Us!?\s+",
            r"^Banking Made Easy!?\s+",
            r"^Your Local Bank!?\s+",
        ]
        for pattern in marketing_patterns:
            description = re.sub(pattern, '', description, flags=re.IGNORECASE).strip()
        
        # Check ignore list FIRST (before any other processing)
        desc_upper = description.upper()
        for ignore_keyword in self.ignore_keywords:
            if ignore_keyword in desc_upper:
                return None  # Ignore this transaction completely
        
        # Filter out garbage descriptions
        garbage_patterns = [
            'DATE AMOUNT', 'DATE DESCRIPTION AMOUNT', 'DESCRIPTION AMOUNT DESCRIPTION AMOUNT',
            'DESCRIPTION DEBITS CREDITS', 'POST DATE', 'TRANS DATE', 'REFERENCE', 'PAGE',
            'ACCOUNT STATEMENTS', 'STATEMENT ENDING', 'CUSTOMER NUMBER', 'CHECKING ACCOUNT',
            'SAVINGS ACCOUNT', 'DAILY BALANCE', 'DATE AMOUNT DATE AMOUNT', 
            'BEGINNING BALANCE', 'ENDING BALANCE', 'DEBIT(S) THIS PERIOD', 'CREDIT(S) THIS PERIOD',
            'INTEREST DAYS', 'INTEREST EARNED THIS', 'ANNUAL PERCENTAGE YIELD'
        ]
        
        for pattern in garbage_patterns:
            if pattern in desc_upper:
                return None
        
        # Filter out fragments
        words = description.split()
        if len(words) == 1 and len(description) < 4:
            return None
        
        if len(description) < 3 or not any(c.isalpha() for c in description):
            return None
        
        original_description = description
        
        # Clean up statement-specific reward/summary formatting
        original_description = re.sub(r'\s+last statement\s+\.+\s*\+?\$[\d,]+\.\d{2}', '', original_description, flags=re.IGNORECASE)
        original_description = re.sub(r'\.{3,}', '', original_description)
        original_description = re.sub(r'\s+\+\$[\d,]+\.\d{2}', '', original_description)
        original_description = re.sub(r'\s*[»›]\s*Visit.*$', '', original_description, flags=re.IGNORECASE)
        original_description = re.sub(r'\s*\d+%.*earn.*$', '', original_description, flags=re.IGNORECASE)
        original_description = ' '.join(original_description.split()).strip()
        
        amount = amounts[0] if amounts else None
        
        # Check if this is a transfer BEFORE sending to LLM
        desc_upper = description.upper()
        is_transfer = any(keyword in desc_upper for keyword in self.transfer_keywords)
        
        # Check if this is a bare WITHDRAWAL (no merchant name)
        is_bare_withdrawal = desc_upper.strip() == 'WITHDRAWAL'
        
        # Check if this is a known bank operation that the LLM can't improve on
        # These all map directly to a canonical name without LLM involvement.
        _BANK_OPS = {
            'MOBILE DEPOSIT':  'Mobile Deposit',
            'DIRECT DEPOSIT':  'Direct Deposit',
            'ACH DEPOSIT':     'ACH Deposit',
            'COUNTER DEPOSIT': 'Counter Deposit',
            'NIGHT DEPOSIT':   'Night Deposit',
        }
        matched_bank_op = next(
            (canonical for keyword, canonical in _BANK_OPS.items() if desc_upper.startswith(keyword)),
            None
        )
        
        # Check if this is an ATM withdrawal (but NOT if there's a merchant name before it)
        # E.g., "XX8934 ATM WITHDRAWAL" → Yes
        desc_clean = re.sub(r'^XX\d+\s+', '', desc_upper).strip()
        is_atm_withdrawal = desc_clean.startswith('ATM WITHDRAWAL') and not is_bare_withdrawal
        
        if getattr(self, 'debug', False) and 'WITHDRAWAL' in desc_upper:
            print(f"  [WITHDRAWAL CHECK] description='{description}', is_bare={is_bare_withdrawal}, is_atm={is_atm_withdrawal}")
        
        # Track if we manually cleaned the description (to skip validation later)
        manually_cleaned = False
        
        # Check if description contains a payment app keyword BEFORE calling LLM.
        # e.g. "XX4297 POS PURCHASE AT CASH APP* SAMUEL SC P71" → "Cash App"
        #      "Cash App * Cash App T3HVKSWHERSWMX4"            → "Cash App"
        # Using the app name directly is more reliable than letting the LLM extract
        # "Samuel" or another fragment as the merchant.
        matched_payment_app = None
        for app_keyword in self.payment_apps:
            if app_keyword in desc_upper:
                # Normalise to title-case (e.g. "CASH APP" → "Cash App")
                matched_payment_app = app_keyword.title()
                break

        # Only clean with LLM if it's NOT a transfer and NOT a special withdrawal type
        if is_transfer:
            description = description.title()
            manually_cleaned = True
        elif matched_payment_app:
            description = matched_payment_app
            manually_cleaned = True
        elif matched_bank_op:
            # Known bank operation — use canonical name directly (LLM can't improve on it)
            description = matched_bank_op
            manually_cleaned = True
        elif is_bare_withdrawal:
            # Keep bare "WITHDRAWAL" as "Withdrawal" (LLM often fails on this)
            description = "Withdrawal"
            manually_cleaned = True
        elif is_atm_withdrawal:
            # Standardize ATM withdrawals
            description = "ATM Withdrawal"
            manually_cleaned = True
        else:
            description = self._clean_merchant_name_with_llm(description, amount, date)
        
        trans = {
            'Transaction Date': date,
            'Place': description,
            'Place_Original': original_description,
            '_statement_beginning_balance': getattr(self, '_beginning_balance', None)  # Store beginning balance with transaction
        }
        
        # If LLM failed to clean (Place == Place_Original), set Place to empty
        # This indicates the name needs manual review/cleaning
        # Skip this check if we manually cleaned the description
        if not manually_cleaned and trans['Place'].strip().upper() == trans['Place_Original'].strip().upper():
            trans['Place'] = ''
        
        # Assign amounts
        if len(amounts) == 1:
            trans['Amount'] = amounts[0]
        elif len(amounts) == 2:
            if hasattr(self, '_has_debit_credit_columns') and self._has_debit_credit_columns:
                # For Debits/Credits columns, if we only have 2 amounts:
                # amounts[0] = the transaction amount (either debit OR credit)
                # amounts[1] = the running balance
                # We can't tell if it's a debit or credit from just the amount,
                # so use Amount column and let classification logic handle it
                trans['Amount'] = amounts[0]
                trans['Balance'] = amounts[1]  # Store balance for later classification
                
                # Debug logging
                if hasattr(self, 'debug') and self.debug and ('FOCUS' in original_description.upper() or 'WITHDRAWAL' in original_description.upper() or 'INVEST' in original_description.upper()):
                    print(f"  [ASSIGN] {original_description[:40]:40s}: Amount=${amounts[0]}, Balance=${amounts[1]}")
            else:
                # Standard format: amounts[0] = transaction, amounts[1] = balance
                trans['Amount'] = amounts[0]
                trans['Balance'] = amounts[1]
        elif len(amounts) >= 3:
            # When we have 3+ amounts, we can properly separate:
            # amounts[0] = Debits, amounts[1] = Credits, amounts[2] = Balance
            # Determine which column has the actual transaction (non-zero value)
            debit_val = amounts[0] if amounts[0] > 0 else None
            credit_val = amounts[1] if amounts[1] > 0 else None
            
            # Assign only the non-zero amount to avoid ambiguity
            if debit_val and not credit_val:
                trans['Debits'] = debit_val
                trans['Credits'] = None
            elif credit_val and not debit_val:
                trans['Debits'] = None
                trans['Credits'] = credit_val
            elif debit_val and credit_val:
                # Both have values - this shouldn't happen normally
                # Use Amount column and let balance comparison handle it
                trans['Amount'] = debit_val  # Assume debit is the transaction
                trans['Balance'] = amounts[2]
            else:
                # Neither has value - skip this transaction
                return None
            
            # Store balance (always the last amount)
            if 'Debits' in trans or 'Credits' in trans:
                trans['Balance'] = amounts[2]
        
        return trans
    
    def _strip_trailing_state(self, name: str) -> str:
        """Remove trailing US/Canadian state or province abbreviation from a description.

        Handles two cases:
          1. Space-separated: "Merchant Name City ST" → "Merchant Name City"
          2. Concatenated to city:  "Merchant Name CITYST" → "Merchant Name CITY"
        """
        parts = name.split()

        # Pass 1: drop tokens that ARE exactly a state/province abbreviation
        while parts and parts[-1].upper() in _STATE_ABBREVS:
            parts.pop()

        # Pass 2: strip a state abbreviation fused to the end of the last token
        # e.g. "CITYST" → "CITY" (suffix ST, prefix CITY ≥ 4 chars)
        if parts:
            last = parts[-1]
            suffix = last[-2:].upper()
            prefix = last[:-2]
            if suffix in _STATE_ABBREVS and len(prefix) >= 4:
                parts[-1] = prefix
                if not parts[-1].strip():
                    parts.pop()

        return ' '.join(parts) if parts else name

    def _find_clean_name_by_fp_prefix(self, raw_fp: str, min_key_len: int = 10) -> Optional[str]:
        """Return the clean name whose fingerprint is the longest prefix of raw_fp.
        Requires the matching key to be at least min_key_len chars to avoid false positives.
        """
        best_key = ''
        for key in self.clean_name_fp:
            if len(key) >= min_key_len and raw_fp.startswith(key) and len(key) > len(best_key):
                best_key = key
        return self.clean_name_fp[best_key] if best_key else None

    def _find_relevant_known_names(self, raw_fp: str, prefix_len: int = 6, max_results: int = 6) -> list:
        """Return known clean names that share the first prefix_len chars of raw_fp."""
        prefix = raw_fp[:prefix_len]
        seen = set()
        results = []
        for key, name in self.clean_name_fp.items():
            if key.startswith(prefix) and name not in seen:
                seen.add(name)
                results.append(name)
                if len(results) >= max_results:
                    break
        return results

    def _clean_merchant_name_with_llm(self, name: str, amount: float = None, date: str = None) -> str:
        """
        Clean merchant name using LLM with multi-model ensemble if configured.
        """
        if not name or len(name) < 3:
            return name

        # Strip trailing state/province abbreviation before sending to LLM
        # (e.g. "MERCHANT NAME City ST" → "MERCHANT NAME City")
        name = self._strip_trailing_state(name)

        if not name or len(name) < 3:
            return name

        raw_fp = self._normalize_raw(name)

        # 1. Exact raw-original match — we've cleaned this exact transaction text before.
        cached = self.raw_to_clean_cache.get(raw_fp)
        if cached:
            return cached

        # 2. Clean-name fingerprint prefix match.
        #    normalize("Royal Liquors Roundup") = "royalliquorsroundup" which is a
        #    prefix of normalize("ROYALLIQUORSROUNDUP SAL FARGO"). This resolves
        #    concatenated-word ambiguity without calling the LLM.
        fp_match = self._find_clean_name_by_fp_prefix(raw_fp)
        if fp_match:
            return fp_match

        # 3. Pre-process before LLM:
        #    a) Strip account-number suffixes fused to merchant prefixes
        #       e.g. "OIL10006676018" → "OIL"
        #    b) Split all-uppercase merged tokens using wordninja
        #       e.g. "ROYALLIQUORSROUNDUP" → "ROYAL LIQUORS ROUNDUP"
        #    These steps make the LLM input significantly more legible for genuinely
        #    new merchants that aren't yet in the fingerprint cache.
        name = self._strip_alpha_digit_suffix(name)
        name = self._presplit_merged_tokens(name)

        # 4. LLM — pass nearby known names as in-context examples so the model
        #    produces consistent output for similar-looking raw texts.
        known_names = self._find_relevant_known_names(raw_fp)

        # Use ensemble if secondary model is configured
        secondary = self.secondary_model if self.use_multi_model else None
        
        cleaned = clean_merchant_with_ensemble(
            merchant=name,
            primary_model=self.primary_model,
            secondary_model=secondary,
            amount=amount,
            date=date,
            known_names=known_names or None,
            debug=hasattr(self, 'debug') and self.debug
        )
        
        return cleaned if cleaned else name
    
    def parse_transaction_block(self, lines: List[str], start_idx: int, statement_year: int = None) -> Tuple[Optional[Dict], int]:
        """
        Parse a transaction that may span multiple lines.
        
        Handles complex patterns:
        1. Simple: "MM/DD/YYYY MERCHANT NAME $100.00 $1,000.00"
        2. Two date format: "12/31/24 12/31/24 REF# MERCHANT NAME 37.62"
        3. Split description before amounts
        4. Description after date
        5. Retail-card style format (MM-DD with 2-line transaction)
        
        Returns:
            (transaction_dict or None, lines_consumed)
        """
        if statement_year is None:
            # Use statement year passed from parse_pdf if available
            if hasattr(self, 'statement_year') and self.statement_year:
                statement_year = self.statement_year
            else:
                statement_year = datetime.now().year
            
        if start_idx >= len(lines):
            return None, 0
        
        current_line = lines[start_idx].strip()
        if not current_line:
            return None, 1

        # Normalise lines where two MM/DD dates (and optionally the description) are
        # concatenated without spaces, e.g. "01/2401/24TST*MERCHANT ..." → "01/24 01/24 TST*MERCHANT ..."
        # Step 1: split two back-to-back no-year dates
        current_line = re.sub(r'^(\d{1,2}/\d{2})(\d{1,2}/\d{2})', r'\1 \2 ', current_line)
        # Step 2: insert space between a no-year date and immediately following non-digit text
        #         e.g. "01/24TST*" → "01/24 TST*"  (skips MM/DD/YYYY to avoid splitting the year)
        current_line = re.sub(r'(\d{1,2}/\d{2})(?=[^\s/\d])', r'\1 ', current_line)
        current_line = ' '.join(current_line.split())  # collapse any double spaces

        # Check for date patterns
        date_pattern_long = r'^(\d{1,2}/\d{1,2}/\d{4})'
        date_pattern_short = r'^(\d{1,2}/\d{1,2}/\d{2})'
        date_pattern_dash = r'^(\d{1,2}-\d{1,2})\s'
        date_pattern_no_year = r'^(\d{1,2}/\d{1,2})\s'
        
        date_match = re.match(date_pattern_long, current_line)
        trans_date = None
        
        if not date_match:
            date_match = re.match(date_pattern_short, current_line)
            if date_match:
                date_parts = date_match.group(1).split('/')
                trans_date = f"{date_parts[0]}/{date_parts[1]}/20{date_parts[2]}"
            else:
                date_match = re.match(date_pattern_dash, current_line)
                if date_match:
                    date_str = date_match.group(1)
                    month_day = date_str.replace('-', '/')
                    trans_date = f"{month_day}/{statement_year}"
                else:
                    date_match = re.match(date_pattern_no_year, current_line)
                    if date_match:
                        trans_date = f"{date_match.group(1)}/{statement_year}"
        else:
            trans_date = date_match.group(1)
        
        # Fix date parsing errors
        if trans_date:
            trans_date = self._fix_date_parsing_errors(trans_date)
        
        if date_match:
            rest = current_line[date_match.end():].strip()
            
            # Check for second date
            second_date_match = (re.match(date_pattern_short, rest) or 
                                re.match(date_pattern_long, rest) or
                                re.match(date_pattern_dash, rest) or
                                re.match(date_pattern_no_year, rest))
            if second_date_match:
                rest = rest[second_date_match.end():].strip()
            
            # Check for reference number
            ref_match = re.match(r'^(\d{17,})\s+', rest)
            if ref_match:
                rest = rest[ref_match.end():].strip()
                # Some formats append a 1-2 digit check/sequence field after the ref number
                # e.g. "24239004112900016857006 7 2AWAREHOUSE..." — strip the lone digit token
                rest = re.sub(r'^\d{1,2}\s+', '', rest)
            
            # Extract amounts
            amounts = []
            for match in re.finditer(r'\$?([0-9,]+\.\d{2})', rest):
                try:
                    clean = match.group(1).replace(',', '')
                    amounts.append(float(clean))
                except ValueError:
                    continue
            
            # Debug: Log amount extraction for specific transactions
            if hasattr(self, 'debug') and self.debug and ('FOCUS' in rest.upper() or 'WITHDRAWAL' in rest.upper()):
                print(f"  [AMOUNTS] {description[:30] if 'description' in locals() else rest[:30]}: {amounts}")
            
            # Extract description
            description = rest
            amount_matches = list(re.finditer(r'\$?[0-9,]+\.\d{2}', description))
            if amount_matches:
                new_desc = ''
                last_end = 0
                for match in amount_matches:
                    new_desc += description[last_end:match.start()]
                    last_end = match.end()
                new_desc += description[last_end:]
                description = new_desc
            
            description = ' '.join(description.split()).strip()
            
            # Remove statement-specific trailing reward text
            rewards_patterns = [
                r'\s*Cash Back Rewards.*$',
                r'\s*Earned This Period.*$',
                r'\s*\d+% (on|and).*$',
                r'\s*Fees Charged.*$',
                r'\s*last statement\s+\.+\s*\+?\$[\d,]+\.\d{2}.*$',
                r'\s*[»›]\s*Visit.*$',
                r'\s*earn is on.*$'
            ]
            for pattern in rewards_patterns:
                description = re.sub(pattern, '', description, flags=re.IGNORECASE).strip()
            
            # Check previous line if no description
            if not description or len(description) < 3 or not any(c.isalpha() for c in description):
                if start_idx > 0:
                    prev_line = lines[start_idx - 1].strip()
                    has_date = (re.match(date_pattern_long, prev_line) or 
                               re.match(date_pattern_short, prev_line) or 
                               re.match(date_pattern_dash, prev_line) or
                               re.match(date_pattern_no_year, prev_line))
                    is_time = re.match(r'^\d{1,2}:\d{2}$', prev_line)
                    
                    # Check if previous line looks like a transaction reference/tail (from page breaks)
                    # Pattern: "City ST code### NNNNNNN" (e.g., "Oakland CA ad983a51 0005274")
                    looks_like_reference_tail = bool(re.match(r'^[A-Za-z\s]+ [A-Z]{2} [a-z0-9]+ \d{7,}$', prev_line))
                    
                    # Debug logging
                    if hasattr(self, 'debug') and self.debug and not description:
                        print(f"  [NO DESC] Checking prev line: {repr(prev_line[:50])}")
                        print(f"    has_date={has_date}, is_time={is_time}, looks_like_ref={looks_like_reference_tail}, has_alpha={any(c.isalpha() for c in prev_line)}, len={len(prev_line)}")
                    
                    if prev_line and not has_date and not is_time and not looks_like_reference_tail and any(c.isalpha() for c in prev_line) and len(prev_line) > 5:
                        description = prev_line
                        if hasattr(self, 'debug') and self.debug:
                            print(f"    → Using prev line as description")
            
            # Check next line for continuation
            lines_consumed = 1
            if start_idx + 1 < len(lines):
                next_line = lines[start_idx + 1].strip()
                has_date = (re.match(date_pattern_long, next_line) or 
                           re.match(date_pattern_short, next_line) or 
                           re.match(date_pattern_dash, next_line) or
                           re.match(date_pattern_no_year, next_line))
                has_amounts = bool(re.search(r'\$?[0-9,]+\.\d{2}', next_line))
                
                looks_like_new_transaction = bool(re.match(r'^XX\d{4}\s+(RECUR|POS|DEBIT|CREDIT)\s+PURCHASE', next_line, re.IGNORECASE))
                looks_like_transfer = any(keyword in next_line.upper() for keyword in ['ONLINE-PHONE', 'TRANSFER FROM', 'TRANSFER TO', 'ONLINE TRANSFER'])
                looks_like_summary = any(keyword in next_line.upper() for keyword in [
                    'EARNED THIS PERIOD', 'EARNED', 'TOTAL REWARDS', 'CASH BACK',
                    'REWARDS BALANCE', 'REWARDS SUMMARY', 'BALANCE', 'FEES CHARGED',
                    'FEESCHARGED', 'INTERESTCHARGED', 'TOTALFEES', 'TOTALINTEREST',
                    'STATEMENT', '% ON GAS', '% ON OTHER'
                ])
                
                if next_line and not has_date and not has_amounts and not looks_like_new_transaction and not looks_like_transfer and not looks_like_summary:
                    if any(c.isalpha() for c in next_line):
                        description += ' ' + next_line
                        lines_consumed = 2
            
            if not description or not amounts:
                return None, lines_consumed
            
            return self._build_transaction(trans_date, description, amounts), lines_consumed
        
        else:
            # Description first, then date+amounts on next line
            if not any(c.isalpha() for c in current_line):
                return None, 1
            
            # Check if current line looks like a transaction reference tail (from page breaks)
            # Pattern: "City ST code### NNNNNNN" (e.g., "Oakland CA ad983a51 0005274")
            looks_like_reference_tail = bool(re.match(r'^[A-Za-z\s]+ [A-Z]{2} [a-z0-9]+ \d{7,}$', current_line))
            if looks_like_reference_tail:
                return None, 1
            
            description = current_line
            description = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}$', '', description)
            
            if start_idx + 1 >= len(lines):
                return None, 1
            
            next_line = lines[start_idx + 1].strip()
            date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})', next_line)
            
            if not date_match:
                return None, 1
            
            trans_date = date_match.group(1)
            rest = next_line[date_match.end():].strip()
            
            amounts = []
            for match in re.finditer(r'\$?([0-9,]+\.\d{2})', rest):
                try:
                    clean = match.group(1).replace(',', '')
                    amounts.append(float(clean))
                except ValueError:
                    continue
            
            if not amounts:
                return None, 2
            
            lines_consumed = 2
            
            if start_idx + 2 < len(lines):
                third_line = lines[start_idx + 2].strip()
                if third_line and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}', third_line):
                    if any(c.isalpha() for c in third_line) and '$' not in third_line:
                        description += ' ' + third_line
                        lines_consumed = 3
            
            return self._build_transaction(trans_date, description, amounts), lines_consumed
    
    def parse_transactions(self, text: str, statement_year: Optional[int] = None) -> List[Dict]:
        """Parse all transactions from text."""
        if statement_year is None:
            statement_year = self.extract_statement_year(text)
        
        lines = text.split('\n')
        transactions = []
        
        # Extract beginning balance for later use in classification
        self._beginning_balance = None
        for line in lines[:100]:
            if 'BEGINNING BALANCE' in line.upper():
                # Extract amount from line like "MM/DD/YYYY Beginning Balance $1,537.52"
                amounts = re.findall(r'\$([0-9,]+\.\d{2})', line)
                if amounts:
                    try:
                        self._beginning_balance = float(amounts[0].replace(',', ''))
                        if hasattr(self, 'debug') and self.debug:
                            print(f"  [DEBUG] Beginning balance: ${self._beginning_balance:.2f}")
                        break
                    except:
                        pass
        
        # Detect Debits/Credits column layout
        self._has_debit_credit_columns = False
        for line in lines[:50]:
            line_upper = line.upper()
            if ('DEBITS' in line_upper and 'CREDITS' in line_upper):
                self._has_debit_credit_columns = True
                if hasattr(self, 'debug') and self.debug:
                    print(f"  [DEBUG] Detected Debits/Credits column layout")
                break
        
        # Look for transaction section
        in_transaction_section = False
        i = 0
        _prev_balance_tracker = None  # tracks last Balance seen; used to detect balance-as-amount errors
        
        while i < len(lines):
            line = lines[i].strip()
            line_upper = line.upper()
            
            # Detect transaction section start
            if any(marker in line_upper for marker in [
                'ACCOUNT ACTIVITY', 'TRANSACTION HISTORY', 'TRANSACTIONS',
                'POST DATE', 'TRANS DATE', 'POSTING', 'DESCRIPTION OF TRANSACTION',
                'ACCOUNT SUMMARY', 'SALE POST', 'SALE DATE'
            ]):
                in_transaction_section = True
                i += 1
                continue
            
            # Detect section end
            if in_transaction_section and any(marker in line_upper for marker in [
                'TOTAL DEBITS', 'TOTAL CREDITS', 'INTEREST SUMMARY', 'FEES SUMMARY',
                'STATEMENT CLOSING', 'IMPORTANT INFORMATION',
                'OVERDRAFT', 'DIRECT DEPOSIT', 'INTEREST RATE', 'DAILY BALANCES',
                'MINIMUM PAYMENT', 'PAYMENT DUE', 'ACCOUNT SUMMARY', 
                'PREVIOUS BALANCE', 'NEW BALANCE'
            ]):
                in_transaction_section = False
                i += 1
                continue
            
            # Skip if not in section and line doesn't start with date
            starts_with_date = re.match(r'^\d{1,2}[/-]\d{1,2}', line)
            if not in_transaction_section and not starts_with_date:
                i += 1
                continue
            
            # Try to parse transaction
            trans, consumed = self.parse_transaction_block(lines, i, statement_year)
            if trans and trans.get('Place'):
                # Detect balance-as-amount: single extracted amount equals the previous row's running balance.
                # This happens when pdfplumber collapses a multi-column layout and the transaction
                # amount column is missing, leaving only the running balance on that row.
                if (
                    'Amount' in trans
                    and 'Balance' not in trans
                    and 'Credits' not in trans
                    and 'Debits' not in trans
                    and _prev_balance_tracker is not None
                    and abs(trans['Amount'] - _prev_balance_tracker) < 0.01
                ):
                    trans['_suspicious_balance'] = True
                    if hasattr(self, 'debug') and self.debug:
                        print(f"  [SUSPICIOUS BALANCE] {trans['Transaction Date']} {trans.get('Place', '')[:25]}: "
                              f"Amount ${trans['Amount']:.2f} == prev balance ${_prev_balance_tracker:.2f} — routing to manual review")

                # Update balance tracker whenever a row carries a Balance field (any numeric value, including 0/negative)
                if 'Balance' in trans and isinstance(trans['Balance'], (int, float)):
                    _prev_balance_tracker = trans['Balance']

                transactions.append(trans)
            
            i += consumed if consumed > 0 else 1
        
        return transactions
    
    def extract_text_and_transactions(self, pdf_path: Path) -> Tuple[str, List[Dict], Dict]:
        """
        Extract text and transactions from PDF.
        
        Returns:
            (text, transactions, validation_results)
        """
        # Extract text using pdfplumber
        text = extract_text_from_pdf(pdf_path, debug=hasattr(self, 'debug') and self.debug)
        
        if not text:
            print(f"  No text extracted")
            return '', [], {'valid': False, 'score': 0, 'transaction_count': 0, 'issues': ['No text extracted'], 'method': 'pdfplumber'}
        
        # Parse transactions from text
        transactions = self.parse_transactions(text)
        
        # Validate transaction quality
        validation = validate_transactions(transactions, 'pdfplumber')
        
        if hasattr(self, 'debug') and self.debug:
            print(f"  -> pdfplumber: {validation['transaction_count']} transactions, quality score: {validation['score']:.0f}/100")
        
        return text, transactions, validation
    
    def filter_transfers(self, transactions: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Separate transfers from real transactions using config keywords."""
        real_transactions = []
        transfers = []
        
        for trans in transactions:
            place = trans.get('Place_Original', trans.get('Place', '')).upper()
            is_transfer = any(keyword in place for keyword in self.transfer_keywords)
            
            # Debug logging for transfers
            if hasattr(self, 'debug') and self.debug and is_transfer:
                print(f"  [TRANSFER FILTERED] {trans.get('Place', '')[:40]} - ${trans.get('Amount', 0)}")
            
            if is_transfer:
                transfers.append(trans)
            else:
                real_transactions.append(trans)
        
        return real_transactions, transfers
    
    def classify_transactions(self, transactions: List[Dict], is_bank_account: bool) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
        """
        Classify transactions into income, expenses, and manual_review.
        
        For bank accounts: Uses Credits/Debits columns, or balance comparison as fallback
        For credit cards: Uses Credits/Debits columns
        Payment apps: Sent to manual_review for user classification
        """
        income = []
        expenses = []
        manual_review = []
        investment_transfers = []
        
        # Sort transactions by statement and date for balance comparison
        def parse_date(trans):
            try:
                date_str = trans.get('Transaction Date', '')
                return datetime.strptime(date_str, '%m/%d/%Y')
            except:
                return datetime.min
        
        # Sort by statement first, then date (balance tracking only works within same statement)
        transactions_sorted = sorted(transactions, key=lambda x: (x.get('Statement', ''), parse_date(x)))
        
        # Track balance per statement
        prev_balance = None
        prev_statement = None
        
        for trans in transactions_sorted:
            # Reset prev_balance when switching to a new statement
            current_statement = trans.get('Statement', '')
            if current_statement != prev_statement:
                # Use the beginning balance stored with this transaction
                prev_balance = trans.get('_statement_beginning_balance')
                prev_statement = current_statement
                if hasattr(self, 'debug') and self.debug:
                    print(f"\n  [NEW STATEMENT] {current_statement} - resetting prev_balance to ${prev_balance}")
        
            place = trans.get('Place', '').upper()
            place_original = trans.get('Place_Original', place).upper()

            # Detect credit card return/reimbursement: standalone "CR" in description
            is_credit_return = bool(re.search(r'\bCR\b', place_original))

            is_payment_app = any(app in place or app in place_original for app in self.payment_apps)
            
            if trans.get('_suspicious_balance'):
                # Amount equals the previous row's running balance — the real transaction amount
                # was not captured (likely a PDF column-collapse issue). Route to manual review
                # so the user can supply the correct amount.
                trans['Type'] = 'Expense'  # conservative hint; user can correct
                trans['_needs_manual_review'] = True
                print(f"  ⚠ Suspicious amount (= prev balance ${trans['Amount']:.2f}): "
                      f"{trans.get('Place', '')} {trans.get('Transaction Date', '')} — routed to manual review")
                manual_review.append(trans)
                continue

            if is_payment_app:
                # Payment apps always go to manual review (user must classify)
                # Try to hint the type based on Credits/Debits, keywords, or transaction description
                trans['_needs_manual_review'] = True
                
                # Hint: Determine likely type (Income or Expense) for the Type column
                has_credits = 'Credits' in trans and trans['Credits'] and trans['Credits'] > 0
                has_debits = 'Debits' in trans and trans['Debits'] and trans['Debits'] > 0
                is_income_keyword = any(keyword in place_original for keyword in self.income_keywords)
                
                # Check description for specific transaction type indicators
                desc_upper = place_original.upper()
                expense_indicators = ['PAYMENT', 'PURCHASE', 'POS PURCHASE', 'WITHDRAWAL', 'PAYMENT APP*']
                income_indicators = ['CASHOUT', 'CASH OUT', 'DEPOSIT', 'CREDIT', 'REFUND', 'TRANSFER FROM']
                
                is_likely_expense = any(indicator in desc_upper for indicator in expense_indicators)
                is_likely_income = any(indicator in desc_upper for indicator in income_indicators)
                
                # Special handling for payment-app transactions without purchase keywords
                # "PAYMENT APP [NAME]" without "PURCHASE"/"POS" = likely cashout (income)
                # "PAYMENT APP*" or "POS PURCHASE AT PAYMENT APP" = likely wallet load (expense)
                if any(app in desc_upper for app in self.payment_apps) and not is_likely_expense and not is_likely_income:
                    # Plain "PAYMENT APP [NAME]" pattern suggests cashout
                    is_likely_income = True
                
                # Prioritize description indicators over column-based hints
                if is_likely_income:
                    trans['Type'] = 'Income'
                elif is_likely_expense:
                    trans['Type'] = 'Expense'
                elif has_credits or is_income_keyword:
                    trans['Type'] = 'Income'
                elif has_debits:
                    trans['Type'] = 'Expense'
                elif 'Amount' in trans:
                    # For Amount column, check keywords
                    trans['Type'] = 'Income' if is_income_keyword else 'Expense'
                else:
                    trans['Type'] = 'Expense'  # Default to expense if unsure
                
                print(f"  Payment app flagged for manual review: {trans.get('Place', '')} (Type: {trans['Type']})")
                manual_review.append(trans)
                continue
            
            if is_bank_account:
                has_credits = 'Credits' in trans and trans['Credits'] and trans['Credits'] > 0
                has_debits = 'Debits' in trans and trans['Debits'] and trans['Debits'] > 0
                
                if has_credits:
                    income.append(trans)
                elif has_debits:
                    expenses.append(trans)
                elif 'Amount' in trans and trans['Amount'] > 0:
                    # Use income_keywords to classify
                    is_income_keyword = any(keyword in place_original for keyword in self.income_keywords)
                    
                    if hasattr(self, 'debug') and self.debug:
                        classification = "INCOME" if (is_income_keyword or is_credit_return) else "EXPENSE"
                        matched_keyword = next((kw for kw in self.income_keywords if kw in place_original), "CR return" if is_credit_return else "none")
                        print(f"  [KEYWORD] {trans.get('Transaction Date')} {trans.get('Place', '')[:25]:25s}: matched='{matched_keyword}' → {classification}")
                    
                    if is_credit_return:
                        trans['category'] = 'Return/Reimbursement'
                        print(f"  Credit return detected (CR): {trans.get('Place', '')} ${trans.get('Amount', '')}")
                        income.append(trans)
                    elif is_income_keyword:
                        income.append(trans)
                    else:
                        expenses.append(trans)
            else:
                has_credits = 'Credits' in trans and trans['Credits'] and trans['Credits'] > 0
                has_debits = 'Debits' in trans and trans['Debits'] and trans['Debits'] > 0
                
                if has_credits:
                    income.append(trans)
                elif is_credit_return:
                    trans['category'] = 'Return/Reimbursement'
                    print(f"  Credit return detected (CR): {trans.get('Place', '')} ${trans.get('Amount', '')}")
                    income.append(trans)
                elif has_debits or 'Amount' in trans:
                    expenses.append(trans)
                else:
                    expenses.append(trans)
        
        return income, expenses, manual_review, investment_transfers
    
    def parse_pdf(self, pdf_path: Path, debug: bool = False, statement_year: int = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str, bool]:
        """
        Parse a bank statement PDF using pdfplumber + LLM cleaning.
        
        Args:
            pdf_path: Path to the PDF file
            debug: If True, print detailed debug info
            statement_year: Year of the statement (from directory name), overrides auto-detection
        
        Returns:
            (income_df, expenses_df, manual_review_df, bank_name, is_bank_account)
        """
        self.debug = debug
        self.statement_year = statement_year  # Store for use in transaction parsing
        
        if debug:
            print(f"\nParsing {pdf_path.name}...")
        
        # Extract text and transactions
        text, transactions, validation = self.extract_text_and_transactions(pdf_path)
        
        if debug and validation.get('issues'):
            print(f"  Validation issues: {', '.join(validation['issues'])}")
        
        # Detect bank and account type
        bank_name = self.detect_bank_name(text)
        is_bank_account = not self.is_credit_card(text)
        
        if debug:
            print(f"  Bank: {bank_name}")
            print(f"  Type: {'Bank Account' if is_bank_account else 'Credit Card'}")
        
        # Parse transactions if not already done
        if not transactions:
            transactions = self.parse_transactions(text)
        
        if debug:
            print(f"  Found {len(transactions)} transaction(s)")
        
        # Filter out transfers
        transactions, transfers = self.filter_transfers(transactions)
        if debug and transfers:
            print(f"  Skipped {len(transfers)} transfer(s)")
        
        # Classify transactions
        income, expenses, manual_review, investment_transfers = self.classify_transactions(transactions, is_bank_account)
        if debug:
            print(f"  {len(income)} income, {len(expenses)} expenses, {len(manual_review)} manual review, {len(investment_transfers)} transfers")
        
        # Convert to DataFrames
        income_df = pd.DataFrame(income) if income else pd.DataFrame()
        expenses_df = pd.DataFrame(expenses) if expenses else pd.DataFrame()
        manual_review_df = pd.DataFrame(manual_review) if manual_review else pd.DataFrame()
        transfers_df = pd.DataFrame(investment_transfers) if investment_transfers else pd.DataFrame()
        
        # Add source column
        if not income_df.empty:
            income_df['Statement'] = bank_name
        if not expenses_df.empty:
            expenses_df['Statement'] = bank_name
        if not manual_review_df.empty:
            manual_review_df['Statement'] = bank_name
        if not transfers_df.empty:
            transfers_df['Statement'] = bank_name
        
        return income_df, expenses_df, manual_review_df, transfers_df, bank_name, is_bank_account
