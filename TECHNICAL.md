# Technical Documentation

This document contains detailed technical information for developers and advanced users.

## Table of Contents
- [Architecture](#architecture)
- [Multi-LLM Validation System](#multi-llm-validation-system)
- [Configuration Files](#configuration-files)
- [Python API](#python-api)
- [Processing Pipeline](#processing-pipeline)
- [Payment Processor Handling](#payment-processor-handling)
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
│   ├── category_patterns.json   # Transaction categorization rules
│   ├── income_keywords.json     # Keywords to identify income
│   ├── transfer_keywords.json   # Keywords to detect transfers
│   └── payment_apps.json        # Payment app identifiers
│
├── scripts/                     # User-facing CLI tools
│   ├── process_monthly.py       # Main processing script
│   ├── setup_monthly.py         # Directory setup utility
│   └── add_transaction.py       # Manual transaction entry
│
├── src/
│   ├── bankai/                  # Core parsing engine
│   │   ├── ocr/                 # OCR text extraction
│   │   ├── parser/              # PDF parsing & cross-referencing
│   │   │   └── hybrid_parser.py # Main parser (pdfplumber + OCR)
│   │   └── utils/               # PDF conversion utilities
│   └── ai_classification/       # Transaction categorization
│       └── categorizer.py       # LLM-based categorization
│
├── statements/                  # Your financial data
│   └── YYYY-MM/
│       ├── *.pdf                # Input: Statement PDFs
│       ├── expenses.csv         # Output: Expenses (money out)
│       ├── income.csv           # Output: Income (money in)
│       ├── manual_review.csv    # Output: Needs classification
│       ├── manual_transactions.csv  # Input: Manual entries (optional)
│       └── *_rejected.csv       # Output: Filtered transfers
│
└── tests/                       # Test suite
    ├── test_parser.py           # Parser unit tests
    ├── test_categorizer.py      # Categorization tests
    └── test_workflow.py         # End-to-end tests
```

## Multi-LLM Validation System

The parser uses a sophisticated 3-pass LLM validation system with historical learning for merchant name cleaning:

### Default Model Configuration

**Primary Model:** qwen2.5:14b (9GB)
- Best reasoning capabilities
- 90-95% accuracy on first month
- 95-98% accuracy after 3+ months of learning

**Multi-Model Ensemble:** Enabled by default
- Secondary: dolphin-mistral (4.1GB) or solar:10.7b (6.1GB)
- Different models for different prompts
- Improved accuracy through diversity

### How It Works

**Phase 0: CSV Learning System (NEW)**
- Loads ALL previous months' CSV files automatically
- Builds historical cache: raw merchant → cleaned name
- Tracks frequency: how many times each merchant appears
- Calculates confidence tiers:
  * **High confidence (5+):** Instant recognition (e.g., Cashwise 45x, Costco 22x)
  * **Medium confidence (2-4):** Good context for LLM
  * **Low confidence (1):** Full LLM processing
- Performance: <0.03 seconds to load 21+ CSV files (336 merchants)
- Example output on startup:
  ```
  Loaded 336 merchants from 21 CSV files
  High confidence (5+): 23, Medium (2-4): 63, Low (1): 250
  Top merchants: Cashwise (45x), ATM Withdrawal (26x), Costco (22x)
  ```

**Similar Merchant Detection (NEW)**
- Before LLM processing, searches for similar merchants in history
- Provides top 3 most frequent similar merchants as context
- Example: "WALMART SUPERCENTER #5678" → LLM sees "Walmart - Fargo" (11x)
- Helps LLM learn user's naming preferences
- Improves consistency on edge cases

**Phase 1: Cache Check**
- If merchant seen 5+ times before: Return cached name (instant)
- If merchant seen 2-4 times: Use as context for LLM
- If merchant seen 1 time or never: Full LLM processing with similar examples

**Phase 2: Pattern-Based Cleaning**
- Remove transaction prefixes (RECUR, POS, etc.)
- Handle payment processors (SQSP*→Squarespace, CASH APP*→Cash App, etc.)
- Strip reference codes and location codes
- Remove store numbers and phone numbers

**Phase 3: Multi-Model LLM Validation (3 Prompts)**

1. **Prompt 1: Extraction-Focused** (qwen2.5:14b)
   - Goal: Extract core merchant name
   - Removes cities, states, store numbers
   - Context: Similar merchants from history
   - Temperature: 0.0 (deterministic)

2. **Prompt 2: Location Removal** (dolphin-mistral or solar:10.7b)
   - Goal: Additional location cleaning
   - Removes directional words (West, East, etc.)
   - Different model for diversity
   - Temperature: 0.0 (deterministic)

3. **Prompt 3: Validation** (qwen2.5:14b)
   - Goal: Check if result is valid business name
   - Examples of good vs bad names
   - Temperature: 0.1 (slight variation)

**Phase 4: Confidence-Weighted Voting**
- Each result scored 0-100 based on:
  * Length (3-30 characters optimal)
  * Proper capitalization
  * No artifacts (PURCHASE, RECUR, etc.)
  * Has spaces (word breaks)
- Winner: Highest combined score (confidence + quality)

**Phase 5: Post-Processing Normalization**
- Removes remaining LLM artifacts
- Fixes ALL CAPS → Title Case
- Removes "THE " prefix
- Adds spaces: "COWBOYJACKS" → "Cowboy Jacks"
- Removes extra words: "Steam Purchase" → "Steam"

**Context-Aware Processing**
- Passes transaction amount + date + similar merchants to LLM
- Helps distinguish similar merchants
- Improves accuracy on edge cases
- User's historical patterns inform current decisions

### Processing Pipeline

1. **Historical Cache Loading**
   - Scans ALL previous months' CSV files
   - Builds frequency-tracked merchant cache
   - Identifies high/medium/low confidence merchants
   - Performance: <0.03s for 20+ months of data

2. **Dual PDF Extraction**
   - pdfplumber (fast, digital PDFs)
   - OCR fallback (scanned documents)
   - Cross-reference both for maximum accuracy

3. **OCR Date Error Correction**
   - Fixes common OCR mistakes (42→12, 41→11, 40→10)
   - Validates months are 1-12

4. **Transaction Parsing**
   - Multi-line transaction handling
   - Smart description selection (picks cleanest original)
   - Multiple date formats supported

5. **Merchant Name Cleaning (Intelligent)**
   - Cache check: High-confidence merchants (5+) → instant
   - Similar merchant detection: Provides context to LLM
   - Payment processor identification (see below)
   - Multi-model LLM validation (3 prompts, 2 models)
   - Confidence-weighted voting
   - Post-processing normalization
   - Result cached with frequency tracking

6. **Bank Detection**
   - Automatic bank identification from PDF
   - No static pattern files needed

7. **Income/Expense Classification**
   - Keyword matching (PAYROLL, SALARY, etc.)
   - LLM classification for ambiguous cases
   - Credit card vs bank account handling

8. **Transfer Detection**
   - Cross-account matching
   - Removes duplicate entries

9. **AI Categorization**
   - 23 predefined categories
   - LLM-based classification
   - Manual review flagging

10. **CSV Export with Learning**
    - Saves to expenses.csv, income.csv, manual_review.csv
    - Merchant names become training data for next month
    - Frequency tracking persists in config/merchant_cache.json

## Payment Processor Handling

Payment processors obscure merchant names. The parser handles these specially:

### Processor Pattern Dictionary

Located in `_clean_merchant_name()` around line 1172:

```python
processor_patterns = {
    r'^SQSP\s*\*': ('return', 'Squarespace'),      # Squarespace (no merchant name after)
    r'^CASH\s+APP\s*\*': ('return', 'Cash App'),   # Cash App (personal name follows)
    r'^BP[#\d]': ('return', 'BP'),                 # BP gas (location codes follow)
    r'^SQ\s*\*': ('extract', r'SQ\s*\*\s*([A-Z][A-Z0-9&\s]+)'),  # Square (merchant after)
    r'^WL\s*\*': ('strip', r'^WL\s*\*\s*'),        # WorldLine (merchant after)
}
```

**Three action types:**
- `'return'`: Immediately return value (no LLM)
- `'extract'`: Extract merchant with regex, then LLM
- `'strip'`: Remove prefix, then LLM

**Adding a New Processor:**
```python
r'^VENMO\s*\*': ('return', 'Venmo'),     # Venmo transactions
r'^PYPL\s*\*': ('return', 'PayPal'),     # PayPal transactions
```

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
from src.bankai.parser.hybrid_parser import HybridPDFParser

# Initialize parser with default settings (recommended)
parser = HybridPDFParser(
    llm_model='qwen2.5:14b',     # Default: Best accuracy
    use_multi_model=True,         # Default: Enable ensemble
    ollama_base_url='http://localhost:11434'  # Default Ollama URL
)

# Parser automatically loads CSV learning cache on init
# Output example:
# Loaded 336 merchants from 21 CSV files in 0.021 seconds
# High confidence (5+): 23, Medium (2-4): 63, Low (1): 250

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

# Advanced Configuration
parser = HybridPDFParser(
    llm_model='qwen2.5:14b',              # Primary model
    secondary_model='dolphin-mistral',    # For multi-model ensemble
    use_multi_model=True,                 # Enable ensemble (recommended)
    ollama_base_url='http://localhost:11434',
    timeout=60,                           # LLM timeout in seconds
    month_str='2025-11'                   # For CSV learning path
)
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

## Performance & Optimization

### CSV Learning Performance

The historical cache system is extremely fast:

**Metrics:**
- Loading time: <0.03 seconds for 21+ CSV files
- Memory usage: ~2MB for 336 merchants
- No time limit needed: Scans ALL previous months

**Example output on parser initialization:**
```
[CACHE] Loaded 336 merchants from 21 CSV files in 0.021 seconds
[CACHE] High confidence (5+): 23 merchants
[CACHE] Medium confidence (2-4): 63 merchants
[CACHE] Low confidence (1): 250 merchants
[CACHE] Top merchants: Cashwise - West Fargo (45x), ATM Withdrawal (26x), Costco (22x)
```

**Confidence Distribution:**
- High confidence (5+): 7% of merchants - Instant recognition
- Medium confidence (2-4): 19% of merchants - Good LLM context
- Low confidence (1): 74% of merchants - Full LLM processing

### Processing Speed

**First Month (No History):**
- Typical: 30-60 minutes for 100 transactions
- Every transaction requires full LLM processing (3 prompts)
- Multi-model ensemble adds ~20% overhead but improves accuracy

**Subsequent Months (With History):**
- High-confidence merchants: Instant (<0.001s per transaction)
- Medium-confidence: ~2-5 seconds per transaction
- Low-confidence: ~10-20 seconds per transaction (full LLM)
- Expected speedup: 50-70% faster overall

**Example progression:**
- Month 1: 40 minutes (90% accuracy)
- Month 2: 25 minutes (93% accuracy)
- Month 3+: 15 minutes (95-98% accuracy)

### Cache Persistence

**Location:** `config/merchant_cache.json`

**Format:**
```json
{
  "CASHWISE #1234 WEST FARGO ND": "Cashwise - West Fargo",
  "TARGET T-1234 FARGO ND": "Target",
  "COSTCO WHSE #123": "Costco"
}
```

**Frequency Tracking:** Internal dictionary (not saved to JSON)
- Recalculated on each run by scanning CSV files
- Always up-to-date with current data

### Optimization Tips

**For Maximum Speed:**
1. Use `--manual-only` mode for quick updates (skips PDF processing)
2. High-confidence merchants process instantly (build history over time)
3. Multi-model ensemble is worth the 20% overhead for accuracy

**For Maximum Accuracy:**
1. Keep default settings (qwen2.5:14b + multi-model)
2. Let history build over 3+ months
3. Review and correct low-confidence merchants
4. Your corrections become training data

**Memory Management:**
- CSV cache: ~2MB for 300+ merchants
- LLM models: qwen2.5:14b (9GB), dolphin-mistral (4.1GB)
- Ollama keeps models in RAM when active
- Total RAM needed: ~16GB recommended

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
3. High-confidence merchants process instantly after 3+ months of history
4. CSV learning system speeds up subsequent months by 50-70%
5. Expected: Month 1 (40min) → Month 3+ (15min) for 100 transactions

### Issue: Merchant Names Still Have Location/Numbers

**Symptoms:**
Place names like "Target Fargo #1234" instead of just "Target"

**Solutions:**
1. Verify Ollama is running: `ollama list`
2. Check qwen2.5:14b is installed: `ollama pull qwen2.5:14b`
3. Enable multi-model ensemble: `use_multi_model=True` (default)
4. Let history build: Corrections in expenses.csv become training data
5. Check merchant_cache.json for your corrections

### Issue: Low Confidence Warnings

**Symptoms:**
Many merchants flagged as "low confidence (1 occurrence)"

**Solutions:**
1. This is normal for first month or one-time transactions
2. Regular merchants gain confidence over time automatically
3. High confidence (5+): No LLM processing needed (instant)
4. Review and correct low-confidence merchants in expenses.csv
5. Your corrections will be cached for next month

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
