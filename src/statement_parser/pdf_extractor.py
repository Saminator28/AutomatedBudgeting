"""
PDF text extraction using pdfplumber (primary) with PyMuPDF fallback.
"""

import pdfplumber
from pathlib import Path
from typing import Tuple, List, Dict


def _extract_with_pymupdf(pdf_path: Path, debug: bool = False) -> str:
    """
    Extract text using PyMuPDF word-level bounding boxes.

    Words are grouped into rows by y-coordinate proximity (tolerance 3.5 pt) then
    joined left-to-right with spaces — this preserves inter-word spacing that
    pdfplumber sometimes loses when characters are encoded without explicit spaces.

    Returns empty string if PyMuPDF is not installed or extraction yields < 100 chars.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ''

    try:
        doc = fitz.open(str(pdf_path))
        page_texts = []
        for page in doc:
            words = page.get_text('words')  # (x0, y0, x1, y1, text, block, line, word)
            if not words:
                continue

            # Group words into rows by y-coordinate
            rows: dict[float, list] = {}
            for x0, y0, x1, y1, text, *_ in words:
                matched_y = None
                for ry in rows:
                    if abs(y0 - ry) <= 3.5:
                        matched_y = ry
                        break
                key = matched_y if matched_y is not None else y0
                rows.setdefault(key, []).append((x0, text))

            lines = []
            for ry in sorted(rows):
                row_words = sorted(rows[ry], key=lambda t: t[0])
                lines.append(' '.join(t for _, t in row_words))
            page_texts.append('\n'.join(lines))

        doc.close()
        text = '\n\n'.join(page_texts)
        return text if len(text.strip()) >= 100 else ''
    except Exception as e:
        if debug:
            print(f'  PyMuPDF extraction failed: {e}')
        return ''


def extract_text_from_pdf(pdf_path: Path, debug: bool = False) -> str:
    """
    Extract text from PDF.

    Strategy:
      1. pdfplumber  — primary; handles multi-column layout correctly for most statements
      2. PyMuPDF     — fallback if pdfplumber returns < 100 chars (e.g. image-based or
                       font-encoding issues); preserves word spacing via bounding boxes
    
    Args:
        pdf_path: Path to PDF file
        debug: Print debug information
        
    Returns:
        Extracted text or empty string if extraction fails
    """
    if debug:
        print(f"  -> Extracting with pdfplumber...")
    
    text = ''
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n\n'
    except Exception as e:
        if debug:
            print(f"  Warning: pdfplumber failed: {e}")
        text = ''

    if len(text.strip()) >= 100:
        if debug:
            output_path = pdf_path.with_suffix('.txt')
            try:
                output_path.write_text(text, encoding='utf-8')
                print(f"  -> Saved extracted text to {output_path.name}")
            except Exception as e:
                print(f"  Warning: Could not save text file: {e}")
        return text

    # pdfplumber produced insufficient text — try PyMuPDF
    if debug:
        print(f"  Warning: pdfplumber extracted insufficient text, trying PyMuPDF...")
    text = _extract_with_pymupdf(pdf_path, debug=debug)
    if text:
        if debug:
            print(f"  -> PyMuPDF fallback succeeded ({len(text)} chars)")
        return text

    if debug:
        print(f"  Warning: both extractors returned insufficient text")
    return ''


def validate_transactions(transactions: List[Dict], method: str) -> Dict:
    """
    Validate quality of extracted transactions.
    
    Args:
        transactions: List of transaction dictionaries
        method: Extraction method used ('pdfplumber')
        
    Returns:
        {
            'valid': bool,
            'score': float (0-100),
            'transaction_count': int,
            'issues': List[str],
            'method': str
        }
    """
    import re
    
    if not transactions:
        return {
            'valid': False,
            'score': 0,
            'transaction_count': 0,
            'issues': ['No transactions found'],
            'method': method
        }
    
    score = 100
    issues = []
    
    # Check 1: Valid dates
    valid_dates = sum(1 for t in transactions 
                     if 'Transaction Date' in t 
                     and re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', str(t['Transaction Date'])))
    date_ratio = valid_dates / len(transactions)
    if date_ratio < 0.9:
        score -= 20
        issues.append(f'Only {date_ratio:.0%} have valid dates')
    
    # Check 2: Valid amounts
    transactions_with_amounts = sum(1 for t in transactions
                                   if any(k in t and t[k] and t[k] > 0 
                                        for k in ['Amount', 'Credits', 'Debits']))
    amount_ratio = transactions_with_amounts / len(transactions)
    if amount_ratio < 0.9:
        score -= 30
        issues.append(f'Only {amount_ratio:.0%} have valid amounts')
    
    # Check 3: Valid descriptions
    valid_descriptions = sum(1 for t in transactions
                            if 'Place' in t 
                            and len(str(t['Place'])) >= 3
                            and any(c.isalpha() for c in str(t['Place'])))
    desc_ratio = valid_descriptions / len(transactions)
    if desc_ratio < 0.8:
        score -= 30
        issues.append(f'Only {desc_ratio:.0%} have valid descriptions')
    
    # Check 4: Reasonable transaction count
    if len(transactions) < 3:
        score -= 20
        issues.append(f'Very few transactions ({len(transactions)})')
    
    # Check 5: No duplicate descriptions
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
