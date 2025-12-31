#!/usr/bin/env python3
"""
Hybrid PDF parser: pdfplumber (fast, accurate) + OCR fallback + optional LLM enhancement.
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.bankai.ocr.text_extractor import TextExtract
from src.bankai.utils.pdf_converter import PDF2ImageConvertor


class HybridPDFParser:
    """
    Hybrid PDF parser with multi-LLM validation and cross-referencing.
    
    Features:
    - Dual extraction: pdfplumber + OCR with intelligent cross-referencing
    - Multi-line transaction parsing with date error correction
    - Multi-LLM merchant name cleaning:
        1. Pattern-based noise removal (payment processors, codes, locations)
        2. 3-prompt LLM validation with confidence scoring
        3. Weighted voting to select best result
        4. Context-aware cleaning (passes amount + date to LLM)
    - Automatic bank detection and transaction classification
    - Minimal processor-specific rules (Squarespace, Cash App, BP, etc.)
    """
    
    def __init__(self, config_dir: Path = None, llm_model: str = 'qwen2.5:14b', use_llm_cleaning: bool = True, use_multi_model: bool = True):
        """Initialize with config directory."""
        if config_dir:
            self.config_dir = config_dir
        else:
            # Try to find config directory relative to this file
            self.config_dir = Path(__file__).parent / 'config'
            if not self.config_dir.exists():
                # If running from project root
                self.config_dir = Path('config')
        
        # Load configs (no bank_patterns needed - we extract from PDFs)
        self.income_keywords = self._load_config('income_keywords.json', 'income_keywords')
        self.transfer_keywords = self._load_config('transfer_keywords.json', 'keywords')
        self.payment_apps = self._load_config('payment_apps.json', 'payment_apps')
        # Convert to uppercase for matching
        self.income_keywords = [k.upper() for k in self.income_keywords]
        self.transfer_keywords = [k.upper() for k in self.transfer_keywords]
        self.payment_apps = [k.upper() for k in self.payment_apps]
        
        # Load LLM model configuration
        llm_config_file = self.config_dir / 'llm_models.json'
        llm_config = {}
        if llm_config_file.exists():
            try:
                with open(llm_config_file) as f:
                    llm_config = json.load(f)
            except:
                pass
        
        # LLM configuration (allow init params to override config file)
        self.llm_model = llm_model if llm_model != 'qwen2.5:14b' else llm_config.get('primary_model', 'qwen2.5:14b')
        self.secondary_model = llm_config.get('secondary_model', 'dolphin-mistral')
        self.use_multi_model = use_multi_model if use_multi_model != True else llm_config.get('use_multi_model', True)
        self.available_models = []  # Will be populated by _check_llm()
        
        # Check for local LLM (Ollama)
        self.use_llm_cleaning = use_llm_cleaning
        self.llm_available = self._check_llm() if use_llm_cleaning else False
        
        # Historical cache for merchant names (improves consistency)
        self.merchant_cache = {}  # raw_name -> cleaned_name
        self.merchant_frequency = {}  # cleaned_name -> frequency count (how often it appears)
        self._load_merchant_cache()
        self._load_user_corrections_from_csvs()
        
        # OCR fallback tools (only initialize if needed)
        self.pdf_converter = None
        self.text_extractor = None
    
    def _check_llm(self) -> bool:
        """Check if Ollama LLM is available locally."""
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if models:
                    # Store all available models
                    self.available_models = [m['name'] for m in models]
                    
                    # Check if our preferred model is available
                    if any(self.llm_model in name for name in self.available_models):
                        if self.use_multi_model and len(self.available_models) > 1:
                            print(f"  ✓ Multi-model ensemble: {len(self.available_models)} models available")
                            print(f"    Primary: {self.llm_model}")
                            print(f"    Secondary: {self.secondary_model}")
                            for model in self.available_models:
                                print(f"    - {model}")
                        else:
                            print(f"  ✓ Local LLM available ({self.llm_model})")
                    else:
                        # Auto-fallback to first available model
                        fallback_model = self.available_models[0]
                        print(f"  ✓ Local LLM available ({len(models)} model(s) detected)")
                        print(f"    Note: {self.llm_model} not found, using {fallback_model}")
                        self.llm_model = fallback_model
                    return True
        except:
            pass
        return False
    
    def _load_merchant_cache(self):
        """Load historical merchant name mappings for consistency."""
        cache_file = self.config_dir / 'merchant_cache.json'
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self.merchant_cache = json.load(f)
                print(f"  ✓ Loaded {len(self.merchant_cache)} cached merchant names")
            except Exception as e:
                print(f"  ⚠ Could not load merchant cache: {e}")
                self.merchant_cache = {}
    
    def _save_merchant_cache(self):
        """Save merchant name mappings for future runs."""
        cache_file = self.config_dir / 'merchant_cache.json'
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.merchant_cache, f, indent=2)
        except Exception as e:
            print(f"  ⚠ Could not save merchant cache: {e}")
    
    def _load_user_corrections_from_csvs(self):
        """Load user's manual corrections from all statement CSVs with frequency tracking.
        
        Scans statements/ directory for expenses.csv and income.csv files,
        extracts cleaned merchant names that users have manually corrected,
        tracks frequency for confidence scoring, and adds them to the merchant cache.
        
        Higher frequency = higher confidence that this is the correct name.
        """
        # Find statements directory
        statements_dir = Path('statements')
        if not statements_dir.exists():
            # Try relative to script location
            statements_dir = Path(__file__).parent.parent.parent / 'statements'
        
        if not statements_dir.exists():
            return
        
        corrections_loaded = 0
        csv_files_scanned = 0
        merchant_counts = {}  # Track frequency: cleaned_name -> count
        
        # Scan all month directories (no limit - it's fast!)
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
                            if len(place) >= 3:
                                # Track how many times this merchant appears
                                merchant_counts[place] = merchant_counts.get(place, 0) + 1
                
                except Exception as e:
                    pass  # Silently skip problematic CSVs
        
        # Now store unique merchants with frequency data
        # CSV files contain user corrections = ground truth, so always overwrite cache
        for place, count in merchant_counts.items():
            cache_key = place.upper().strip()
            # Always use CSV data (user corrections are authoritative)
            if cache_key not in self.merchant_cache or self.merchant_cache[cache_key] != place:
                self.merchant_cache[cache_key] = place
                corrections_loaded += 1
            
            # Store frequency for confidence scoring
            self.merchant_frequency[place] = count
        
        if corrections_loaded > 0 and csv_files_scanned > 0:
            # Calculate confidence stats
            high_confidence = sum(1 for c in merchant_counts.values() if c >= 5)
            medium_confidence = sum(1 for c in merchant_counts.values() if 2 <= c < 5)
            low_confidence = sum(1 for c in merchant_counts.values() if c == 1)
            
            print(f"  📚 Loaded {corrections_loaded} merchants from {csv_files_scanned} CSV files")
            print(f"     High confidence (5+ occurrences): {high_confidence}")
            print(f"     Medium confidence (2-4): {medium_confidence}")
            print(f"     Low confidence (1): {low_confidence}")
    
    def _get_similar_merchants(self, name: str, limit: int = 5) -> list:
        """Get most frequently seen merchants similar to this name.
        
        Used to provide context to LLM for difficult/ambiguous merchant names.
        Returns merchants sorted by frequency (most common first).
        """
        if not self.merchant_frequency:
            return []
        
        # Normalize for comparison
        name_norm = name.upper().replace(' ', '').replace('-', '').replace('&', '')
        
        similar = []
        for merchant, freq in self.merchant_frequency.items():
            merchant_norm = merchant.upper().replace(' ', '').replace('-', '').replace('&', '')
            
            # Check if similar (contains or is contained)
            if (name_norm in merchant_norm or merchant_norm in name_norm) and len(name_norm) >= 3:
                similar.append((merchant, freq))
        
        # Sort by frequency (most common first)
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return [merchant for merchant, freq in similar[:limit]]
    
    def llm_clean_merchant_name(self, merchant: str, amount: float = None, date: str = None) -> str:
        """
        Use LLM to clean up merchant name with multi-pass cross-validation and context.
        
        Three-pass system:
        1. Extraction-focused (remove noise)
        2. Location-removal focused
        3. Validation (checks if result makes sense)
        
        Context (amount, date) helps LLM make better decisions.
        
        Example: "XX4297 RECUR PURCHASE. YSI* MAPLE RIDGE VILLA" → "Maple Ridge Villa"
        """
        if not self.llm_available:
            return merchant
        
        try:
            import requests
            
            # Build context string if available
            context = ""
            if amount is not None:
                context += f" Amount: ${amount:.2f}."
            if date:
                context += f" Date: {date}."
            
            # Get similar merchants from history for context
            similar_merchants = self._get_similar_merchants(merchant, limit=3)
            if similar_merchants:
                context += f"\nSimilar merchants in your history: {', '.join(similar_merchants)}"
            
            # Method 1: Extraction-focused prompt
            prompt1 = f"""Extract clean business name from transaction.{context}

