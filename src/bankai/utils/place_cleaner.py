"""
Place Name Cleaner

Cleans up merchant/place names extracted from bank statements.
Uses spaCy NER, pattern matching, and optional local LLM (Ollama) enhancement.
"""

import re
from typing import Optional
import requests
import spacy

class PlaceCleaner:
    """Clean up merchant place names from bank statements."""
    
    # Common patterns to remove
    PATTERNS_TO_REMOVE = [
        r'^\d+\s+',      # All numbers at start followed by space
        r'\d{15,}',      # Very long reference numbers anywhere
        r'SQ \*',        # Square payment prefix
        r'TST\*',        # Toast payment prefix
        r'SP ',          # SP prefix
        r'WA ',          # WA prefix
        r'TM \*',        # TM prefix
        r'CPP\*',        # CPP prefix
        r'\*',           # Asterisks
        r'\s+\d{4,}(?=\s)', # Numbers in the middle - preserve trailing space to avoid merging words
    ]
    
    def __init__(self, use_llm: bool = False, ollama_model: str = "dolphin-mistral:latest"):
        """
        Initialize the place name cleaner.
        
        Args:
            use_llm: Whether to use local LLM (Ollama) for enhanced cleaning
            ollama_model: Ollama model to use (default: dolphin-mistral:latest)
        """
        self.use_llm = use_llm
        self.ollama_model = ollama_model
        self.ollama_available = False
        
        if self.use_llm:
            # Check if Ollama is running
            try:
                response = requests.get('http://localhost:11434/api/tags', timeout=2)
                if response.status_code == 200:
                    self.ollama_available = True
                    print(f"✓ Ollama detected, using {ollama_model} for enhanced cleaning")
                else:
                    print("Warning: Ollama not responding. Falling back to spaCy-only cleaning.")
                    print("  To use local LLM: Install Ollama and run 'ollama pull llama3.2:1b'")
                    self.use_llm = False
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                print("Warning: Ollama not running. Falling back to spaCy-only cleaning.")
                print("  To use local LLM: Install Ollama and run 'ollama serve'")
                self.use_llm = False
        
        # Load spaCy model for intelligent location detection (required)
        try:
            self.nlp = spacy.load('en_core_web_sm')
        except OSError:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. This is required for intelligent cleaning.\n"
                "Install with: python -m spacy download en_core_web_sm"
            )
    
    def clean(self, place: str) -> str:
        """
        Clean a place name.
        
        Args:
            place: Raw place name from statement
            
        Returns:
            Cleaned place name
        """
        # If Ollama is available, use LLM-only approach (faster and smarter)
        if self.use_llm and self.ollama_available:
            # Just do basic pattern cleaning, then let LLM handle everything
            cleaned = place.strip()
            # Remove very long reference numbers
            cleaned = re.sub(r'^\d{6,}\s*', '', cleaned)
            cleaned = re.sub(r'\d{6,}', '', cleaned)
            # Clean up whitespace
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            # Let LLM do the intelligent cleaning
            return self._llm_enhance(cleaned)
        
        # Otherwise use spaCy-based pattern cleaning (default)
        return self._pattern_based_clean(place)
    
    def _pattern_based_clean(self, place: str) -> str:
        """Apply intelligent pattern-based cleaning rules without hardcoded merchant lists."""
        cleaned = place.strip()
        
        # Step 1: Remove reference numbers and transaction codes
        # Remove very long numbers at the start (reference numbers like 383639374)
        cleaned = re.sub(r'^\d{6,}\s*', '', cleaned)
        
        # Remove payment processor prefixes
        for pattern in self.PATTERNS_TO_REMOVE:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove trailing long alphanumeric codes (transaction IDs)
        cleaned = re.sub(r'\s+[A-Z0-9]{10,}$', '', cleaned, flags=re.IGNORECASE)
        
        # Remove long numbers attached without space (e.g., Focus3035517373 -> Focus)
        # This needs to be more aggressive
        cleaned = re.sub(r'\d{6,}', '', cleaned)
        
        # Remove 4-5 digit store numbers that appear between merchant name and city
        # (e.g., "CHIPOTLE 3415 FARGO" -> "CHIPOTLE FARGO")
        cleaned = re.sub(r'\s+\d{3,5}(?=\s+[A-Z])', ' ', cleaned)
        
        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Step 2: AI-powered cleaning using spaCy NER
        # Intelligently removes locations, trailing numbers, and store codes
        cleaned = self._remove_locations_with_nlp(cleaned)
        
        # Step 3: Remove formatted numbers that AI can't detect
        # AI handles plain numbers (e.g., "Store 123") but misses special formats
        # Remove store numbers with # prefix (e.g., "Store #3016")
        cleaned = re.sub(r'\s*#\s*\d+', '', cleaned)
        # Remove dash-prefixed numbers (e.g., "Coffee - 140")
        cleaned = re.sub(r'\s*-\s*\d+[-\d]*$', '', cleaned)
        
        # Step 4: Clean up common business suffixes
        # Remove generic business type suffixes at the end
        cleaned = re.sub(r'\s+(Inc|LLC|Ltd|Corp|Company|Co)\s*\.?$', '', cleaned, flags=re.IGNORECASE)
        
        # Step 5: Remove website domains and convert to readable names
        # Convert periods between words to spaces (e.g., "Shop.Deere" -> "Shop Deere")
        cleaned = re.sub(r'\.(?=[A-Z])', ' ', cleaned)
        
        # Convert ".com", ".net" etc to space
        cleaned = re.sub(r'\.(com|net|org|edu)/?', ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove " COM" " NET" etc that result from above
        cleaned = re.sub(r'\s+(COM|NET|ORG|EDU)$', '', cleaned, flags=re.IGNORECASE)
        
        # Step 6: Handle common abbreviations intelligently
        # Expand "WHSE" to "Warehouse"
        cleaned = re.sub(r'\bWHSE\b', 'Warehouse', cleaned, flags=re.IGNORECASE)
        # Expand "SUPERCTR" or "SUPERCENTER" 
        cleaned = re.sub(r'\b(SUPERCTR|SUPERCENTR)\b', 'Supercenter', cleaned, flags=re.IGNORECASE)
        
        # Step 7: Remove numbers embedded in middle of names (store codes)
        # But preserve numbers that are part of brand names
        # Remove standalone 4+ digit numbers in middle
        cleaned = re.sub(r'\s+\d{4,}(?=\s)', ' ', cleaned)
        
        # Step 8: Remove common junk words
        # Remove "External" and trailing codes
        cleaned = re.sub(r'\s+External\s+[A-Z]+$', '', cleaned, flags=re.IGNORECASE)
        
        # Step 9: Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Step 10: Smart capitalization
        # If all uppercase, convert to title case
        # But preserve acronyms and known patterns
        if cleaned.isupper() and len(cleaned) > 3:
            # Handle special cases: Keep 2-3 letter words uppercase (like "AT", "TJ")
            words = cleaned.split()
            cleaned_words = []
            for word in words:
                if len(word) <= 3 and word.isupper():
                    cleaned_words.append(word)  # Keep short acronyms uppercase
                elif "'" in word:
                    # Handle possessives and contractions
                    parts = word.split("'")
                    cleaned_words.append(parts[0].title() + "'" + parts[1].title())
                else:
                    cleaned_words.append(word.title())
            cleaned = ' '.join(cleaned_words)
        
        return cleaned
    
    def _remove_locations_with_nlp(self, text: str) -> str:
        """
        Use spaCy NER to intelligently detect and remove unwanted entities.
        Removes:
        - Locations (cities, states, countries) 
        - Trailing numbers (store codes, reference numbers)
        - Unnecessary suffixes from organization names
        
        Args:
            text: Merchant name with potential suffixes
            
        Returns:
            Cleaned merchant name
        """
        # First, remove store numbers that interfere with location detection
        # Remove 4+ digit numbers (but preserve brand names with numbers like "1st Bank")
        text = re.sub(r'\s+\d{4,}\s+', ' ', text)
        
        # Remove trailing 1-5 digit numbers at the very end (store codes)
        text = re.sub(r'\s+\d{1,5}\s*$', '', text)
        
        # Remove common CITY + STATE patterns before spaCy (spaCy struggles with all-caps location patterns)
        # Pattern: Any capitalized word(s) + 2-letter state code at end
        # But be careful not to match merchant names - only if last 2 words are [CITY][STATE]
        text = re.sub(r'\s+[A-Z][A-Z]+\s+[A-Z]{2}\s*$', '', text, flags=re.IGNORECASE)  # "FARGO ND", "AUSTIN TX"
        text = re.sub(r'\s+(WEST|EAST|NORTH|SOUTH)\s+[A-Z][A-Z]+\s+[A-Z]{2}\s*$', '', text, flags=re.IGNORECASE)  # "WEST FARGO ND"
        text = re.sub(r'\s+ST\s+[A-Z][A-Z]+\s+[A-Z]{2}\s*$', '', text, flags=re.IGNORECASE)  # "ST CLOUD MN"
        
        # Handle merged words - add space before common city/directional patterns
        # This helps spaCy recognize location entities in merged text like "CHIPOTLEFARGO"
        common_locations = [
            'Fargo', 'Minneapolis', 'Chicago', 'Seattle', 'Portland', 'Denver', 
            'Phoenix', 'Dallas', 'Houston', 'Austin', 'Miami', 'Atlanta', 
            'Boston', 'Detroit', 'Philadelphia', 'York', 'Angeles', 'Francisco',
            'Diego', 'West', 'East', 'North', 'South', 'Redmond', 'Vegas',
            'Charlotte', 'Columbus', 'Memphis', 'Nashville', 'Sacramento',
            'Kansas', 'Orlando', 'Cleveland', 'Tampa', 'Pittsburgh'
        ]
        
        for location in common_locations:
            # Case-insensitive replacement that adds space before the location
            # Handle both "ChipotleFargo" and "CHIPOTLEFARGO" patterns
            # Match: any letter (not just lowercase) followed by the location name
            pattern = re.compile(r'([a-zA-Z])(' + location + r')$', re.IGNORECASE)
            text = pattern.sub(r'\1 \2', text)
        
        # Process text with spaCy
        doc = self.nlp(text)
        
        result = text
        text_length = len(text)
        threshold = int(text_length * 0.4)  # Last 60% of text for context
        
        entities_to_remove = []
        
        # Collect entities to remove from the end
        for ent in doc.ents:
            # Remove location entities (GPE = cities/states/countries, LOC = locations)
            if ent.label_ in ['GPE', 'LOC'] and ent.start_char >= threshold:
                entities_to_remove.append(ent)
            
            # Remove trailing numbers (CARDINAL = numeric values)
            # Only if they're at the very end (likely store numbers/codes)
            elif ent.label_ == 'CARDINAL' and ent.end_char >= text_length - 3:
                # Check if it's a small number (1-5 digits = likely store code)
                try:
                    num_val = float(ent.text.replace(',', ''))
                    if 0 < num_val < 100000:  # Store numbers, not amounts
                        entities_to_remove.append(ent)
                except ValueError:
                    pass
        
        # Remove entities from end to beginning to preserve indices
        for ent in reversed(sorted(entities_to_remove, key=lambda e: e.start_char)):
            result = result[:ent.start_char].rstrip(' ,#-') + result[ent.end_char:]
        
        # If no entities found, try pattern-based location removal
        if not entities_to_remove:
            # Look for known location words at the end of the text
            for location in common_locations:
                pattern = r'\s+' + re.escape(location) + r'(?:\s+[A-Z]{2})?$'
                if re.search(pattern, result, re.IGNORECASE):
                    result = re.sub(pattern, '', result, flags=re.IGNORECASE)
                    break
        
        # Also remove directional words and state abbreviations at the end
        result = re.sub(r'\s+(West|East|North|South)$', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\s+[A-Z]{2}$', '', result)
        
        # Remove "Store" prefix if number was already removed
        result = re.sub(r'\s+Store\s*$', '', result, flags=re.IGNORECASE)
        
        return result.strip()
    
    def _llm_enhance(self, place: str) -> str:
        """
        Use local LLM (Ollama) to further clean and standardize the place name.
        
        Args:
            place: Pre-cleaned place name
            
        Returns:
            LLM-enhanced place name
        """
        if not self.ollama_available:
            return place
            
        try:
            prompt = f"""Extract and standardize the merchant/business name. Remove location data, transaction codes, and reference numbers. Output format: business name only.

Input: {place}
Output:"""

            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': self.ollama_model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0,
                        'num_predict': 30  # Limit tokens for short responses
                    }
                },
                timeout=5
            )
            
            if response.status_code == 200:
                cleaned = response.json()['response'].strip()
                # Remove common LLM artifacts
                cleaned = cleaned.replace('Clean:', '').replace('clean:', '').strip()
                cleaned = cleaned.split('\n')[0]  # Take only first line
                
                # Validate the response is good
                if cleaned and len(cleaned) <= 100 and cleaned != place:
                    return cleaned
            
        except Exception as e:
            # Silently fall back to spaCy if LLM fails
            pass
        
        # Fallback: use pattern-based cleaning if LLM fails
        return self._pattern_based_clean(place)
    
    def batch_clean(self, places: list) -> list:
        """
        Clean multiple place names efficiently.
        
        Args:
            places: List of raw place names
            
        Returns:
            List of cleaned place names
        """
        return [self.clean(place) for place in places]
