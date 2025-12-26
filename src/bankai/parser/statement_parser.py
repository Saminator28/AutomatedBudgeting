"""
Statement Parser Module

Parses bank statements using AI-based table detection and OCR.
Based on Microsoft's Table Transformer Model.
"""

from transformers import AutoImageProcessor, TableTransformerForObjectDetection
import torch
from PIL import Image, ImageDraw
import pandas as pd
from typing import List, Dict, Tuple
import sys
from pathlib import Path
import re
import json
from datetime import datetime
import json
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bankai.utils.pdf_converter import PDF2ImageConvertor
from bankai.ocr.text_extractor import TextExtract
from bankai.utils.place_cleaner import PlaceCleaner


class StatementParser:
    """Parse bank statements from PDFs to structured data."""
    
    def __init__(
        self, 
        model_name: str = "microsoft/table-transformer-detection",
        clean_place_names: bool = True,
        use_llm_cleaning: bool = False,
        use_llm_transfer_detection: bool = False,
        llm_host: str = "http://localhost:11434"
    ):
        """
        Initialize the statement parser.
        
        Args:
            model_name: Hugging Face model for table detection
            clean_place_names: Whether to clean up place names
            use_llm_cleaning: Whether to use LLM for enhanced place name cleaning
            use_llm_transfer_detection: Whether to use LLM to detect transfers (DISABLED - use keyword filtering only)
            llm_host: Ollama API host for LLM transfer detection
        """
        print("Initializing Statement Parser...")
        
        # Check if we're online by quickly testing HuggingFace connectivity
        import socket
        import urllib.request
        
        online = False
        try:
            # Quick connectivity check (1 second timeout)
            urllib.request.urlopen('https://huggingface.co', timeout=1)
            online = True
        except:
            print("⚠ Offline mode detected - using cached models")
        
        # Load table detection model
        if online:
            # Online: download latest if available
            self.image_processor = AutoImageProcessor.from_pretrained(model_name)
            self.model = TableTransformerForObjectDetection.from_pretrained(model_name)
        else:
            # Offline: use cached models only
            self.image_processor = AutoImageProcessor.from_pretrained(model_name, local_files_only=True)
            self.model = TableTransformerForObjectDetection.from_pretrained(model_name, local_files_only=True)
        
        # Load income keywords from config
        self.income_keywords = self._load_income_keywords()
        self.payment_app_keywords = self._load_payment_app_keywords()
        
        # Initialize utilities
        self.pdf_converter = PDF2ImageConvertor(dpi=300)
        self.text_extractor = TextExtract()
        
        # Initialize place name cleaner
        self.clean_place_names = clean_place_names
        if self.clean_place_names:
            self.place_cleaner = PlaceCleaner(use_llm=use_llm_cleaning)
        
        # Initialize LLM transfer detection
        self.use_llm_transfer_detection = use_llm_transfer_detection
        self.llm_host = llm_host
        if self.use_llm_transfer_detection:
            # Check if Ollama is available
            try:
                response = requests.get(f"{self.llm_host}/api/tags", timeout=2)
                if response.status_code == 200:
                    print("✓ Ollama detected for transfer detection")
                else:
                    print("⚠ Ollama not available, disabling LLM transfer detection")
                    self.use_llm_transfer_detection = False
            except:
                print("⚠ Ollama not available, disabling LLM transfer detection")
                self.use_llm_transfer_detection = False
        
        print("✓ Models loaded successfully")
    
    def _load_income_keywords(self) -> List[str]:
        """
        Load income keywords from config file.
        Returns list of uppercase keywords to match against transaction descriptions.
        """
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'income_keywords.json'
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    keywords = config.get('income_keywords', [])
                    # Convert to uppercase for case-insensitive matching
                    return [kw.upper() for kw in keywords]
            else:
                print(f"  ⚠ Income keywords config not found at {config_path}, using defaults")
        except Exception as e:
            print(f"  ⚠ Error loading income keywords: {e}, using defaults")
        
        # Fallback default keywords
        return [
            'DEPOSIT', 'INTEREST', 'TRANSFER FROM', 'PAYMENT RECEIVED',
            'REFUND', 'DIVIDEND', 'CREDIT ADJUSTMENT', 'PAYROLL', 'SALARY',
            'DIRECT DEPOSIT', 'DD ', 'WAGE', 'INCOME'
        ]
    
    def _load_payment_app_keywords(self) -> List[str]:
        """
        Load payment app keywords from config file.
        These transactions will be saved separately for manual classification.
        Returns list of uppercase keywords to match against transaction descriptions.
        """
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'payment_apps.json'
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    keywords = config.get('payment_app_keywords', [])
                    # Convert to uppercase for case-insensitive matching
                    return [kw.upper() for kw in keywords]
        except Exception as e:
            print(f"  ⚠ Error loading payment app keywords: {e}")
        
        # Fallback default keywords
        return ['VENMO', 'ZELLE', 'CASH APP', 'CASHAPP', 'APPLE PAY', 'APPLE CASH', 'PAYPAL']
    
    def detect_tables(
        self, 
        image: Image.Image, 
        threshold: float = 0.7
    ) -> List[Dict[str, any]]:
        """
        Detect tables in an image.
        
        Args:
            image: PIL Image object
            threshold: Confidence threshold for detection (0-1)
            
        Returns:
            List of detected table bounding boxes with scores
        """
        # Prepare image for model
        inputs = self.image_processor(images=image, return_tensors="pt")
        
        # Run detection
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # Convert outputs to bounding boxes
        target_sizes = torch.tensor([image.size[::-1]])
        results = self.image_processor.post_process_object_detection(
            outputs, 
            threshold=threshold, 
            target_sizes=target_sizes
        )[0]
        
        tables = []
        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            box = [round(i, 2) for i in box.tolist()]
            tables.append({
                'bbox': box,
                'score': round(score.item(), 3),
                'label': self.model.config.id2label[label.item()]
            })
        
        print(f"  ✓ Detected {len(tables)} table(s)")
        return tables
    
    def parse_transaction_line(self, line: str) -> Dict[str, any]:
        """
        Parse a transaction line to extract transaction date, place, and amount.
        
        Args:
            line: Raw text line from statement
            
        Returns:
            Dictionary with 'Transaction Date', 'Place', 'Credits' or None if not a valid transaction
        """
        line = line.strip()
        if not line:
            return None
        
        # Skip header lines
        if any(header in line.upper() for header in ['TRANS DATE', 'POST DATE', 'REFERENCE', 'TRANSACTION DESCRIPTION', 'CREDITS', 'DEBITS']):
            return None
        
        # Split line into parts (OCR often separates by spaces)
        parts = line.split()
        
        if len(parts) < 3:
            return None
        
        # Check for reference number (long numeric string > 15 digits)
        # Some statements have reference numbers, some don't - make it optional
        # Reference might be split across multiple parts or concatenated
        has_reference = False
        reference_idx = None
        for idx, part in enumerate(parts):
            # Check single part
            if len(part) > 15 and part.isdigit():
                has_reference = True
                reference_idx = idx
                break
            # Check if part contains embedded reference (e.g., "24692165296109866146943")
            if len(part) >= 20:
                # Look for sequence of 16+ consecutive digits
                digit_seq = ''
                for char in part:
                    if char.isdigit():
                        digit_seq += char
                    else:
                        if len(digit_seq) > 15:
                            has_reference = True
                            reference_idx = idx
                            break
                        digit_seq = ''
                if len(digit_seq) > 15:
                    has_reference = True
                    reference_idx = idx
                    break
        
        # Also check if adjacent parts form a long reference
        if not has_reference:
            for i in range(len(parts) - 1):
                combined = parts[i] + parts[i+1]
                if len(combined) > 15 and combined.replace(' ', '').isdigit():
                    has_reference = True
                    reference_idx = i
                    break
        
        # Don't require reference number - some banks don't include them
        # Just proceed with parsing if we have date + amount patterns
        
        # Look for transaction date pattern (MM-DD or MM/DD at start)
        trans_date = None
        date_pattern = r'^\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?$'
        
        # Try to find transaction date (usually first element)
        if re.match(date_pattern, parts[0]):
            trans_date = parts[0]
            # Normalize date format to MM/DD/YYYY
            if trans_date:
                date_parts = re.split(r'[-/]', trans_date)
                if len(date_parts) == 3:
                    month, day, year = date_parts
                    # Convert 2-digit year to 4-digit year
                    if len(year) == 2:
                        year = '20' + year
                    trans_date = f"{month.zfill(2)}/{day.zfill(2)}/{year}"
                elif len(date_parts) == 2:
                    # No year provided, assume current year
                    month, day = date_parts
                    from datetime import datetime
                    year = str(datetime.now().year)
                    trans_date = f"{month.zfill(2)}/{day.zfill(2)}/{year}"
        
        # Look for all amounts in the line (there may be multiple for debits, credits, balance)
        amounts = []
        amount_indices = []
        for i, part in enumerate(parts):
            # Check if it starts with $ or looks like a currency amount
            clean_part = part.replace('$', '').replace(',', '')
            if part.startswith('$') or (clean_part.replace('.', '').replace('-', '').isdigit() and '.' in clean_part):
                try:
                    amount_val = float(clean_part)
                    amounts.append(amount_val)
                    amount_indices.append(i)
                except ValueError:
                    continue
        
        # If we have date and at least one amount, extract the transaction
        if trans_date and amounts:
            # Find where description starts (after date)
            start_idx = 1
            if start_idx < len(parts) and re.match(date_pattern, parts[start_idx]):
                start_idx = 2  # Skip post date if it exists
            
            # Skip reference number if it exists (long numeric string)
            if has_reference and reference_idx is not None:
                # Skip the reference number part
                if reference_idx >= start_idx and reference_idx < len(parts):
                    # If reference is where we'd start description, skip it
                    if reference_idx == start_idx or reference_idx == start_idx + 1:
                        start_idx = reference_idx + 1
            
            # Find first amount index to know where description ends
            first_amount_idx = amount_indices[0] if amount_indices else len(parts)
            
            # Extract place/description (everything between start and first amount)
            if start_idx < first_amount_idx:
                place_parts = parts[start_idx:first_amount_idx]
                place = ' '.join(place_parts)
                
                # Clean up place name
                place = re.sub(r'\s+', ' ', place).strip()
                
                if place:
                    result = {
                        'Transaction Date': trans_date,
                        'Place': place,
                    }
                    
                    # Handle multiple amount columns
                    if len(amounts) == 3:
                        # Format: debits, credits, balance
                        result['Debits'] = amounts[0] if amounts[0] > 0 else None
                        result['Credits'] = amounts[1] if amounts[1] > 0 else None
                        result['Balance'] = amounts[2]
                    elif len(amounts) == 2:
                        # Two amounts: either (debit, balance) or (credit, balance)
                        # The second one is always the balance (larger running total)
                        # The first is the transaction amount
                        transaction_amt = amounts[0]
                        balance = amounts[1]
                        
                        # Determine if it's a debit or credit based on transaction description
                        # Use keywords from config file (config/income_keywords.json)
                        place_upper = place.upper()
                        is_credit = any(keyword in place_upper for keyword in self.income_keywords)
                        
                        if is_credit:
                            result['Credits'] = transaction_amt
                        else:
                            result['Debits'] = transaction_amt
                        result['Balance'] = balance
                    elif len(amounts) == 1:
                        # Single amount - assume it's credits (legacy format for credit cards)
                        result['Credits'] = amounts[0]
                    
                    return result
        
        return None
    
    def _is_transfer_llm(self, description: str, amount: float = None, date: str = None) -> tuple:
        """
        Use LLM to determine if a transaction is likely an internal transfer.
        
        Args:
            description: Transaction description/place
            amount: Transaction amount (optional)
            date: Transaction date (optional)
            
        Returns:
            Tuple of (is_transfer: bool, reason: str)
        """
        if not self.use_llm_transfer_detection:
            return False, ""
        
        # Build prompt for LLM
        prompt = f"""Analyze this bank transaction and determine if it is an internal transfer between accounts (NOT a purchase or expense).

Transaction Description: {description}"""
        
        if amount:
            prompt += f"\nAmount: ${amount:.2f}"
        if date:
            prompt += f"\nDate: {date}"
        
        prompt += """\n\nInternal transfers include:
- Transfers between checking/savings accounts
- Credit card payments from bank account
- Moving money between your own accounts
- Online banking transfers
- Mobile banking transfers
- Transfers to/from investment accounts

NOT transfers (these are expenses):
- Purchases from merchants
- Bill payments to companies
- ATM withdrawals
- Checks written to other people/businesses
- Debit card purchases

Respond with ONLY:
TRANSFER: [YES or NO]
REASON: [brief explanation]

Example responses:
TRANSFER: YES
REASON: Online transfer to savings account

TRANSFER: NO
REASON: Purchase from retail merchant"""
        
        try:
            response = requests.post(
                f"{self.llm_host}/api/generate",
                json={
                    "model": "dolphin-llama3:latest",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 100
                    }
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json().get('response', '').strip()
                
                # Parse response
                is_transfer = 'TRANSFER: YES' in result.upper()
                
                # Extract reason
                reason = ""
                for line in result.split('\n'):
                    if line.strip().startswith('REASON:'):
                        reason = line.split('REASON:', 1)[1].strip()
                        break
                
                return is_transfer, reason
            
        except Exception as e:
            # Silently fail and return False if LLM fails
            pass
        
        return False, ""
    
    def _convert_columnar_to_rows(self, lines: List[str]) -> List[str]:
        """
        Detect if table data is in column format (vertical) and convert to row format.
        
        Some PDFs (like Magnifi Financial) extract tables where all dates are together,
        then all descriptions, then all amounts. This method detects that pattern and
        reorganizes the data into transaction rows.
        
        Args:
            lines: List of text lines from table extraction
            
        Returns:
            List of lines reorganized into row format, or original lines if not columnar
        """
        if not lines or len(lines) < 10:
            return lines
        
        # Date pattern for detection - more flexible to handle OCR errors
        # Matches: 10/15/25, 0/15/25, 1/5/25, etc.
        date_pattern = r'^\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?$'
        
        # Find sequences of dates, amounts, and other data
        # KEY INSIGHT: Only collect dates from sections that have reference numbers (actual transactions)
        columns = {
            'dates': [],  # Dates associated with transactions
            'references': [],
            'descriptions': [],
            'card_numbers': [],
            'amounts': []
        }
        
        # First pass: check if this table section has reference numbers at all
        has_reference_numbers = False
        for line in lines:
            parts = line.split()
            for part in parts:
                cleaned = part.replace(' ', '')
                if len(cleaned) > 15 and cleaned.isdigit():
                    has_reference_numbers = True
                    break
            if has_reference_numbers:
                break
        
        # If no reference numbers found, this might not be a transaction table
        # But still process it in case it's a valid table without references
        
        current_section = None
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect section headers
            line_upper = line.upper()
            if 'DATE' in line_upper and len(line) < 15:
                current_section = 'dates'
                i += 1
                continue
            elif 'REFERENCE' in line_upper and len(line) < 20:
                current_section = 'references'
                i += 1
                continue
            elif 'DESCRIPTION' in line_upper or 'TRANSACTION' in line_upper:
                current_section = 'descriptions'
                i += 1
                continue
            elif 'CARD' in line_upper and len(line) < 15:
                current_section = 'card_numbers'
                i += 1
                continue
            elif 'AMOUNT' in line_upper and len(line) < 15:
                current_section = 'amounts'
                i += 1
                continue
            
            # Skip other header-like lines
            if any(header in line_upper for header in ['POSTING', 'TRANS', 'SUMMARY', 'TOTAL', 'INTEREST', 'FEE']) and len(line) < 20:
                i += 1
                continue
            
            # Skip payment-related lines that contain dates we don't want
            if any(keyword in line_upper for keyword in ['PAYMENT ACH', 'ACH PAYMENT', 'ONLINE TRANSFER', 'TYPE:', 'CO:', 'ENTRY CLASS', 'ID:']):
                i += 1
                continue
            
            # Check for malformed date lines like "22/25 = 10/21/25" (OCR error)
            # Extract the date after the equals sign
            if '=' in line and len(line) < 30:
                parts = line.split('=')
                if len(parts) == 2:
                    date_candidate = parts[1].strip()
                    if re.match(date_pattern, date_candidate):
                        columns['dates'].append(date_candidate)
                        i += 1
                        continue
            
            # Collect data based on current section and line content
            if re.match(date_pattern, line):
                # This is a date - collect it
                columns['dates'].append(line)
                i += 1
                continue
            
            # Check for reference numbers (long numeric strings, possibly with spaces)
            # In columnar format, these appear on separate lines
            cleaned_ref = line.replace(' ', '').replace('\t', '')
            if len(cleaned_ref) > 15 and cleaned_ref.isdigit():
                columns['references'].append(line)
                i += 1
                continue
            
            # Check for amounts (numbers with decimals or negative signs)
            clean_line = line.replace('$', '').replace(',', '').replace('-', '').strip()
            # Don't confuse 4-digit card numbers with amounts
            if len(line) == 4 and line.isdigit():
                # This is a card number, not an amount
                columns['card_numbers'].append(line)
                i += 1
                continue
            # Check for amounts: must have decimal point and be valid float
            # But skip amounts from summary/fee lines
            skip_amount_keywords = ['SUMMARY', 'TOTAL', 'INTEREST', 'FEE', 'YEAR TO DATE']
            line_contains_summary = any(kw in line_upper for kw in skip_amount_keywords)
            if '.' in line and len(line) > 3 and not line_contains_summary:
                try:
                    # Try to parse as amount
                    amount_val = float(line.replace('$', '').replace(',', ''))
                    columns['amounts'].append(line)
                    i += 1
                    continue
                except ValueError:
                    pass
            
            # Everything else is likely a description
            if line and len(line) > 2:
                # Skip common non-transaction text and sub-details of payments
                skip_keywords = ['PAGE', 'STATEMENT', 'ACCOUNT', 'TYPE:', 'CO:', 'ENTRY CLASS', 'ID:']
                if not any(skip in line_upper for skip in skip_keywords):
                    # Check if this line contains a reference number (long digit string)
                    has_reference = False
                    for part in line.split():
                        if len(part) > 15 and part.isdigit():
                            columns['references'].append(part)
                            has_reference = True
                            break
                    
                    # Filter out lines that are clearly not descriptions
                    if current_section == 'descriptions' or (len(line) > 5 and any(c.isalpha() for c in line)):
                        # Avoid collecting section headers as descriptions
                        if not (len(line) < 20 and line_upper in ['POSTING', 'TRANS', 'DATE', 'REFERENCE', 'DESCRIPTION', 'CARD', 'AMOUNT']):
                            columns['descriptions'].append(line)
            
            i += 1
        
        # Check if we detected columnar format
        # First, check if lines are already in row format (date + ref + description + amount on same line)
        # Look for lines that have: date pattern + long reference number + amount
        row_format_count = 0
        for line in lines[:20]:  # Check first 20 lines
            parts = line.split()
            if len(parts) < 3:
                continue
            # Check if this line has date, reference (15+ digits), and amount
            has_date = any(re.match(date_pattern, part) for part in parts[:3])  # Date in first 3 elements
            # Check for reference - look for any part with 15+ consecutive digits (may be in middle of line)
            has_long_ref = any(len(part) > 15 and part.replace(' ', '').isdigit() for part in parts)
            # Check for amount - must have decimal point
            has_amount = False
            for part in parts:
                clean = part.replace('$', '').replace(',', '').replace('-', '')
                if '.' in clean and clean.replace('.', '').isdigit():
                    try:
                        float(clean)
                        has_amount = True
                        break
                    except:
                        pass
            
            if has_date and has_long_ref and has_amount:
                row_format_count += 1
        
        # If we found multiple complete rows, data is already in row format - skip columnar conversion
        if row_format_count >= 2:
            print(f"  ✓ Data already in row format ({row_format_count} complete rows found), skipping columnar conversion")
            return lines
        
        # Need at least dates and amounts in separate columns
        num_dates = len(columns['dates'])
        num_amounts = len(columns['amounts'])
        num_descriptions = len(columns['descriptions'])
        num_references = len(columns['references'])
        
        # Columnar format validation based on reference count
        
        # KEY INSIGHT: Use reference count as ground truth for transaction count
        # Dates should match reference count (or be 2x for posting+trans dates)
        # Amounts should match reference count
        # Only proceed if we have references AND matching dates/amounts
        if num_references >= 2 and num_amounts >= 2:
            # Check if dates match references (1:1 or 2:1 ratio)
            if num_dates >= num_references and num_dates <= num_references * 2:
                # Good ratio - proceed with columnar conversion
                print(f"  💡 Detected columnar table format - converting to rows...")
                print(f"     Found {num_dates} date(s), {num_references} reference(s), {num_amounts} amount(s), {num_descriptions} description(s)")
                
                # Use reference count as the authoritative transaction count
                num_transactions = num_references
                
                # Determine if we have 2 dates per transaction or 1
                dates_per_transaction = num_dates // num_references if num_references > 0 else 1
                
                # Sanity check
                if dates_per_transaction == 0:
                    print(f"  ⚠ Date/reference ratio invalid ({num_dates}:{num_references}), skipping columnar conversion")
                    return lines
                
                # Reconstruct transaction rows
                reconstructed_lines = []
                
                for idx in range(num_transactions):
                    row_parts = []
                    
                    # Add date(s) for this transaction
                    if dates_per_transaction == 2:
                        # Two dates per transaction (posting + trans date)
                        # Use the SECOND date (trans date) as the primary date
                        if idx * 2 + 1 < num_dates:
                            row_parts.append(columns['dates'][idx * 2 + 1])  # Trans date (second date)
                        elif idx * 2 < num_dates:
                            row_parts.append(columns['dates'][idx * 2])  # Fallback to posting date if trans date missing
                    else:
                        # One date per transaction
                        if idx < num_dates:
                            row_parts.append(columns['dates'][idx])
                    
                    # Add reference number
                    if idx < len(columns['references']):
                        row_parts.append(columns['references'][idx])
                    
                    # Add description
                    if idx < num_descriptions:
                        row_parts.append(columns['descriptions'][idx])
                    
                    # Add card number
                    if idx < len(columns['card_numbers']):
                        row_parts.append(columns['card_numbers'][idx])
                    
                    # Add amount
                    if idx < num_amounts:
                        row_parts.append(columns['amounts'][idx])
                    
                    # Combine into a single line
                    reconstructed_line = ' '.join(row_parts)
                    reconstructed_lines.append(reconstructed_line)
                    print(f"     Row {idx+1}: {reconstructed_line[:80]}...")
                
                return reconstructed_lines
        
        # Not columnar format, return original lines
        return lines
    
    def extract_table_structure(
        self,
        image: Image.Image,
        table_bbox: List[float]
    ) -> tuple:
        """
        Extract table structure and content from a detected table region.
        
        Args:
            image: PIL Image object
            table_bbox: Bounding box of the table [x_min, y_min, x_max, y_max]
            
        Returns:
            Tuple of (transactions_list, skipped_transfers_list)
        """
        # Expand bounding box by 5% on each side to capture edge content
        # that might be cut off (like amount decimals)
        x_min, y_min, x_max, y_max = table_bbox
        width = x_max - x_min
        height = y_max - y_min
        padding_x = width * 0.05
        padding_y = height * 0.02
        
        # Apply padding (ensure we don't go outside image bounds)
        img_width, img_height = image.size
        x_min = max(0, x_min - padding_x)
        y_min = max(0, y_min - padding_y)
        x_max = min(img_width, x_max + padding_x)
        y_max = min(img_height, y_max + padding_y)
        
        expanded_bbox = [x_min, y_min, x_max, y_max]
        
        # Crop to table region
        table_image = image.crop(expanded_bbox)
        
        # Extract text using OCR
        text = self.text_extractor.extract_text(table_image)
        
        # Parse text into transaction lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Debug: show first few lines from OCR
        if len(lines) > 0 and len(lines) <= 10:
            # Only show for small tables
            print(f"  📄 OCR extracted {len(lines)} lines")
        elif len(lines) > 10:
            print(f"  📄 OCR extracted {len(lines)} lines")
        
        # Check if this is a summary/fees table - skip if so
        # Only skip if it's ONLY summary data (no actual transactions with references)
        summary_indicators = ['FEE SUMMARY', 'TOTAL FEES FOR THIS PERIOD', 'TOTAL INTEREST FOR THIS PERIOD']
        is_summary_table = any(indicator in text.upper() for indicator in summary_indicators)
        
        # But also check if there are valid transaction lines (with reference numbers)
        has_transactions = False
        if is_summary_table:
            for line in lines:
                parts = line.split()
                # Look for long reference numbers indicating real transactions
                for part in parts:
                    if len(part) > 15 and part.isdigit():
                        has_transactions = True
                        break
                if has_transactions:
                    break
        
        # Only skip if it's a summary table WITHOUT transactions
        if is_summary_table and not has_transactions:
            print(f"  ⚠ Detected summary table, skipping...")
            return [], []
        
        # Try to detect if table is in column format and convert to rows
        lines = self._convert_columnar_to_rows(lines)
        
        # Parse each line for date, description, amount
        transactions = []
        skipped_transfers = []
        
        for line in lines:
            parsed = self.parse_transaction_line(line)
            if parsed:
                # Skip internal transfers
                place = parsed.get('Place', '').upper()
                if any(keyword in place for keyword in [
                    'ONLINE PHONE', 'ONLINE-PHONE', 'PHONE TRANSFER',
                    'ONLINE TRANSFER', 'ONLINE-TRANSFER', 'TRANSFER FROM',
                    'MOBILE TRANSFER', 'ONLINE PAYMENT', 'ONLINE PMT',
                    'MAGNIFI FINANCIAL EXTERNAL', 'PAYMENT ACH', 'ACH PAYMENT'
                ]):
                    skipped_transfers.append(parsed)
                    continue
                
                # Skip transactions with $0.00 or no amount (extraction failures)
                amount = parsed.get('Credits') or parsed.get('Debits') or parsed.get('Amount', 0)
                if amount == 0 or amount is None:
                    continue
                
                # Fix common OCR date errors (0/15/25 -> 10/15/25)
                if 'Transaction Date' in parsed:
                    date = parsed['Transaction Date']
                    if date.startswith('0/'):
                        parsed['Transaction Date'] = '10' + date[1:]
                
                # Clean place name if enabled
                if self.clean_place_names and 'Place' in parsed:
                    parsed['Place'] = self.place_cleaner.clean(parsed['Place'])
                
                transactions.append(parsed)
        
        # Print skipped transfers summary
        if skipped_transfers:
            print(f"  ⚠ Skipped {len(skipped_transfers)} internal transfer(s):")
            for skip in skipped_transfers[:6]:
                date = skip.get('Transaction Date', 'N/A')
                place = skip.get('Place', 'N/A')[:50]
                amount = skip.get('Credits') or skip.get('Debits') or skip.get('Amount', 'N/A')
                print(f"    - {date}: {place} (${amount})")
        
        return transactions, skipped_transfers
    
    def _save_skipped_transfers(self, skipped_transfers_list, output_path):
        if not skipped_transfers_list:
            return
        
        df_skipped = pd.DataFrame(skipped_transfers_list)
        
        # Ensure we have key columns
        if 'Transaction Date' not in df_skipped.columns:
            df_skipped['Transaction Date'] = None
        if 'Place' not in df_skipped.columns:
            df_skipped['Place'] = None
        if 'Amount' not in df_skipped.columns:
            df_skipped['Amount'] = None
        
        # Deduplicate skipped transfers (same transaction can appear in multiple tables)
        # Determine which amount column to use for deduplication
        amount_col = None
        for col in ['Credits', 'Debits', 'Amount']:
            if col in df_skipped.columns and df_skipped[col].notna().any():
                amount_col = col
                break
        
        if amount_col:
            initial_count = len(df_skipped)
            df_skipped = df_skipped.drop_duplicates(subset=['Transaction Date', 'Place', amount_col], keep='first')
            if len(df_skipped) < initial_count:
                print(f"  ℹ Removed {initial_count - len(df_skipped)} duplicate skipped transfer(s)")
        
        # Reorder columns
        cols = ['Transaction Date', 'Place', 'Amount']
        for col in df_skipped.columns:
            if col not in cols:
                cols.append(col)
        
        df_skipped = df_skipped[cols]
        df_skipped.to_csv(output_path, index=False)
        print(f"  💾 Saved {len(df_skipped)} skipped transfer(s) to: {output_path}")
    
    def _parse_table_text_to_dataframe(self, text):
        """
        Parse extracted table text into a pandas DataFrame.
        Handles different bank statement formats.
        Returns DataFrame with transactions.
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Parse each line for date, description, amount
        transactions = []
        for line in lines:
            parsed = self.parse_transaction_line(line)
            if parsed:
                # Don't filter here, just collect all transactions
                # Clean place name if enabled
                if self.clean_place_names and 'Place' in parsed:
                    parsed['Place'] = self.place_cleaner.clean(parsed['Place'])
                
                transactions.append(parsed)
        
        # Create DataFrame - column structure depends on what we parsed
        if transactions:
            df = pd.DataFrame(transactions)
            
            # Ensure base columns exist
            base_cols = ['Transaction Date', 'Place']
            for col in base_cols:
                if col not in df.columns:
                    df[col] = None
            
            # Reorder columns: Date, Place, then Debits/Credits/Balance if they exist
            col_order = ['Transaction Date', 'Place']
            if 'Debits' in df.columns:
                col_order.append('Debits')
            if 'Credits' in df.columns:
                col_order.append('Credits')
            if 'Balance' in df.columns:
                col_order.append('Balance')
            
            # Keep columns in order, add any extras at the end
            other_cols = [col for col in df.columns if col not in col_order]
            df = df[col_order + other_cols]
        else:
            df = pd.DataFrame(columns=['Transaction Date', 'Place', 'Credits'])
        
        return df
    
    def visualize_tables(
        self, 
        image: Image.Image, 
        tables: List[Dict[str, any]]
    ) -> Image.Image:
        """
        Draw bounding boxes around detected tables.
        
        Args:
            image: PIL Image object
            tables: List of detected tables
            
        Returns:
            Image with drawn bounding boxes
        """
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        
        for table in tables:
            bbox = table['bbox']
            draw.rectangle(bbox, outline="red", width=3)
            
            # Draw label and score
            label = f"{table['label']}: {table['score']:.2f}"
            draw.text((bbox[0], bbox[1] - 10), label, fill="red")
        
        return img_copy
    
    def detect_statement_source(self, image: Image.Image) -> str:
        """
        Detect the bank/card issuer from the statement header.
        
        Args:
            image: PIL Image of the first page
            
        Returns:
            Bank/card name or 'Unknown (detected text from header)'
        """
        # Extract text from top portion of the page (header area)
        width, height = image.size
        header_region = image.crop((0, 0, width, int(height * 0.2)))  # Top 20%
        
        header_text = self.text_extractor.extract_text(header_region).upper()
        
        # Load bank patterns from config file
        bank_patterns = self._load_bank_patterns()
        
        # Check for bank names in header
        for pattern, name in bank_patterns.items():
            if pattern in header_text:
                return name
        
        # If not found, try to extract the likely bank name from header
        # Look for capitalized text in first few lines
        lines = [line.strip() for line in header_text.split('\n') if line.strip()]
        potential_names = []
        for line in lines[:5]:  # Check first 5 non-empty lines
            # Skip common non-bank text
            if any(skip in line.lower() for skip in ['po box', 'statement', 'account', 'page', 'address', 'phone']):
                continue
            # Look for lines with letters (likely bank names)
            if len(line) > 2 and any(c.isalpha() for c in line):
                # Remove numbers and special chars, take first substantial word
                words = line.split()
                for word in words:
                    if len(word) >= 4 and word.isalpha():
                        potential_names.append(word.title())
                        break
        
        if potential_names:
            detected_name = ' '.join(potential_names[:2])  # Take first 2 words
            return f'Unknown ({detected_name})'
        
        return 'Unknown'
    
    def _load_bank_patterns(self) -> dict:
        """Load bank patterns from the config file."""
        # Go up three levels: parser -> bankai -> src -> root, then into config
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'bank_patterns.json'
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                return data.get('patterns', {})
        except FileNotFoundError:
            print(f"⚠ Warning: bank_patterns.json not found at {config_path}")
            # Return default patterns as fallback
            return {
                'CHASE': 'Chase',
                'BANK OF AMERICA': 'Bank of America',
                'DISCOVER': 'Discover',
            }
        except json.JSONDecodeError as e:
            print(f"⚠ Warning: Error parsing bank_patterns.json: {e}")
            return {}
    
    def bankstatement2csv(
        self,
        pdf: str,
        output_file: str = "output.xlsx",
        visualize: bool = False,
        return_dataframe: bool = False,
        detect_source: bool = False
    ):
        """
        Convert a bank statement PDF to structured Excel/CSV file.
        
        Args:
            pdf: Path to PDF file
            output_file: Output filename (default: output.xlsx)
            visualize: Whether to save visualization images
            return_dataframe: If True, return DataFrame instead of saving
            detect_source: If True, detect bank/card name from statement
        
        Returns:
            Tuple of (DataFrame, source_name) if return_dataframe=True, None otherwise
        """
        print(f"\n{'='*60}")
        print(f"Processing Bank Statement: {pdf}")
        print(f"{'='*60}\n")
        
        # Step 1: Convert PDF to images
        print("Step 1: Converting PDF to images...")
        images = self.pdf_converter.convert(pdf)
        
        # Detect statement source if requested
        statement_source = 'Unknown'
        if detect_source and images:
            print("Step 1.5: Detecting statement source...")
            statement_source = self.detect_statement_source(images[0])
            if statement_source.startswith('Unknown'):
                print(f"  ⚠ Detected: {statement_source}")
                print(f"  💡 To fix: Add your bank to config/bank_patterns.json")
            else:
                print(f"  ✓ Detected: {statement_source}")
        
        # Process each page
        all_transactions = []
        all_skipped_transfers = []
        
        for page_num, image in enumerate(images, 1):
            print(f"\nStep 2: Processing page {page_num}...")
            
            # Detect tables with a permissive threshold (0.2 for sparse columnar formats)
            tables = self.detect_tables(image, threshold=0.2)
            
            if not tables:
                print(f"  ⚠ No tables detected on page {page_num}")
                
                # Try extracting from full page as fallback
                # (columnar formats may not register as tables)
                print(f"  💡 Trying full-page text extraction...")
                full_text = self.text_extractor.extract_text(image)
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                
                # Debug: show first few lines
                if len(lines) > 0:
                    print(f"  📄 OCR extracted {len(lines)} lines, first 10:")
                    for idx, line in enumerate(lines[:10]):
                        print(f"      {idx+1}. {line[:80]}")
                
                # Try columnar conversion
                converted_lines = self._convert_columnar_to_rows(lines)
                if converted_lines != lines:  # If conversion happened
                    # Parse the converted rows
                    transactions = []
                    skipped = []
                    for line in converted_lines:
                        parsed = self.parse_transaction_line(line)
                        if parsed:
                            # Skip internal transfers
                            place = parsed.get('Place', '').upper()
                            if any(keyword in place for keyword in [
                                'ONLINE PHONE', 'ONLINE-PHONE', 'PHONE TRANSFER',
                                'ONLINE TRANSFER', 'ONLINE-TRANSFER', 'TRANSFER FROM',
                                'MOBILE TRANSFER', 'ONLINE PAYMENT', 'ONLINE PMT',
                                'MAGNIFI FINANCIAL EXTERNAL', 'PAYMENT ACH', 'ACH PAYMENT'
                            ]):
                                skipped.append(parsed)
                                continue
                            
                            # Skip transactions with $0.00 or no amount (extraction failures)
                            amount = parsed.get('Credits') or parsed.get('Debits') or parsed.get('Amount', 0)
                            if amount == 0 or amount is None:
                                continue
                            
                            # Fix common OCR date errors (0/15/25 -> 10/15/25)
                            if 'Transaction Date' in parsed:
                                date = parsed['Transaction Date']
                                if date.startswith('0/'):
                                    parsed['Transaction Date'] = '10' + date[1:]
                            
                            # Clean place name if enabled
                            if self.clean_place_names and 'Place' in parsed:
                                parsed['Place'] = self.place_cleaner.clean(parsed['Place'])
                            
                            transactions.append(parsed)
                    
                    all_skipped_transfers.extend(skipped)
                    if transactions:
                        all_transactions.append(pd.DataFrame(transactions))
                        print(f"    ✓ Extracted {len(transactions)} row(s) from full page")
                
                continue
            
            # Visualize if requested
            if visualize:
                vis_image = self.visualize_tables(image, tables)
                vis_path = f"visualization_page_{page_num}.jpg"
                vis_image.save(vis_path)
                print(f"  ✓ Saved visualization to {vis_path}")
            
            # Extract data from each table
            for i, table in enumerate(tables):
                print(f"  Step 3: Extracting table {i+1}...")
                transactions, skipped = self.extract_table_structure(image, table['bbox'])
                
                # Always collect skipped transfers
                all_skipped_transfers.extend(skipped)
                
                if transactions:
                    all_transactions.append(pd.DataFrame(transactions))
                    print(f"    ✓ Extracted {len(transactions)} row(s)")
        
        # Combine all transactions
        if all_transactions:
            final_df = pd.concat(all_transactions, ignore_index=True)
            
            # Deduplicate transactions (from table overlap)
            # Keep first occurrence based on Date + Place + Amount combination
            amount_col = 'Credits' if 'Credits' in final_df.columns else ('Debits' if 'Debits' in final_df.columns else 'Amount')
            if amount_col in final_df.columns:
                initial_count = len(final_df)
                final_df = final_df.drop_duplicates(subset=['Transaction Date', 'Place', amount_col], keep='first')
                if len(final_df) < initial_count:
                    print(f"  ℹ Removed {initial_count - len(final_df)} duplicate transaction(s)")
            
            # Reorder columns: Transaction Date and Place first, then any amount columns
            base_cols = ['Transaction Date', 'Place']
            amount_cols = ['Debits', 'Credits', 'Balance']
            
            # Add amount columns in order if they exist
            ordered_cols = base_cols.copy()
            for col in amount_cols:
                if col in final_df.columns:
                    ordered_cols.append(col)
            
            # Add any remaining columns
            other_cols = [col for col in final_df.columns if col not in ordered_cols]
            final_df = final_df[ordered_cols + other_cols]
            
            # Save skipped transfers to a separate file (before potential early return)
            if all_skipped_transfers and output_file:
                import os
                # Create unique rejected file name based on PDF source
                pdf_basename = os.path.basename(pdf).replace('.pdf', '')
                output_dir = os.path.dirname(output_file)
                rejected_file = os.path.join(output_dir, f"{pdf_basename}_rejected.csv")
                self._save_skipped_transfers(all_skipped_transfers, rejected_file)
            
            # Return DataFrame if requested
            if return_dataframe:
                return final_df, statement_source
            
            # Save to file
            print(f"\nStep 4: Saving results...")
            if output_file.endswith('.csv'):
                final_df.to_csv(output_file, index=False)
            else:
                final_df.to_excel(output_file, index=False)
            
            print(f"✓ Saved {len(final_df)} transaction(s) to {output_file}")
            print(f"\n{'='*60}")
            
        else:
            print("\n⚠ No transactions extracted from the PDF")
            if statement_source.startswith('Unknown'):
                print("\n💡 Possible reasons:")
                print("   1. Bank/card not recognized - Add to config/bank_patterns.json")
                print("      Detected bank name: " + statement_source.replace('Unknown ', '').strip('()'))
                print("   2. Unusual PDF format - Consider manual entry via manual_transactions.csv")
                print("   3. Scanned/image PDF - OCR may need adjustment")
            else:
                print(f"\n💡 The PDF format from {statement_source} may not be supported")
                print("   This can happen when:")
                print("   - Table data is in an unusual layout (e.g., vertical columns instead of rows)")
                print("   - Multi-line transactions that don't fit the expected pattern")
                print("   - Heavily formatted or styled tables that confuse OCR")
                print("\n   Workaround: Create manual_transactions.csv with your transactions")
            print(f"{'='*60}")
            
            if return_dataframe:
                return pd.DataFrame(columns=['Transaction Date', 'Place', 'Credits']), statement_source