REMOVE ALL:
- City/state names and abbreviations (any city, ST, CA, etc.)
- Store/location numbers (#1234, 00001000, 50020)
- Reference codes (10+ digit strings, alphanumeric codes)
- Payment codes (WEB PMTS, ACH, POS, etc.)
- Asterisks and special prefixes (*, SQ*, TST*, YSI*)
- Direction words (West, East, North, South)

FIX:
- Add spaces to compressed words (NAMEHERE → Name Here)
- Expand abbreviations (Elec → Electric, Co → Company, Inc)
- Keep recognized brand codes (BP, 7-Eleven, etc.)
- Proper capitalization

Examples:
"THE HOME DEPOT #3701 CITYNAME ST" → "Home Depot"
"RESTAURANTINC CITYNAME" → "Restaurant Inc"
"Electric Co WEB PMTS CODE123" → "Electric Company"
"YSI* FACILITY NAME WEST CITY ST 00001000" → "YSI Facility Name"
"COMPRESSEDNAME CITY ST" → "Compressed Name"
"BP#9267972HWY 13BP CITYNAME ST" → "BP"
"COWBOYJACKS-APPLEV PHONE# ST" → "Cowboy Jacks"
"DECOR&MOREFROM RUE CITY ST" → "Decor & More"
"PIKEAND PINTGRILLINC CITY ST" → "Pike and Pint Grill Inc"

Transaction: {merchant}
Name:"""
            
            # Method 2: Location-removal focused
            prompt2 = f"""Clean merchant name - remove only location info:

Remove:
- City names
- State codes (ND, MN, CA, etc.)
- Direction words (West, East)
- Store numbers

Keep business name intact.

Input: {merchant}
Output:"""
            
            # Method 3: Validation prompt
            prompt3 = f"""Is this a valid business name? If not, provide corrected version.{context}

Good: "Home Depot", "Cash App", "BP", "Squarespace"
Bad: "Purchase", "Recur Purchase", "POS", "WL Steam"

Transaction: {merchant}
Valid:"""
            
            results = []
            confidences = []
            
            # Multi-model ensemble: Use different models if available
            if self.use_multi_model and len(self.available_models) >= 2:
                # Strategy: Use different models for diversity
                # Prompt 1: Primary model (extraction-focused, best at details)
                # Prompt 2: Secondary model (location removal, provides diversity)
                # Prompt 3: Primary model (validation, consistency with prompt 1)
                
                # Find the configured models in available models
                primary_found = None
                secondary_found = None
                
                for model in self.available_models:
                    if self.llm_model in model:
                        primary_found = model
                    if self.secondary_model in model:
                        secondary_found = model
                
                # Use configured models if found, otherwise fall back to first two available
                if primary_found and secondary_found:
                    model_sequence = [primary_found, secondary_found, primary_found]
                    # print(f"  [DEBUG] Using configured models: {primary_found} + {secondary_found}")
                elif primary_found:
                    # Primary found but not secondary - use primary + any other
                    other_model = next((m for m in self.available_models if m != primary_found), self.available_models[0])
                    model_sequence = [primary_found, other_model, primary_found]
                    # print(f"  [DEBUG] Using primary + fallback: {primary_found} + {other_model}")
                else:
                    # Neither found - use first two available
                    model_sequence = [self.available_models[0], self.available_models[1], self.available_models[0]]
                    # print(f"  [DEBUG] Using available models: {self.available_models[0]} + {self.available_models[1]}")
            else:
                # Single model for all prompts
                model_sequence = [self.llm_model] * 3
            
            # Run all three prompts with assigned models
            for idx, (prompt, model) in enumerate(zip([prompt1, prompt2, prompt3], model_sequence)):
                try:
                    response = requests.post(
                        'http://localhost:11434/api/generate',
                        json={
                            'model': model,  # Use model from sequence
                            'prompt': prompt,
                            'stream': False,
                            'options': {
                                'temperature': 0.0 if idx < 2 else 0.1,
                                'num_predict': 35,
                                'top_p': 0.9,
                                'stop': ['\n', 'Transaction', 'Rules', 'Example', 'Input:', 'Remove:', 
                                        'REMOVE', 'FIX:', 'Examples:', '\n\n', 'Valid:', 'Good:', 'Bad:']
                            }
                        },
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        result = response.json().get('response', '').strip()
                        result = self._clean_llm_response(result, merchant)
                        if result:
                            results.append(result)
                            confidence = self._calculate_confidence(result, merchant, idx)
                            confidences.append(confidence)
                except:
                    continue
            
            # Cross-validate with confidence weighting
            if len(results) >= 2:
                final_result = self._cross_validate_merchant_names_weighted(
                    results, confidences, merchant
                )
                return final_result
            elif len(results) == 1:
                return results[0]
                
        except Exception as e:
            pass
        
        return merchant
    
    def _clean_llm_response(self, result: str, original: str) -> str:
        """Clean and validate LLM response for merchant name."""
        if not result:
            return None
        
        # Clean up LLM response
        result = result.replace('"', '').replace("'", '').strip()
        
        # Take only first line if multi-line
        if '\n' in result:
            result = result.split('\n')[0].strip()
        
        # Check for concatenated responses - take first part before markers
        markers = [' Merchant:', ' Business:', ' Name:', ' Clean name:', 
                  ' Input:', ' Transaction:', ' Examples:', ' REMOVE']
        for marker in markers:
            if marker in result:
                result = result.split(marker)[0].strip()
                break
        
        # Remove common prefixes and artifacts that LLM might leave
        artifact_prefixes = ['SQ*', 'SQ *', 'TST*', 'TST *', 'WL*', 'WL *', 'YSI*', 'YSI *', 'XX', 'POS ']
        for prefix in artifact_prefixes:
            if result.upper().startswith(prefix.upper()):
                result = result[len(prefix):].strip()
        
        # Remove standalone asterisks that LLM might leave
        result = result.replace('* ', ' ').replace(' *', ' ').strip('*').strip()
        
        # Split on common business name patterns (when LLM returns multiple concatenated names)
        # e.g., "OReilly Coborns" or "HOOLIGANS Home Depot"
        words = result.split()
        
        # Only truncate if we have clear signs of concatenation (>4 words AND recognized chains)
        if len(words) > 4:
            # Check if we have two separate business names concatenated
            known_chains = ['Home', 'Depot', 'Cash', 'App', 'Grand', 'Junction', 
                           'Coborns', 'Coborn', 'Wine', 'More']
            
            # Look for a second business name starting after position 2-3
            for i in range(2, len(words)):
                if words[i] in known_chains and i > 2:
                    # Found likely concatenation - take first part
                    result = ' '.join(words[:i])
                    break
        
        # Remove common LLM prefixes/artifacts
        prefixes_to_remove = [
            'Output:', 'Answer:', 'Result:', 'Clean name:', 'Business:', 'Business name:', 
            'Name:', 'The business name is:', 'Merchant:', 'Extract:', 'Transaction:',
            'Critical rules:', 'Critical Rules Applied:', 'Rules for extraction:',
            'Examples:', 'You are', 'Based on', 'Simplify:', 'Input:', 'REMOVE ALL:',
            'KEEP:', 'MUST REMOVE:', 'STANDARDIZE:'
        ]
        for prefix in prefixes_to_remove:
            if result.lower().startswith(prefix.lower()):
                result = result[len(prefix):].strip()
                result = result.lstrip(':').strip()
        
        # Remove if result contains prompt keywords (sign of echo)
        if any(keyword in result.lower() for keyword in 
               ['transaction text', 'extract the', 'business name', 'one line', 
                'merchant name', 'simplify this', 'remove:', 'fix:', 'remove all',
                'must remove', 'keep:', 'standardize:']):
            return None
        
        # Only use if result is reasonable
        if result and 3 <= len(result) <= 60 and any(c.isalpha() for c in result):
            # Don't use if it's just the original with minor changes
            if result.lower() == original.lower():
                return None
            return result
        
        return None
    
    def _calculate_confidence(self, result: str, original: str, prompt_idx: int) -> float:
        """
        Calculate confidence score for LLM result.
        
        Factors:
        - Length (too short = low confidence)
        - Has actual business name characteristics
        - Prompt type (validation prompt gets higher weight)
        - Similarity to original (too similar = didn't clean much)
        """
        confidence = 50.0  # Base confidence
        
        # Length scoring
        if 3 <= len(result) <= 30:
            confidence += 20
        elif len(result) > 30:
            confidence -= 10
        
        # Has proper capitalization
        if result and result[0].isupper():
            confidence += 10
        
        # Not too similar to original (means it actually cleaned)
        if result.lower() != original.lower():
            confidence += 15
        
        # Has spaces (likely proper name, not code)
        if ' ' in result:
            confidence += 10
        
        # No artifacts
        bad_words = ['PURCHASE', 'RECUR', 'POS', 'ACH', 'WEB', 'PMTS']
        if not any(word in result.upper() for word in bad_words):
            confidence += 15
        else:
            confidence -= 20
        
        # Validation prompt (prompt_idx=2) gets bonus
        if prompt_idx == 2:
            confidence += 10
        
        # Cap between 0-100
        return max(0, min(100, confidence))
    
    def _cross_validate_merchant_names_weighted(self, results: list, confidences: list, original: str) -> str:
        """
        Cross-validate multiple LLM results using confidence-weighted voting.
        
        Returns the result with highest combined score (quality + confidence).
        """
        if not results:
            return original
        
        # If all results agree, return it with high confidence
        unique_results = list(set(r.lower() for r in results))
        if len(unique_results) == 1:
            return results[0]  # All agree - highest confidence
        
        # Score each result
        scores = []
        for idx, result in enumerate(results):
            score = 0
            
            # Add confidence score
            if idx < len(confidences):
                score += confidences[idx]
            
            # Add quality scoring (from original method)
            # Penalize location words
            location_words = ['fargo', 'west', 'east', 'north', 'south', 'saint', 'st ',
                             'albany', 'moorhead', 'alexandria', 'savage', 'oakland',
                             ' nd', ' mn', ' ca', ' wa', ' va', ' me', ' sd', ' ny']
            if any(loc in result.lower() for loc in location_words):
                score -= 50
            
            # Penalize artifacts
            if any(word in result.upper() for word in ['PURCHASE', 'RECUR', 'POS', 'WL*']):
                score -= 30
            
            # Prefer moderate length
            result_len = len(result)
            if 5 <= result_len <= 25:
                score += 15
            elif result_len > 35:
                score -= 10
            
            # Prefer 2-3 words
            word_count = len(result.split())
            if 2 <= word_count <= 3:
                score += 10
            elif word_count > 5:
                score -= 10
            
            scores.append(score)
        
        # Return result with highest score
        best_idx = scores.index(max(scores))
        return results[best_idx]
    
    def llm_classify_transaction(self, place: str, amount: float) -> str:
        """
        Use LLM to classify ambiguous transactions as income or expense.
        
        Returns: 'income' or 'expense'
        """
        if not self.llm_available:
            return 'expense'  # Default to expense
        
        try:
            import requests
            prompt = f"""Classify this bank transaction as either "income" or "expense". Consider the merchant name and amount.

Merchant: {place}
Amount: ${amount:.2f}

Is this income or an expense? Reply with just one word: income OR expense"""
            
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': 'llama3.2',
                    'prompt': prompt,
                    'stream': False,
                    'options': {'temperature': 0.1}
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json().get('response', '').strip().lower()
                if 'income' in result:
                    return 'income'
                elif 'expense' in result:
                    return 'expense'
        except:
            pass
        
        return 'expense'
    
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
    
    def detect_bank_name(self, text: str) -> str:
        """
        Extract bank/institution name directly from statement text.
        No pattern matching needed - the name is printed on the statement.
        """
        text_upper = text.upper()
        lines = text.split('\n')
        
        # Look for common bank identifiers in first 50 lines
        for line in lines[:50]:
            line_upper = line.upper().strip()
            
            # Direct bank name patterns (look for ".COM", "BANK", etc.)
            if 'STEARNSBANK.COM' in line_upper or 'STEARNS BANK' in line_upper:
                return 'Stearns Bank'
            
            if 'MYMAGNIFI.ORG' in line_upper or 'MAGNIFI FINANCIAL' in line_upper:
                return 'Magnifi Financial'
            
            # Check for "Issued by" pattern (common in credit cards)
            if 'ISSUED BY' in line_upper:
                # Extract the bank name after "Issued by"
                if 'FIRST NATIONAL BANK' in line_upper:
                    # Check what brand
                    full_text_upper = text.upper()
                    if 'SCHEELS' in full_text_upper:
                        return 'Scheels Visa'
                    return 'First National Bank of Omaha'
        
        # Fallback: Look for URLs or contact info
        import re
        urls = re.findall(r'www\.([a-zA-Z0-9-]+)\.(com|org|net)', text.lower())
        if urls:
            domain = urls[0][0]  # First domain found
            # Capitalize properly
            if 'stearns' in domain:
                return 'Stearns Bank'
            if 'magnifi' in domain:
                return 'Magnifi Financial'
            if 'scheels' in domain or 'fnbo' in domain:
                return 'Scheels Visa'
        
        # Last resort: Check for trademark/registered marks
        if 'SCHEELS' in text_upper and ('VISA' in text_upper or 'CARD' in text_upper):
            return 'Scheels Visa'
        
        return 'Unknown'
    
    def extract_statement_year(self, text: str) -> int:
        """Extract the statement year from PDF text."""
        text_lower = text.lower()
        
        # Look for common patterns like:
        # "For billing cycle ending 01/14/2025"
        # "Statement Closing Date 01/14/25"
        # "forbilling cycleending 01/14/25" (Scheels - no spaces)
        
        patterns = [
            r'(?:billing cycle|statement).*?ending.*?\d{1,2}/\d{1,2}/(\d{4})',
            r'statement closing date.*?\d{1,2}/\d{1,2}/(\d{2,4})',
            r'statement date.*?\d{1,2}/\d{1,2}/(\d{4})',
            r'forbilling cycleending \d{1,2}/\d{1,2}/(\d{2})',  # Scheels format
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
        
        # Fallback: current year
        return datetime.now().year
    
    def is_credit_card(self, text: str) -> bool:
        """Determine if statement is from credit card (vs bank account)."""
        text_upper = text.upper()
        
        # Strong bank indicators override everything
        bank_indicators = ['CHECKING', 'SAVINGS', 'ACCOUNT ACTIVITY', 
                          'BEGINNING BALANCE', 'ENDING BALANCE']
        if any(ind in text_upper for ind in bank_indicators):
            return False
        
        # Credit card indicators
        credit_indicators = ['VISA', 'MASTERCARD', 'AMEX', 'DISCOVER',
                            'CREDIT CARD', 'MINIMUM PAYMENT DUE', 
                            'CARD ACCOUNT', 'STATEMENT CLOSING']
        return any(ind in text_upper for ind in credit_indicators)
    
    def validate_transactions(self, transactions: List[Dict], method: str) -> Dict:
        """
        Validate quality of extracted transactions.
        
        Returns:
            {
                'valid': bool,
                'score': float (0-100),
                'transaction_count': int,
                'issues': List[str]
            }
        """
        if not transactions:
            return {
                'valid': False,
                'score': 0,
                'transaction_count': 0,
                'issues': ['No transactions found']
            }
        
        score = 100
        issues = []
        
        # Check 1: Valid dates (MM/DD/YYYY format)
        valid_dates = sum(1 for t in transactions 
                         if 'Transaction Date' in t 
                         and re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', str(t['Transaction Date'])))
        date_ratio = valid_dates / len(transactions)
        if date_ratio < 0.9:
            score -= 20
            issues.append(f'Only {date_ratio:.0%} have valid dates')
        
        # Check 2: Valid amounts (should have numbers)
        transactions_with_amounts = sum(1 for t in transactions
                                       if any(k in t and t[k] and t[k] > 0 
                                            for k in ['Amount', 'Credits', 'Debits']))
        amount_ratio = transactions_with_amounts / len(transactions)
        if amount_ratio < 0.9:
            score -= 30
            issues.append(f'Only {amount_ratio:.0%} have valid amounts')
        
        # Check 3: Valid descriptions (not empty, not just numbers)
        valid_descriptions = sum(1 for t in transactions
                                if 'Place' in t 
                                and len(str(t['Place'])) >= 3
                                and any(c.isalpha() for c in str(t['Place'])))
        desc_ratio = valid_descriptions / len(transactions)
        if desc_ratio < 0.8:
            score -= 30
            issues.append(f'Only {desc_ratio:.0%} have valid descriptions')
        
        # Check 4: Reasonable transaction count (not too few)
        if len(transactions) < 3:
            score -= 20
            issues.append(f'Very few transactions ({len(transactions)})')
        
        # Check 5: No duplicate descriptions (sign of parsing errors)
        descriptions = [t.get('Place', '') for t in transactions]
        unique_ratio = len(set(descriptions)) / len(descriptions) if descriptions else 0
        if unique_ratio < 0.5:
            score -= 10
            issues.append(f'Many duplicates (uniqueness: {unique_ratio:.0%})')
        
        return {
            'valid': score >= 50,
            'score': max(0, score),
            'transaction_count': len(transactions),
            'issues': issues,
            'method': method
        }
    
    def extract_text_dual_method(self, pdf_path: Path) -> Tuple[str, str, List[Dict], List[Dict]]:
        """
        Extract using BOTH pdfplumber and OCR, validate both, use the better one.
        
        Returns:
            (best_text, method_used, validation_results_pdf, validation_results_ocr)
        """
        print(f"  → Extracting with pdfplumber...")
        
        # Method 1: pdfplumber (fast, accurate for digital PDFs)
        text_pdf = ''
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_pdf += page_text + '\n\n'
        except Exception as e:
            print(f"  ⚠ pdfplumber failed: {e}")
        
        # Parse and validate pdfplumber results
        transactions_pdf = []
        validation_pdf = {'valid': False, 'score': 0}
        if len(text_pdf.strip()) > 100:
            transactions_pdf = self.parse_transactions(text_pdf)
            validation_pdf = self.validate_transactions(transactions_pdf, 'pdfplumber')
            print(f"  → pdfplumber: {validation_pdf['transaction_count']} transactions, quality score: {validation_pdf['score']:.0f}/100")
        else:
            print(f"  → pdfplumber: No text extracted")
        
        # Method 2: OCR (slower, works on scanned PDFs)
        print(f"  → Extracting with OCR...")
        if not self.pdf_converter:
            self.pdf_converter = PDF2ImageConvertor(dpi=400)
            self.text_extractor = TextExtract()
        
        text_ocr = ''
        try:
            images = self.pdf_converter.convert(str(pdf_path))
            for image in images:
                page_text = self.text_extractor.extract_text(image)
                if page_text:
                    text_ocr += page_text + '\n\n'
        except Exception as e:
            print(f"  ⚠ OCR failed: {e}")
        
        # Parse and validate OCR results
        transactions_ocr = []
        validation_ocr = {'valid': False, 'score': 0}
        if len(text_ocr.strip()) > 100:
            transactions_ocr = self.parse_transactions(text_ocr)
            validation_ocr = self.validate_transactions(transactions_ocr, 'OCR')
            print(f"  → OCR: {validation_ocr['transaction_count']} transactions, quality score: {validation_ocr['score']:.0f}/100")
        else:
            print(f"  → OCR: No text extracted")
        
        # Smart merge: Cross-reference both methods for best accuracy
        if transactions_pdf and transactions_ocr:
            # Both methods produced results - cross-reference them
            merged_transactions = self.cross_reference_transactions(
                transactions_pdf, transactions_ocr, 'pdfplumber', 'OCR'
            )
            
            # Use the text from the better scoring method for bank detection
            if validation_pdf['score'] >= validation_ocr['score']:
                best_text = text_pdf
                best_method = 'pdfplumber + OCR (merged)'
            else:
                best_text = text_ocr
                best_method = 'OCR + pdfplumber (merged)'
            
            print(f"  ✓ Using merged results from both methods")
            return best_text, best_method, merged_transactions, {
                'valid': True,
                'score': max(validation_pdf['score'], validation_ocr['score']),
                'transaction_count': len(merged_transactions),
                'method': best_method,
                'issues': []  # No issues when merging succeeds
            }
        
        # Fallback: Only one method worked, or choose better one
        elif transactions_pdf:
            print(f"  ✓ Using pdfplumber only")
            return text_pdf, 'pdfplumber', transactions_pdf, validation_pdf
        elif transactions_ocr:
            print(f"  ✓ Using OCR only")
            return text_ocr, 'OCR', transactions_ocr, validation_ocr
        else:
            # Neither worked well - use the better scored one
            if validation_pdf['score'] >= validation_ocr['score']:
                print(f"  ⚠ Both methods have low quality, using pdfplumber (score: {validation_pdf['score']:.0f})")
                return text_pdf, 'pdfplumber (low quality)', transactions_pdf, validation_pdf
            else:
                print(f"  ⚠ Both methods have low quality, using OCR (score: {validation_ocr['score']:.0f})")
                return text_ocr, 'OCR (low quality)', transactions_ocr, validation_ocr
    
    def _fix_ocr_date_errors(self, date_str: str) -> str:
        """
        Fix common OCR date recognition errors.
        
        Common OCR mistakes:
        - "42" → "12" (4 misread as 1)
        - "01" → "04" (1 misread as 4)
        - etc.
        
        Strategy: Validate month is 1-12, if not, try to correct
        """
        if not date_str or '/' not in date_str:
            return date_str
        
        parts = date_str.split('/')
        if len(parts) < 2:
            return date_str
        
        try:
            month = int(parts[0])
            
            # Month must be 1-12
            if month > 12:
                # Common OCR errors for months
                corrections = {
                    42: 12,  # "42" → "12" (4 looks like 1)
                    41: 11,  # "41" → "11"
                    40: 10,  # "40" → "10"
                    14: 11,  # "14" → "11" (sometimes)
                    13: 11,  # "13" might be "11"
                }
                
                if month in corrections:
                    corrected_month = corrections[month]
                    parts[0] = str(corrected_month).zfill(2 if month >= 10 else 1)
                    corrected = '/'.join(parts)
                    return corrected
                
                # Try digit swap (42 → 24, but 24 is invalid, so → 12)
                if month // 10 > 1:  # First digit > 1
                    # Try setting first digit to 0 or 1
                    second_digit = month % 10
                    if second_digit <= 2:
                        # e.g., 42 → 12, 41 → 11
                        corrected_month = 10 + second_digit
                        parts[0] = str(corrected_month)
                        corrected = '/'.join(parts)
                        return corrected
        except (ValueError, IndexError):
            pass
        
        return date_str
    
    def parse_transaction_block(self, lines: List[str], start_idx: int, statement_year: int = None) -> Tuple[Optional[Dict], int]:
        """
        Parse a transaction that may span multiple lines.
        
        Complex patterns to handle:
        1. Simple: "01/15/2025 MERCHANT NAME $100.00 $1,000.00"
        2. Two date format: "12/31/24 12/31/24 REF# MERCHANT NAME 37.62" (Magnifi)
        3. Split description before amounts:
           "MERCHANT NAME DETAILS 1/01/25"  (description with partial date)
           "01/02/2025 $500.00 $1,912.93"   (full date + amounts)
           "ADDITIONAL INFO"                 (optional continuation)
        4. Description after date:
           "01/16/2025 Cash App Samuel Sch T3FD6RY4CNBR9PE $220.29 $3,365.52"
        5. Scheels format (MM-DD with 2-line transaction):
           "12-16 12-17 24445004352400212869805 WMSUPERCENTER #4352 $91.99"
           "FARGO ND"
        
        Returns:
            (transaction_dict or None, lines_consumed)
        """
        if statement_year is None:
            statement_year = datetime.now().year
            
        if start_idx >= len(lines):
            return None, 0
        
        current_line = lines[start_idx].strip()
        if not current_line:
            return None, 1
        
        # Check for date patterns: MM/DD/YYYY, MM/DD/YY, or MM-DD (Scheels format)
        date_pattern_long = r'^(\d{1,2}/\d{1,2}/\d{4})'  # MM/DD/YYYY
        date_pattern_short = r'^(\d{1,2}/\d{1,2}/\d{2})'  # MM/DD/YY
        date_pattern_dash = r'^(\d{1,2}-\d{1,2})\s'  # MM-DD (Scheels)
        
        date_match = re.match(date_pattern_long, current_line)
        if not date_match:
            date_match = re.match(date_pattern_short, current_line)
            if date_match:
                # Convert 2-digit year to 4-digit (assume 2000s)
                date_parts = date_match.group(1).split('/')
                trans_date = f"{date_parts[0]}/{date_parts[1]}/20{date_parts[2]}"
            else:
                # Try dash format (Scheels: MM-DD, need to add year from statement)
                date_match = re.match(date_pattern_dash, current_line)
                if date_match:
                    # Convert to MM/DD/YYYY format using statement year
                    date_str = date_match.group(1)
                    month_day = date_str.replace('-', '/')
                    trans_date = f"{month_day}/{statement_year}"
                else:
                    trans_date = None
        else:
            trans_date = date_match.group(1)
        
        # Validate and fix OCR date errors (e.g., "42/29/2025" → "12/29/2025")
        if trans_date:
            trans_date = self._fix_ocr_date_errors(trans_date)
        
        if date_match:
            # Has date at start
            rest = current_line[date_match.end():].strip()
            
            # Check for second date (Magnifi/Scheels format: "01/15/25 01/15/25 REF# DESC" or "12-16 12-17 REF# DESC")
            second_date_match = (re.match(date_pattern_short, rest) or 
                                re.match(date_pattern_long, rest) or
                                re.match(date_pattern_dash, rest))
            if second_date_match:
                # Skip the second date
                rest = rest[second_date_match.end():].strip()
            
            # Check for reference number (long string of digits, typically 17-20+)
            ref_match = re.match(r'^(\d{17,})\s+', rest)
            if ref_match:
                # Skip reference number
                rest = rest[ref_match.end():].strip()
            
            # Extract amounts from this line
            amounts = []
            for match in re.finditer(r'\$?([0-9,]+\.\d{2})', rest):
                try:
                    clean = match.group(1).replace(',', '')
                    amounts.append(float(clean))
                except ValueError:
                    continue
            
            # Extract description (everything except amounts and reference numbers)
            description = rest
            # Remove amounts - collect all match positions first, then rebuild string
            amount_matches = list(re.finditer(r'\$?[0-9,]+\.\d{2}', description))
            if amount_matches:
                # Build new string without amount matches
                new_desc = ''
                last_end = 0
                for match in amount_matches:
                    new_desc += description[last_end:match.start()]
                    last_end = match.end()
                new_desc += description[last_end:]
                description = new_desc
            
            # Remove any remaining long digit strings (reference numbers)
            description = re.sub(r'\d{17,}', '', description)
            description = ' '.join(description.split()).strip()
            
            # If no description on this line, check PREVIOUS line
            if not description or len(description) < 3 or not any(c.isalpha() for c in description):
                if start_idx > 0:
                    prev_line = lines[start_idx - 1].strip()
                    # Only use prev line if it doesn't start with a date and has meaningful text
                    has_date = (re.match(date_pattern_long, prev_line) or 
                               re.match(date_pattern_short, prev_line) or 
                               re.match(date_pattern_dash, prev_line))
                    # Also skip if previous line looks like a time or short fragment
                    is_time = re.match(r'^\d{1,2}:\d{2}$', prev_line)
                    if prev_line and not has_date and not is_time and any(c.isalpha() for c in prev_line) and len(prev_line) > 5:
                        description = prev_line
            
            # Check next line for additional description info
            lines_consumed = 1
            if start_idx + 1 < len(lines):
                next_line = lines[start_idx + 1].strip()
                # If next line has text but no date, it's continuation
                has_date = (re.match(date_pattern_long, next_line) or 
                           re.match(date_pattern_short, next_line) or 
                           re.match(date_pattern_dash, next_line))
                
                if next_line and not has_date:
                    # Check if it's meaningful continuation (not just numbers)
                    if any(c.isalpha() for c in next_line) and '$' not in next_line:
                        description += ' ' + next_line
                        lines_consumed += 1
            
            if not description or not amounts:
                return None, lines_consumed
            
            return self._build_transaction(trans_date, description, amounts), lines_consumed
        
        else:
            # Pattern 2: Description first, then date+amounts on next line
            # Current line is description (should have text, maybe partial date)
            if not any(c.isalpha() for c in current_line):
                return None, 1
            
            description = current_line
            
            # Remove partial date from end if present (e.g., "1/01/25")
            description = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}$', '', description)
            
            # Look for date+amounts on next line
            if start_idx + 1 >= len(lines):
                return None, 1
            
            next_line = lines[start_idx + 1].strip()
            date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})', next_line)
            
            if not date_match:
                return None, 1
            
            trans_date = date_match.group(1)
            rest = next_line[date_match.end():].strip()
            
            # Extract amounts
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
            
            # Check for additional info on line after amounts
            if start_idx + 2 < len(lines):
                third_line = lines[start_idx + 2].strip()
                if third_line and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}', third_line):
                    if any(c.isalpha() for c in third_line) and '$' not in third_line:
                        # Additional info like "AT 9:30"
                        description += ' ' + third_line
                        lines_consumed += 1
            
            return self._build_transaction(trans_date, description, amounts), lines_consumed
    
    def _build_transaction(self, date: str, description: str, amounts: List[float]) -> Dict:
        """Build transaction dict from parsed components."""
        description = ' '.join(description.split()).strip()
        
        # Filter out garbage descriptions (page headers, footers, fragments)
        desc_upper = description.upper()
        garbage_patterns = [
            'DATE AMOUNT',
            'DESCRIPTION DEBITS CREDITS',
            'POST DATE',
            'TRANS DATE',
            'REFERENCE',
            'PAGE',
            'ACCOUNT STATEMENTS',
            'STATEMENT ENDING',
            'CUSTOMER NUMBER',
            'CHECKING ACCOUNT',
            'SAVINGS ACCOUNT',
            'DAILY BALANCE',
            'DATE AMOUNT DATE AMOUNT',
            'BEGINNING BALANCE',
            'ENDING BALANCE'
        ]
        
        for pattern in garbage_patterns:
            if pattern in desc_upper:
                return None  # Invalid transaction
        
        # Filter out fragments (< 2 words or very short)
        words = description.split()
        if len(words) == 1 and len(description) < 4:
            return None  # Single short word is probably a fragment
        
        # Filter out very short or non-meaningful descriptions
        if len(description) < 3 or not any(c.isalpha() for c in description):
            return None
        
        # Save original before cleaning
        original_description = description
        
        # Get the amount for context-aware cleaning
        amount = amounts[0] if amounts else None
        
        # Clean up the merchant name for readability (pass context)
        description = self._clean_merchant_name_with_context(description, amount, date)
        
        trans = {
            'Transaction Date': date,
            'Place': description,
            'Place_Original': original_description  # Save for transfer detection
        }
        
        # Assign amounts based on count
        if len(amounts) == 1:
            trans['Amount'] = amounts[0]
        elif len(amounts) == 2:
            # transaction amount + balance
            trans['Amount'] = amounts[0]
            trans['Balance'] = amounts[1]
        elif len(amounts) >= 3:
            # debits, credits, balance (or debit, credit, balance)
            trans['Debits'] = amounts[0] if amounts[0] > 0 else None
            trans['Credits'] = amounts[1] if amounts[1] > 0 else None
            trans['Balance'] = amounts[2]
        
        return trans
    
    def _normalize_llm_output(self, name: str) -> str:
        """
        Post-process LLM output to fix common issues across all models.
        
        Handles:
        - Extra explanatory text in parentheses
        - "No location information" artifacts
        - All caps -> Title Case
        - Missing spaces between words
        - Extra words after main business name
        """
        if not name:
            return name
        
        # Remove common LLM artifacts
        artifacts = [
            r'\(No location information.*?\)',
            r'\(No location.*?\)',
            r'No location information provided.*',
            r'Yes, the transaction name is:?',
            r'The transaction name is:?',
            r'A fun one!',
            r'A fun transaction!',
            r'the transaction details:',
        ]
        
        for pattern in artifacts:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        name = name.strip()
        
        # Remove trailing/leading punctuation artifacts
        name = re.sub(r'^[,\s]+|[,\s]+$', '', name)
        
        # Fix all caps -> Title Case (but preserve known acronyms)
        if name.isupper() and len(name) > 3:
            # Check if it's a known acronym (2-4 letters, all caps)
            if len(name) <= 4 and name.isalpha():
                pass  # Keep BP, TST, YSI, etc as-is
            else:
                # Title case it
                name = name.title()
        
        # Remove "THE " prefix if present
        if name.upper().startswith('THE '):
            name = name[4:]
        
        # Add space before caps in concatenated words (COWBOYJACKS -> Cowboy Jacks)
        # But only if no spaces exist and it's mixed case
        if ' ' not in name and any(c.isupper() for c in name[1:]):
            # Insert space before capital letters
            name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # Remove extra words after known business names
        # "Steam Purchase" -> "Steam", "Walmart Supercenter" -> "Walmart"
        extra_words = [
            'Purchase', 'Supercenter', 'Store', 'Location', 'Branch',
            'Retailer', 'LLC', 'Inc', 'Corporation', 'Company'
        ]
        for word in extra_words:
            # Only remove if it's the last word
            if name.endswith(f' {word}'):
                name = name[:-len(word)-1].strip()
        
        return name.strip()
    
    def _clean_merchant_name_with_context(self, name: str, amount: float = None, date: str = None) -> str:
        """
        Clean merchant name with transaction context for better accuracy.
        
        Strategy:
        1. Check historical cache (instant, consistent)
        2. Apply pattern-based cleaning (remove codes, prefixes, noise)
        3. Pass to multi-LLM validation (3 prompts + confidence scoring)
        4. Post-process to normalize LLM output (remove artifacts)
        5. Save to cache for future runs
        6. Fallback to smart title case if LLM unavailable
        """
        if not name or len(name) < 3:
            return name
        
        original = name
        
        # Phase 0: Check cache (instant lookup, ensures consistency)
        cache_key = name.upper().strip()
        if cache_key in self.merchant_cache:
            return self.merchant_cache[cache_key]
        
        # Phase 1: Pattern-based cleaning (remove noise)
        name = self._clean_merchant_name(name)
        
        # Phase 2: If LLM available, do context-aware refinement
        if self.llm_available and len(name) > 3:
            context_cleaned = self.llm_clean_merchant_name(name, amount, date)
            if context_cleaned and context_cleaned != name and len(context_cleaned) >= 3:
                # Phase 3: Normalize LLM output (remove common artifacts)
                context_cleaned = self._normalize_llm_output(context_cleaned)
                
                # Save to cache for future runs
                if len(context_cleaned) >= 3:
                    self.merchant_cache[cache_key] = context_cleaned
                    return context_cleaned
        
        # Save pattern-cleaned result to cache
        if name != original:
            self.merchant_cache[cache_key] = name
        
        return name
    
    def _clean_merchant_name(self, name: str) -> str:
        """
        Clean merchant names dynamically - no static store lists.
        
        Phase 1: Remove noise (codes, numbers, locations)
        Phase 2: LLM intelligent cleaning
        Phase 3: Fallback to smart title case
        """
        if not name or len(name) < 3:
            return name
        
        original = name
        
        # === PHASE 1: PATTERN-BASED NOISE REMOVAL ===
        
        # ATM withdrawals - special case
        if re.match(r'^\$[\d,]+\.?\d*\s+AT\s+\d{1,2}:\d{2}', name):
            return 'ATM Withdrawal'
        
        # Remove card numbers
        name = re.sub(r'\bXX+\d{4}\b', '', name)
        
        # Remove common OCR/parsing artifacts and prefixes
        name = re.sub(r'^(Gino|Jaison|jazionn)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^(Payment\.ACH|Payment\.|ACH\s+)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^[=\-><]\s+', '', name)  # Leading special characters
        
        # Remove transaction type prefixes (more comprehensive)
        name = re.sub(r'^(RECUR\.?\s*PURCHASE\.?\s*|POS\s+(?:PURCHASE\s+)?AT\s+|PURCHASE\s+AT\s+)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+RECUR\s+PURCHASE\.?\s*', ' ', name, flags=re.IGNORECASE)
        
        # Remove leading single digits (like "7 Walmart")
        name = re.sub(r'^\d{1,2}\s+', '', name)
        
        # Remove store numbers attached to names (Autozone6252 → Autozone)
        name = re.sub(r'(\w)(\d{3,})(?=\s|$)', r'\1', name)
        
        # Remove trailing incomplete words/codes
        name = re.sub(r'\s+[A-Z0-9]{1,2}$', '', name)  # Single/double char codes at end
        
        # Remove phone numbers early (various formats)
        name = re.sub(r'\s*\d{3}-\d{3}-\d{4}', '', name)
        name = re.sub(r'\s+\d{10}\b', '', name)
        name = re.sub(r'\s+\d{3}-\d{7}', '', name)
        
        # Clean up specific patterns
        # Remove reference codes (alphanumeric strings 10+ chars that are mostly numbers)
        name = re.sub(r'\s+[A-Z0-9]{10,}\b', '', name)  # Increased to 10+ to preserve business names
        name = re.sub(r'\s+[a-f0-9]{8,}\b', '', name)  # hex codes
        
        # Remove payment reference numbers (mostly digits)
        name = re.sub(r'\s+\d{8,}\b', '', name)  # Changed from 10+ to 8+
        
        # Payment processor patterns (easy to add/modify)
        # Format: (pattern, action) where action is 'return:Name' or 'strip' or 'extract'
        processor_patterns = {
            r'^SQSP\s*\*': ('return', 'Squarespace'),      # Squarespace (no merchant name after)
            r'^CASH\s+APP\s*\*': ('return', 'Cash App'),   # Cash App (personal name follows, not merchant)
            r'^BP[#\d]': ('return', 'BP'),                 # BP gas (location codes follow)
            r'^SQ\s*\*': ('extract', r'SQ\s*\*\s*([A-Z][A-Z0-9&\s]+)'),  # Square (merchant after prefix)
            r'^WL\s*\*': ('strip', r'^WL\s*\*\s*'),        # WorldLine (merchant after prefix)
        }
        
        # Process payment processors
        for pattern, (action, value) in processor_patterns.items():
            if re.match(pattern, name, flags=re.IGNORECASE):
                if action == 'return':
                    return value  # Return immediately, no further processing
                elif action == 'extract':
                    match = re.search(value, name, flags=re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                    else:
                        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
                    break  # Continue to LLM cleaning
                elif action == 'strip':
                    name = re.sub(value, '', name, flags=re.IGNORECASE).strip()
                    break  # Continue to LLM cleaning
        
        # Remove other processor prefixes
        name = re.sub(r'\s+WEB[ _](?:PMTS?|PAY)\s+\S+', '', name, flags=re.IGNORECASE)
        
        # Remove store # patterns and location codes
        name = re.sub(r'\s*#\s*\d+', '', name)
        
        # Remove trailing gibberish/codes (e.g., "APPLEV", "CITY#")
        name = re.sub(r'[-\s]+[A-Z]{5,}$', '', name)  # Remove trailing all-caps 5+ letters
        name = re.sub(r'\s+\d{3}-\d{7}$', '', name)  # Remove phone numbers at end
        
        # Remove percentage codes (%01/31/2025%)
        name = re.sub(r'%[^%]+%', '', name)
        
        # Remove trailing zip codes
        name = re.sub(r'\s+\d{4,5}$', '', name)
        
        # Remove city/state patterns at end (generic pattern)
        name = re.sub(r'\s+[A-Z][a-z]+\s+[A-Z]{2}$', '', name)
        
        # Remove standalone state codes at end
        name = re.sub(r'\s+[A-Z]{2}\s*\d*$', '', name)
        
        # Remove prefixes like TST-, SQ-, PAW-
        name = re.sub(r'^(?:TST|SQ|PAW)\s*-\s*', '', name, flags=re.IGNORECASE)
        
        # Remove trailing codes like "8 MN 7" or "425-9"
        name = re.sub(r'\s+\d+\s+[A-Z]{2}\s+\d+$', '', name)
        name = re.sub(r'\s+\d{3}-\d+$', '', name)
        
        # Remove OIL suffix from gas stations
        name = re.sub(r'\s+OIL$', '', name, flags=re.IGNORECASE)
        
        # Handle asterisk processor codes (WINRED* TRUMP NATI → WinRed Trump Nati)
        if '*' in name:
            parts = name.split('*', 1)
            if len(parts) == 2:
                name = f"{parts[0].strip()} {parts[1].strip()}"
        
        # Remove domain patterns
        name = re.sub(r'\s+Help\.\w+\.Com', '', name, flags=re.IGNORECASE)
        
        # Remove highway numbers
        name = re.sub(r'\s+Hwy\s+\d+', '', name, flags=re.IGNORECASE)
        
        # Remove standalone hyphens
        name = re.sub(r'\s+-\s*$', '', name)
        name = re.sub(r'^\s*-\s+', '', name)
        
        # Remove short trailing codes (A109B, EH)
        name = re.sub(r'\s+[A-Z]\d+[A-Z]$', '', name)
        name = re.sub(r'\s+[A-Z]{1,2}$', '', name)
        
        # Clean up whitespace
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Remove trailing numbers
        name = re.sub(r'\s+\d+$', '', name)
        
        # Decompress concatenated business names (add spaces before capitals)
        # But only for long all-caps strings without spaces
        if len(name) > 15 and name.isupper() and ' ' not in name[:10]:
            # Add space before 'AND' in middle of name
            name = re.sub(r'([A-Z])AND([A-Z])', r'\1 AND \2', name)
            # Add space at word boundaries (e.g., PIKEAND PINTGRILLINC → PIKE AND PINT GRILL INC)
            name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # === PHASE 2: LLM INTELLIGENT CLEANING ===
        
        if self.llm_available and len(name) > 3:
            cleaned = self.llm_clean_merchant_name(name)
            if cleaned and cleaned != name and len(cleaned) >= 3:
                return cleaned
        
        # === PHASE 3: FALLBACK - SMART TITLE CASE ===
        # Only used if LLM is unavailable or fails
        
        # Add spaces before capitals in compound words (CashWise → Cash Wise)
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # Title case but preserve certain acronyms
        words = name.split()
        cleaned_words = []
        for word in words:
            # Preserve known acronyms
            if word.upper() in ['ATM', 'POS', 'ACH', 'USA', 'LLC', 'INC', 'BP', 'ND', 'MN']:
                cleaned_words.append(word.upper())
            # Title case long uppercase words
            elif len(word) > 2 and word.isupper():
                cleaned_words.append(word.title())
            else:
                cleaned_words.append(word)
        name = ' '.join(cleaned_words)
        
        # If we cleaned too much, return original
        if len(name) < 3:
            return original
        
        return name.strip()
    
    def parse_transactions(self, text: str, statement_year: Optional[int] = None) -> List[Dict]:
        """Parse all transactions from text"""
        if statement_year is None:
            statement_year = self.extract_statement_year(text)
        
        lines = text.split('\n')
        transactions = []
        
        # Look for transaction section markers
        in_transaction_section = False
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            line_upper = line.upper()
            
            # Detect transaction section start
            if any(marker in line_upper for marker in [
                'ACCOUNT ACTIVITY', 'TRANSACTION HISTORY', 'TRANSACTIONS',
                'POST DATE', 'TRANS DATE', 'POSTING', 'DESCRIPTION OF TRANSACTION'
            ]):
                in_transaction_section = True
                i += 1
                continue
            
            # Detect section end
            if in_transaction_section and any(marker in line_upper for marker in [
                'TOTAL DEBITS', 'TOTAL CREDITS', 'INTEREST SUMMARY', 'FEES SUMMARY',
                'PAGE 2', 'PAGE 3', 'PAGE 4', 'STATEMENT CLOSING', 'IMPORTANT INFORMATION',
                'OVERDRAFT', 'DIRECT DEPOSIT', 'INTEREST RATE', 'DAILY BALANCES',
                'DAILY BALANCE', 'ENDING BALANCE'
            ]):
                in_transaction_section = False
                i += 1
                continue
            
            # Skip summary lines (before transaction section or within)
            if any(skip in line_upper for skip in [
                'BEGINNING BALANCE', 'ENDING BALANCE', 'CREDIT(S) THIS PERIOD',
                'DEBIT(S) THIS PERIOD', 'INTEREST PAID', 'ANNUAL PERCENTAGE',
                'INTEREST DAYS', 'INTEREST EARNED FROM'
            ]):
                i += 1
                continue
            
            # Skip header lines
            if any(header in line_upper for header in [
                'POST DATE DESCRIPTION', 'DATE DESCRIPTION DEBITS',
                'TRANS DATE', 'REFERENCE'
            ]):
                i += 1
                continue
            
            # Skip if not in transaction section and line doesn't start with date
            if not in_transaction_section and not re.match(r'^\d{1,2}[/-]\d{1,2}', line):
                i += 1
                continue
            
            # Try to parse transaction
            trans, consumed = self.parse_transaction_block(lines, i, statement_year)
            if trans and trans.get('Place'):  # Only add if we have a description
                transactions.append(trans)
            
            i += consumed if consumed > 0 else 1
        
        return transactions
    
    def _select_best_description(self, place_a: str, place_b: str, orig_a: str, orig_b: str) -> str:
        """
        Select the best merchant description from two sources.
        
        Scoring criteria:
        - Shorter is better (less noise)
        - Fewer artifacts (PURCHASE, RECUR, WL*, etc.)
        - More readable (proper capitalization)
        - No transaction prefixes
        """
        def score_description(place: str, original: str) -> int:
            score = 100
            
            # Penalize artifacts heavily
            artifacts = ['PURCHASE', 'RECUR', 'WL*', 'WL ', 'SQ*', 'TST*', 'Payment.', 
                        'Gino ', 'Jaison ', 'XX', 'POS ', 'ACH ']
            for artifact in artifacts:
                if artifact in place or artifact in place.upper():
                    score -= 30
            
            # Penalize long descriptions (likely have extra junk)
            if len(place) > 40:
                score -= 20
            elif len(place) > 25:
                score -= 10
            
            # Penalize too many words (likely concatenated)
            word_count = len(place.split())
            if word_count > 5:
                score -= 15
            elif word_count > 4:
                score -= 5
            
            # Reward proper capitalization
            if place and place[0].isupper():
                score += 5
            
            # Penalize if starts with lowercase or number
            if place and (place[0].islower() or place[0].isdigit()):
                score -= 10
            
            # Penalize special characters at start
            if place and place[0] in ['=', '-', '>', '<']:
                score -= 20
            
            return score
        
        score_a = score_description(place_a, orig_a)
        score_b = score_description(place_b, orig_b)
        
        # Use the higher scoring description
        if score_a >= score_b:
            return place_a
        else:
            return place_b
    
    def cross_reference_transactions(self, transactions_a: List[Dict], transactions_b: List[Dict], 
                                     method_a: str, method_b: str) -> List[Dict]:
        """
        Cross-reference transactions from two extraction methods and merge intelligently.
        
        Strategy:
        1. Match transactions by date + amount (with tolerance)
        2. When matched, use the better description (longer, more complete)
        3. Include unique transactions from both sources
        4. Mark ambiguous cases
        
        Returns: Merged list of best transactions
        """
        if not transactions_a and not transactions_b:
            return []
        if not transactions_a:
            return transactions_b
        if not transactions_b:
            return transactions_a
        
        merged = []
        matched_b = set()
        
        print(f"  → Cross-referencing {len(transactions_a)} ({method_a}) vs {len(transactions_b)} ({method_b}) transactions...")
        
        # Pass 1: Find matches and merge
        for trans_a in transactions_a:
            date_a = trans_a.get('Transaction Date', '')
            amount_a = trans_a.get('Amount', trans_a.get('Debits', trans_a.get('Credits', 0)))
            
            best_match = None
            best_match_idx = None
            
            # Look for matching transaction in B
            for idx, trans_b in enumerate(transactions_b):
                if idx in matched_b:
                    continue
                    
                date_b = trans_b.get('Transaction Date', '')
                amount_b = trans_b.get('Amount', trans_b.get('Debits', trans_b.get('Credits', 0)))
                
                # Match criteria: same date AND amount within 1 cent tolerance
                if date_a == date_b and abs(float(amount_a) - float(amount_b)) < 0.02:
                    best_match = trans_b
                    best_match_idx = idx
                    break
            
            if best_match:
                # Found a match - merge intelligently using BOTH descriptions
                matched_b.add(best_match_idx)
                
                place_a = trans_a.get('Place', '')
                place_b = best_match.get('Place', '')
                place_orig_a = trans_a.get('Place_Original', place_a)
                place_orig_b = best_match.get('Place_Original', place_b)
                
                # Select the cleaner ORIGINAL description, then re-clean it
                # This ensures we start with the best raw data before cleaning
                selected_original = self._select_best_description(place_orig_a, place_orig_b, place_orig_a, place_orig_b)
                
                # Re-clean the selected original with CONTEXT for best result
                amount = trans_a.get('Amount', trans_a.get('Debits', trans_a.get('Credits', 0)))
                date = trans_a.get('Transaction Date', '')
                cleaned_place = self._clean_merchant_name_with_context(selected_original, amount, date)
                
                # Start with trans_a as base, update with best cleaned description
                merged_trans = trans_a.copy()
                merged_trans['Place'] = cleaned_place
                merged_trans['Place_Original'] = selected_original
                merged_trans['_extraction_method'] = f'{method_a} (matched with {method_b})'
                
                merged.append(merged_trans)
            else:
                # No match found - include unique transaction from A
                trans_a_copy = trans_a.copy()
                trans_a_copy['_extraction_method'] = f'{method_a} only'
                merged.append(trans_a_copy)
        
        # Pass 2: Add unmatched transactions from B
        for idx, trans_b in enumerate(transactions_b):
            if idx not in matched_b:
                trans_b_copy = trans_b.copy()
                trans_b_copy['_extraction_method'] = f'{method_b} only'
                merged.append(trans_b_copy)
        
        # Sort by date
        merged.sort(key=lambda x: x.get('Transaction Date', ''))
        
        unique_from_a = sum(1 for t in merged if 'only' in t.get('_extraction_method', '') and method_a in t['_extraction_method'])
        unique_from_b = sum(1 for t in merged if 'only' in t.get('_extraction_method', '') and method_b in t['_extraction_method'])
        matched_count = len(merged) - unique_from_a - unique_from_b
        
        print(f"  → Merged: {matched_count} matched, {unique_from_a} unique from {method_a}, {unique_from_b} unique from {method_b}")
        print(f"  → Total: {len(merged)} transactions")
        
        return merged
    
    def filter_transfers(self, transactions: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Separate transfers from real transactions using config keywords."""
        real_transactions = []
        transfers = []
        
        for trans in transactions:
            # Use original place for transfer detection (before cleaning)
            place = trans.get('Place_Original', trans.get('Place', '')).upper()
            
            # Check against transfer keywords
            is_transfer = any(keyword in place for keyword in self.transfer_keywords)
            
            if is_transfer:
                transfers.append(trans)
            else:
                real_transactions.append(trans)
        
        return real_transactions, transfers
    
    def classify_transactions(self, transactions: List[Dict], is_bank_account: bool) -> Tuple[List[Dict], List[Dict]]:
        """
        Classify transactions into income vs expenses.
        Uses LLM for ambiguous cases.
        
        For bank accounts: Credits = income, Debits = expenses
        For credit cards: All are expenses (credits are purchases)
        """
        income = []
        expenses = []
        
        for trans in transactions:
            place = trans.get('Place', '').upper()
            place_original = trans.get('Place_Original', place).upper()  # Use original for keyword matching
            amount = trans.get('Amount', trans.get('Credits', trans.get('Debits', 0)))
            
            # Check if it's a payment app (needs manual review) - check both cleaned and original
            is_payment_app = any(app in place or app in place_original for app in self.payment_apps)
            if is_payment_app:
                trans['_manual_review'] = True
            
            if is_bank_account:
                # Bank account logic
                has_credits = 'Credits' in trans and trans['Credits'] and trans['Credits'] > 0
                has_debits = 'Debits' in trans and trans['Debits'] and trans['Debits'] > 0
                has_amount = 'Amount' in trans and trans['Amount'] and trans['Amount'] > 0
                
                if has_credits:
                    # Has explicit credit column - this is income
                    income.append(trans)
                elif has_debits:
                    # Has explicit debit column - this is expense
                    expenses.append(trans)
                elif has_amount:
                    # Single amount column - determine by keywords or LLM
                    # IMPORTANT: Check original text before cleaning for keywords like "PAYROLL"
                    is_income_keyword = any(keyword in place_original for keyword in self.income_keywords)
                    
                    if is_income_keyword:
                        income.append(trans)
                    elif self.llm_available and is_payment_app:
                        # Use LLM for ambiguous payment app transactions
                        classification = self.llm_classify_transaction(place, amount)
                        if classification == 'income':
                            income.append(trans)
                        else:
                            expenses.append(trans)
                    else:
                        # Default to expense for bank accounts with single amount
                        expenses.append(trans)
            else:
                # Credit card - all are expenses
                expenses.append(trans)
        
        return income, expenses
    
    def parse_pdf(self, pdf_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, str, bool]:
        """
        Parse a bank statement PDF using dual extraction + validation.
        
        Returns:
            (income_df, expenses_df, bank_name, is_bank_account)
        """
        print(f"\n📄 Parsing {pdf_path.name}...")
        
        # Extract text using BOTH methods and validate
        text, method, transactions, validation = self.extract_text_dual_method(pdf_path)
        
        if validation['issues']:
            print(f"  ⚠ Validation issues: {', '.join(validation['issues'])}")
        
        # Detect bank and account type
        bank_name = self.detect_bank_name(text)
        is_bank_account = not self.is_credit_card(text)
        
        print(f"  Bank: {bank_name}")
        print(f"  Type: {'Bank Account' if is_bank_account else 'Credit Card'}")
        
        # Use pre-parsed transactions if available, otherwise parse now
        if not transactions:
            transactions = self.parse_transactions(text)
        
        print(f"  ✓ Found {len(transactions)} transaction(s)")
        
        # Filter out transfers
        transactions, transfers = self.filter_transfers(transactions)
        if transfers:
            print(f"  ℹ Skipped {len(transfers)} transfer(s)")
        
        # Classify into income/expenses
        income, expenses = self.classify_transactions(transactions, is_bank_account)
        print(f"  ✓ {len(income)} income, {len(expenses)} expenses")
        
        # Convert to DataFrames
        income_df = pd.DataFrame(income) if income else pd.DataFrame()
        expenses_df = pd.DataFrame(expenses) if expenses else pd.DataFrame()
        
        # Add source column
        if not income_df.empty:
            income_df['Statement'] = bank_name
        if not expenses_df.empty:
            expenses_df['Statement'] = bank_name
        
        # Save merchant cache for future runs (improves consistency)
        if self.merchant_cache:
            self._save_merchant_cache()
        
        return income_df, expenses_df, bank_name, is_bank_account


def main():
    """Test the hybrid parser."""
    parser = HybridPDFParser()
    
    test_dir = Path('statements/2025-01')
    pdfs = list(test_dir.glob('*.pdf'))
    
    print(f"Found {len(pdfs)} PDF(s)\n")
    print("="*80)
    
    for pdf_path in pdfs:
        income_df, expenses_df, bank, is_bank = parser.parse_pdf(pdf_path)
        
        if not income_df.empty:
            print(f"\n  Income transactions:")
            # Show available columns dynamically
            cols = ['Transaction Date', 'Place']
            if 'Credits' in income_df.columns:
                cols.append('Credits')
            elif 'Amount' in income_df.columns:
                cols.append('Amount')
            print(income_df[cols].head())
        
        if not expenses_df.empty:
            print(f"\n  Expense transactions:")
            cols = ['Transaction Date', 'Place']
            if 'Debits' in expenses_df.columns:
                cols.append('Debits')
            elif 'Amount' in expenses_df.columns:
                cols.append('Amount')
            print(expenses_df[cols].head(10))
        
        print("\n" + "="*80)


if __name__ == '__main__':
    main()
