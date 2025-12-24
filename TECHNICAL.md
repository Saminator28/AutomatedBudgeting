# Technical Documentation

This document contains detailed technical information for developers and advanced users.

## Table of Contents
- [Architecture](#architecture)
- [Configuration Files](#configuration-files)
- [Python API](#python-api)
- [Processing Modes](#processing-modes)
- [Privacy & Security](#privacy--security)
- [Adding Custom Banks](#adding-custom-banks)
- [Manual Transaction Import](#manual-transaction-import)
- [Category System](#category-system)
- [Troubleshooting](#troubleshooting)

## Architecture

### Project Structure
```
AutomatedBudgeting/
├── config/                      # Configuration files
│   ├── bank_patterns.json       # Bank detection patterns
│   ├── category_patterns.json   # Transaction categorization rules
│   └── income_keywords.json     # Keywords to identify income
│
├── scripts/                     # User-facing CLI tools
│   ├── process_monthly.py       # Main processing script
│   └── setup_monthly.py         # Directory setup utility
│
├── src/
│   ├── bankai/                  # Core parsing engine
│   │   ├── ocr/                 # Text extraction (Tesseract)
│   │   ├── parser/              # Statement parsing & table detection
│   │   └── utils/               # PDF conversion & place cleaning
│   └── ai_classification/       # Transaction categorization
│
└── statements/                  # Your financial data
    └── YYYY-MM/
        ├── *.pdf                # Input: Statement PDFs
        ├── expenses.csv         # Output: Expenses (money out)
        ├── income.csv           # Output: Income (money in)
        ├── manual_review.csv    # Output: Needs classification
        ├── manual_transactions.csv  # Input: Manual entries (optional)
        └── *_rejected.csv       # Output: Filtered transfers
```

### Processing Pipeline

1. **PDF Loading** → pdf2image converts PDF pages to images
2. **Table Detection** → Microsoft Table Transformer identifies transaction tables
3. **OCR Extraction** → Tesseract extracts text from detected tables
4. **Data Structuring** → Parser converts text to structured DataFrame
5. **Bank Detection** → Pattern matching identifies statement source
6. **Place Cleaning** → spaCy NER + optional Ollama LLM cleans merchant names
7. **Income/Expense Split** → Keyword matching separates credits/debits
8. **Transfer Detection** → Cross-account matching removes duplicates
9. **Categorization** → AI assigns categories to transactions
10. **Manual Review** → Payment apps and uncategorized flagged for review

## Configuration Files

### bank_patterns.json

Maps bank names as they appear in PDFs to display names:

```json
{
  "patterns": {
    "CHASE": "Chase",
    "WELLS FARGO": "Wells Fargo",
    "DISCOVER": "Discover",
    "BANK OF AMERICA": "Bank of America"
  }
}
```

**Key (left)**: Text appearing in PDF header (case-insensitive)  
**Value (right)**: Display name in CSV output

### category_patterns.json

Defines 23 transaction categories with keyword patterns:

```json
{
  "categories": {
    "Groceries": [
      "walmart",
      "safeway",
      "whole foods",
      "kroger"
    ],
    "Dining": [
      "restaurant",
      "mcdonald",
      "starbucks",
      "cafe"
    ]
  }
}
```

**Category Learning**: When you classify an uncategorized transaction in `manual_review.csv`, the place is automatically added to this file for future automatic categorization.

### income_keywords.json

Keywords that identify income transactions:

```json
{
  "income_keywords": [
    "DEPOSIT",
    "PAYROLL",
    "SALARY",
    "DIRECT DEP",
    "ACH CREDIT",
    "INTEREST EARNED",
    "REFUND",
    "CASHBACK",
    "BONUS"
  ]
}
```

**Case-insensitive matching**: Checked against transaction descriptions.

## Python API

### Basic Usage

```python
from src.bankai.parser.statement_parser import StatementParser

# Initialize parser
parser = StatementParser(
    clean_place_names=True,      # Enable merchant name cleaning
    use_llm_cleaning=False        # Use spaCy only (True = Ollama LLM)
)

# Parse single statement
result = parser.bankstatement2csv(
    pdf='statements/2025-11/statement.pdf',
    output_file='output.csv',
    visualize=False,              # Set True to save table detection images
    return_dataframe=True,        # Return DataFrame instead of saving
    detect_source=True            # Enable bank auto-detection
)

if result:
    df, source_name = result
    print(f"Extracted {len(df)} transactions from {source_name}")
```

### Advanced Categorization

```python
from src.ai_classification.categorizer import TransactionCategorizer

# Initialize categorizer
categorizer = TransactionCategorizer(use_llm=True)  # Enable Ollama validation

# Categorize DataFrame
df = categorizer.categorize_dataframe(
    df,
    description_column='Place',
    amount_column='Amount'
)

# Print categorization report
categorizer.print_categorization_report(
    df,
    merchant_column='Place',
    month='2025-11'
)
```

## Processing Modes

### Full Reprocess Mode (Default)
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

**What it does:**
1. Deletes all generated CSV files
2. Reprocesses all PDFs from scratch
3. Applies OCR, table detection, categorization
4. Validates manual_review.csv classifications
5. Imports manual_transactions.csv
6. Generates fresh expenses/income/manual_review.csv

**When to use:**
- PDFs changed or added
- Want clean slate
- Testing configuration changes
- Monthly initial processing

### Manual-Only Mode (Lightweight)
```bash
python scripts/process_monthly.py --month 2025-11 --manual-only
```

**What it does:**
1. Skips PDF processing (fast!)
2. Validates categories in manual_review.csv
3. Validates categories in manual_transactions.csv
4. Moves classified transactions to expenses/income.csv
5. Updates manual_review.csv to remove processed items
6. Learns patterns from uncategorized transactions

**When to use:**
- Iterative classification workflow
- Already processed PDFs
- Just adding manual transactions
- Quick category validation

### No-Force Mode
```bash
python scripts/process_monthly.py --month 2025-11 --no-force
```

**What it does:**
- Skips months that already have expenses.csv
- Useful for batch processing new months only

## Privacy & Security

### How Privacy is Ensured

**No Network Communication:**
- All AI models run locally (Microsoft Table Transformer, spaCy NER)
- Ollama LLM runs locally at `http://localhost:11434`
- Tesseract OCR processes on your machine
- No API calls to OpenAI, Google, or cloud services

**Verification Steps:**

1. **Disconnect Internet Test:**
```bash
sudo ifconfig en0 down  # macOS
sudo ip link set eth0 down  # Linux

python scripts/process_monthly.py --month 2025-11
# Should work fine!
```

2. **Network Monitoring:**
```bash
# Monitor network activity during processing
sudo nethogs  # Linux
sudo lsof -i  # macOS/Linux
```

3. **Code Audit:**
```bash
# Search for external API calls
grep -r "api.openai.com" src/ scripts/
grep -r "http://" src/ scripts/ | grep -v "localhost"
```

**Data Protection Best Practices:**

- Encrypt `statements/` directory
- Enable full-disk encryption (LUKS, FileVault, BitLocker)
- Keep PDFs off cloud-synced folders
- Add sensitive files to `.gitignore`
- Run on air-gapped machine for maximum security

## Adding Custom Banks

### Step 1: Identify Bank Name in PDF

Open your PDF and look at the header/logo area. The bank name should be prominently displayed.

### Step 2: Add Pattern to Configuration

Edit `config/bank_patterns.json`:

```json
{
  "patterns": {
    "YOUR BANK NAME": "Your Bank Display Name",
    "STEARNS BANK": "Stearns Bank",
    "MOUNTAIN AMERICA": "Mountain America Credit Union"
  }
}
```

### Step 3: Test Detection

```bash
python scripts/process_monthly.py --month 2025-11 --force
```

Check the "Statement" column in `expenses.csv` - should show your display name.

### Step 4: Handle Edge Cases

If detection still fails:

1. **Check PDF text extraction:**
```python
from PyPDF2 import PdfReader
reader = PdfReader('statement.pdf')
print(reader.pages[0].extract_text()[:500])  # First 500 chars
```

2. **Look for alternative text** in the header
3. **Add multiple patterns** for the same bank:
```json
{
  "patterns": {
    "BANK NAME": "Bank",
    "BANK NAME NA": "Bank",
    "BANK NAME N.A.": "Bank"
  }
}
```

## Manual Transaction Import

### CSV Format Specification

**Required columns:**
- `Transaction Date` - Format: MM/DD/YYYY, MM-DD-YYYY, or YYYY-MM-DD
- `Place` - Merchant/place name (will be cleaned automatically)
- `Amount` - Positive number (use negative for refunds)

**Optional columns:**
- `category` - Pre-assign category (validated and auto-corrected)
- `Statement` - Source identifier (defaults to "Cash")

**Example:**
```csv
Transaction Date,Place,Amount,category
11/26/2025,Farmer's Market,35.50,Groceries
11/27/2025,Coffee Shop,6.25,Dining
11/28/2025,Hardware Store,42.99,Shopping
11/29/2025,Store Return,-15.00,Shopping
```

### Date Format Handling

Supported formats (auto-detected):
- `11/26/2025` (MM/DD/YYYY)
- `11-26-2025` (MM-DD-YYYY)
- `2025-11-26` (YYYY-MM-DD)
- `11/26/25` (MM/DD/YY)
- `11/26` (MM/DD - assumes current year)

### Category Validation

Categories are validated during import:

```bash
python scripts/process_monthly.py --month 2025-11 --manual-only
```

**Output:**
```
📝 Manual Transaction Category Corrections:
  ✓ 'food' → 'Dining' (Coffee Shop)
  ✓ 'donation' → 'Gifts & Charity' (Charity)

📚 Added 2 place(s) to category_patterns.json:
  + 'coffee shop' → Dining
  + 'charity' → Gifts & Charity

❌ INVALID CATEGORIES FOUND - Please fix these in manual_transactions.csv:
  ✗ 'invalid_cat' for 'Some Store'
```

### Month Validation

Transactions are automatically filtered to the correct month:

```bash
# Processing 2025-11
# Transaction dated 12/01/2025 will be skipped with warning
```

## Category System

### Available Categories (23 Total)

1. **Essential Living**
   - Groceries
   - Dining
   - Rent
   - Utilities
   - Healthcare
   - Insurance

2. **Transportation**
   - Transportation
   - Auto Maintenance
   - Fuel

3. **Personal**
   - Personal Care
   - Clothing
   - Education

4. **Financial**
   - Investment
   - Banking Fees

5. **Lifestyle**
   - Entertainment
   - Shopping
   - Subscriptions
   - Gifts & Charity
   - Travel
   - Pet Care

6. **Miscellaneous**
   - Home Improvement
   - Other

7. **Uncategorized** (fallback)

### Category Validation Flow

```
User enters category → Exact match check → LLM validation (if enabled)
                                       ↓
                                 Fuzzy pattern match
                                       ↓
                                 Flag as invalid OR
                                 Auto-correct with confidence score
```

### Pattern Learning

**Uncategorized Transactions:**
- Automatically added to `category_patterns.json`
- Won't need manual review next time

**Payment Apps (Venmo/Zelle):**
- Never added to patterns (require context each time)
- Always appear in manual_review.csv

## Troubleshooting

### Issue: LLM Timeout Errors

**Symptoms:**
```
[LLM Error for 'food']: Connection timeout
```

**Solutions:**
1. Check Ollama is running: `ollama list`
2. Restart Ollama: `ollama serve`
3. Increase timeout in `process_monthly.py` line 248:
   ```python
   timeout=60  # Increase from 30 to 60 seconds
   ```

### Issue: Bank Not Detected

**Symptoms:**
Statement column shows "Unknown"

**Solutions:**
1. Check PDF text extraction
2. Add pattern to `bank_patterns.json`
3. Check for typos in pattern key
4. Try multiple pattern variations

### Issue: Wrong Income/Expense Classification

**Symptoms:**
Paycheck appears in expenses, or bill appears in income

**Solutions:**
1. Edit `config/income_keywords.json`
2. Add unique keywords from transaction description
3. Reprocess with `--force`

### Issue: Categories Not Sticking

**Symptoms:**
Manually classified transactions revert to original category

**Solutions:**
1. Use `--manual-only` mode (preserves manual classifications)
2. Check `_manual_category` flag in DataFrame
3. Ensure not using `--force` when updating classifications

### Issue: Manual Transactions Not Importing

**Symptoms:**
Manual transactions don't appear in expenses.csv

**Solutions:**
1. Check CSV format (required columns: Date, Place, Amount)
2. Verify dates are in correct month format
3. Remove comment lines (starting with `#`)
4. Check for empty lines or formatting issues

### Issue: Performance Problems

**Symptoms:**
Processing takes very long

**Solutions:**
1. Use `--manual-only` for quick updates (skips PDF processing)
2. Process specific months instead of all: `--month 2025-11`
3. Disable LLM if not needed: `use_llm_cleaning=False`
4. Reduce PDF quality if file size is large

## Testing & Development

### Test Suite

The project includes a comprehensive test suite for developers:

```bash
# Run all tests
python tests/run_tests.py

# Run specific test module
python tests/run_tests.py test_parser

# Verbose mode
python tests/run_tests.py -v
```

**Test Modules:**
- `test_parser.py` - Transaction line parsing, bank detection
- `test_categorizer.py` - AI categorization, validation, income detection
- `test_workflow.py` - Integration tests for monthly processing
- `test_config.py` - Configuration file validation

**Test Coverage:**
- ~41 unit tests covering core functionality
- Fast execution (~30 seconds, no PDF processing)
- 21 tests verify existing features
- 20 tests document aspirational features (expected to fail)

See `tests/README.md` for detailed documentation.

### Automated Test Reports on Release

The project includes a GitHub Actions workflow that automatically:
- Runs the full test suite when a release is created
- Generates detailed test reports (TXT and Markdown formats)
- Attaches reports to the GitHub release
- Updates release notes with test summary

**Files attached to each release:**
- `test-report-{version}.txt` - Full test output with details
- `test-summary-{version}.md` - Formatted summary with metadata

**Workflow location:** `.github/workflows/release.yml`

**Manual trigger:**
You can also manually run the workflow from GitHub Actions tab for any branch.

### API Improvements (Roadmap)

These APIs are documented in tests but not yet implemented:

**Pattern Learning:**
- `TransactionCategorizer.add_pattern(place, category)` - Programmatically add categorization patterns

**Category Validation:**
- `TransactionCategorizer.is_valid_category(category)` → bool - Check if category is valid
- `TransactionCategorizer.correct_category(typo)` → corrected_category - Fix typos/abbreviations

**Income Detection:**
- `TransactionCategorizer.is_income(place)` → bool - Check if transaction is income

**Bank Detection:**
- `StatementParser._detect_bank_from_text(header_text)` → bank_name - Identify bank from PDF header

**Data Quality Improvements:**
- Standardize debit/credit amount handling in parser
- Normalize config file structures for easier programmatic access
- Add comprehensive unit test coverage for all public APIs

## Advanced Topics

### Custom Categorization Logic

Extend the categorizer:

```python
from src.ai_classification.categorizer import TransactionCategorizer

class CustomCategorizer(TransactionCategorizer):
    def categorize_transaction(self, description, amount):
        # Custom logic
        if amount > 1000:
            return "Large Purchase"
        return super().categorize_transaction(description, amount)
```

### Batch Processing Multiple Accounts

```python
from pathlib import Path
from src.bankai.parser.statement_parser import StatementParser

parser = StatementParser()
accounts = ['checking', 'savings', 'credit_card']

for account in accounts:
    pdfs = Path(f'statements/{account}').glob('*.pdf')
    for pdf in pdfs:
        parser.bankstatement2csv(pdf=str(pdf))
```

### Export to Other Formats

```python
import pandas as pd

# Load expenses
df = pd.read_csv('statements/2025-11/expenses.csv')

# Export to JSON
df.to_json('expenses.json', orient='records', indent=2)

# Export to Excel with formatting
with pd.ExcelWriter('expenses.xlsx', engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Expenses', index=False)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT License - See [LICENSE](LICENSE) for details.
