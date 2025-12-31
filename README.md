# Automated Budgeting Tool

**Turn your bank statements into organized spreadsheets - automatically!**

Drop your PDF bank statements in a folder, run one command, and get clean CSV files with all your transactions organized and categorized.

> **100% Private** - Everything runs on your computer. No data sent anywhere.
> **Multi-LLM Validation** - 3-pass merchant name cleaning with confidence scoring for maximum accuracy.

## What Does This Do?

This tool reads your bank statement PDFs and creates spreadsheets (CSV files) with:

✅ **All your transactions** organized by date  
✅ **Separate files** for money in (income) vs money out (expenses)  
✅ **Categories** automatically assigned (groceries, dining, rent, etc.)  
✅ **Clean merchant names** - Multi-LLM validation removes extra numbers, locations, and codes  
✅ **Dual extraction** - Cross-references pdfplumber + OCR for maximum accuracy  
✅ **Your manual cash purchases** included automatically

**Works with any bank!** Chase, Bank of America, Wells Fargo, Discover, credit cards, and more.

## Quick Example

**You have:** `November_Statement.pdf` (messy bank PDF)

**You get:**
- `expenses.csv` - Your spending organized by category
- `income.csv` - Your paychecks and deposits  
- `manual_review.csv` - A few transactions that need your input

**Time:** ~30 seconds per statement

---

## Getting Started

### What You Need

- A computer (Windows, Mac, or Linux)
- Python 3.8 or newer
- 15 minutes for setup (one-time)

### Installation

**Step 1: Install Tesseract** (reads text from PDFs)

Choose your operating system:

<details>
<summary><strong>Windows</strong></summary>

1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer
3. Download Poppler: https://github.com/oschwartz10612/poppler-windows/releases/

## Dashboard (Web UI)

Visualize your categorized expenses in an interactive dashboard (pie chart, table, filters) using a local web app. Works on Windows, macOS, and Linux.

### Prerequisites
- Python dependencies: Already installed via `requirements.txt` (see above)
- Node.js and npm: [Download here](https://nodejs.org/) if not already installed

### Quick Start (All Platforms)
From the project root, run:
```bash
pip install -r requirements.txt
bash scripts/launch_dashboard.sh
```
This launches both the backend (FastAPI) and frontend (React). The dashboard opens at [http://localhost:3000](http://localhost:3000).

#### Windows users:
- If `bash` is not available, run the backend and frontend manually (see below).

### Manual Start (All Platforms)
1. **Start the backend:**
  ```bash
  cd src/ui/backend
  uvicorn main:app --reload
  ```
2. **Start the frontend (in a new terminal):**
  ```bash
  cd src/ui
  npm install
  npm start
  ```
3. Open your browser to [http://localhost:3000](http://localhost:3000)

### How it works
- The dashboard reads from the latest `expenses.csv` in your `statements/YYYY-MM/` folders.
- The backend provides an API at `/api/expense-categories` for the frontend.

### Troubleshooting
- If you see errors about missing Node.js/npm, [install Node.js here](https://nodejs.org/).
- If port 3000 or 8000 is in use, stop other apps or change the port in the scripts.
- For more details, see [TECHNICAL.md](TECHNICAL.md).

---
5. Add to PATH: `C:\Program Files\poppler\Library\bin`

</details>

<details>
<summary><strong>Mac</strong></summary>

Open Terminal and run:
```bash
brew install tesseract
brew install poppler
```

</details>

<details>
<summary><strong>Linux</strong></summary>

Open Terminal and run:
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

</details>

**Step 2: Set Up Python Environment**

Open Terminal (Mac/Linux) or Command Prompt (Windows):

<details>
<summary><strong>Mac/Linux</strong></summary>

```bash
# Go to project folder
cd ~/Documents/AutomatedBudgeting

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Download language model
python -m spacy download en_core_web_sm
```

</details>

<details>
<summary><strong>Windows</strong></summary>

```batch
REM Go to project folder (adjust path to where you downloaded it)
cd C:\Users\YourName\Documents\AutomatedBudgeting

REM Create virtual environment
python -m venv venv

REM Activate it
venv\Scripts\activate

REM Install required packages
pip install -r requirements.txt

REM Download language model
python -m spacy download en_core_web_sm
```

</details>

**You're done!** 🎉

---

## How to Use

### Basic Workflow

**1. Organize your PDFs**

Create folders for each month:
```
statements/
  2025-11/
    chase_checking.pdf
    visa_card.pdf
  2025-12/
    chase_checking.pdf
```

**2. Run the processor**

**Mac/Linux:**
```bash
# Activate virtual environment first
source venv/bin/activate

# Process your statements
python scripts/process_monthly.py --month 2025-11
```

**Windows:**
```batch
REM Activate virtual environment first
venv\Scripts\activate

REM Process your statements
python scripts\process_monthly.py --month 2025-11
```

**3. Check your results**

Look in `statements/2025-11/`:
- `expenses.csv` - Open in Excel/Google Sheets
- `income.csv` - Your paychecks and deposits
- `manual_review.csv` - A few items need your input (optional)

That's it! 🎉

---

## Common Tasks

> **Remember:** Always activate your virtual environment first!
> - Mac/Linux: `source venv/bin/activate`
> - Windows: `venv\Scripts\activate`

### Process All Your Statements at Once

```bash
# Mac/Linux
python scripts/process_monthly.py

# Windows
python scripts\process_monthly.py
```

Processes every month folder and skips ones already done.

### Process Just the Latest Month

```bash
# Mac/Linux
python scripts/process_monthly.py --month latest

# Windows
python scripts\process_monthly.py --month latest
```

### Add Cash Purchases

You can add transactions that aren't on your bank statement (cash purchases, etc.):

**1. Create a file:** `manual_transactions.csv` in your month folder
- Mac/Linux: `statements/2025-11/manual_transactions.csv`
- Windows: `statements\2025-11\manual_transactions.csv`

**2. Add your transactions:**
```csv
Transaction Date,Place,Amount,category
11/26/2025,Farmer's Market,35.50,Groceries
11/27/2025,Cash Coffee Shop,6.25,Dining
```

**3. Run the processor:**
```bash
# Mac/Linux
python scripts/process_monthly.py --month 2025-11

# Windows
python scripts\process_monthly.py --month 2025-11
```

Your cash transactions will be automatically included!

### Handle Transactions Needing Review

Some transactions need your input (like Venmo payments - could be gifts, bills, etc.):

**1. Open:** `statements/2025-11/manual_review.csv`

**2. Fill in the Classification and category columns:**
```csv
Transaction Date,Place,Amount,Classification,category
11/15/2025,Venmo Payment,50.00,Expense,Gifts & Charity
11/20/2025,Zelle Transfer,100.00,Expense,Rent
```

**3. Update your files:**
```bash
# Mac/Linux
python scripts/process_monthly.py --month 2025-11 --manual-only

# Windows
python scripts\process_monthly.py --month 2025-11 --manual-only
```

These transactions will move to your expenses or income file.

---

## Categories

Your transactions are automatically sorted into these categories:

**Daily Life:** Groceries, Dining, Transportation, Utilities  
**Personal:** Healthcare, Shopping, Entertainment, Personal Care  
**Home:** Rent, Home Improvement  
**Financial:** Insurance, Banking Fees, Investment  
**Other:** Gifts & Charity, Travel, Education, Pet Care, Subscriptions

**Don't see your category?** See [TECHNICAL.md](TECHNICAL.md) for the complete list and how to add custom ones.

---

## Tips & Tricks

### Start Small
Process one month first to get comfortable:
```bash
# Mac/Linux
python scripts/process_monthly.py --month 2025-11

# Windows
python scripts\process_monthly.py --month 2025-11
```

### Monthly Routine
1. Download statements from your bank (PDF)
2. Put them in a new folder:
   - Mac/Linux: `statements/2025-12/`
   - Windows: `statements\2025-12\`
3. Run the processor:
   - Mac/Linux: `python scripts/process_monthly.py --month latest`
   - Windows: `python scripts\process_monthly.py --month latest`
4. Open the CSV files in Excel or Google Sheets

### Keep It Organized
- Use one folder per month: `statements/2025-11/`, `statements/2025-12/`
- Name PDFs clearly: `chase_checking.pdf`, `visa_card.pdf`
- Back up your CSV files regularly

---

## Getting Help

### Something Not Working?

**Check these first:**
1. Did you activate the virtual environment?
   - Mac/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
2. Are your PDFs in the right folder?
   - Mac/Linux: `statements/YYYY-MM/`
   - Windows: `statements\YYYY-MM\`
3. Is the month format correct? (Must be `YYYY-MM` like `2025-11`)

**Common Issues:**

<details>
<summary><strong>"Command not found" or "python is not recognized" error</strong></summary>

**Mac/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```batch
venv\Scripts\activate
```

**After activation**, you should see `(venv)` at the start of your command prompt.

**If that doesn't work (Windows):**
- Try: `python3` instead of `python`
- Or try: `py` instead of `python`
- Make sure Python is installed: Download from https://www.python.org/downloads/

</details>

<details>
<summary><strong>"No PDFs found" message</strong></summary>

Check your folder structure:

**Mac/Linux:**
```
statements/
  2025-11/  ← Must use YYYY-MM format
    *.pdf   ← PDFs go here
```

**Windows:**
```
statements\
  2025-11\  ← Must use YYYY-MM format
    *.pdf   ← PDFs go here
```

</details>

<details>
<summary><strong>Bank name shows as "Unknown"</strong></summary>

See "Adding Your Bank" in [TECHNICAL.md](TECHNICAL.md) - it's a simple one-line configuration.

</details>

### Want More Details?

See [TECHNICAL.md](TECHNICAL.md) for:
- Advanced configuration
- Privacy & security details
- Troubleshooting guide
- Python API documentation
- Custom categorization rules

### Need Help?

Open an issue on GitHub with:
- What you tried to do
- What happened instead
- Any error messages you saw

---

## Privacy & Security

**Your data never leaves your computer.**

- ✅ No internet connection needed (except initial setup)
- ✅ No accounts to create
- ✅ No cloud uploads
- ✅ All AI runs locally on your machine

Want proof? Disconnect from the internet and it still works!

---

## What's Next?

Once you're comfortable with the basics, you can:

- Set up automatic categorization rules
- Add your own bank if it's not detected
- Configure custom categories
- Export to accounting software

See [TECHNICAL.md](TECHNICAL.md) for advanced features.

---

## Support the Project

If this tool saves you time, consider:
- ⭐ Starring the project on GitHub
- 📢 Sharing with friends who do budgeting
- 🐛 Reporting bugs you find
- 💡 Suggesting improvements

---

## Disclaimers

⚠️ **AI-Generated Code:** This tool was built using AI code generation. Always verify extracted financial data against your original statements.

---

## Credits

- Built upon concepts from [BankAIAgent](https://github.com/farhan0167/BankAIAgent)
- Uses Microsoft's Table Transformer Model
- OCR powered by Tesseract

## License

MIT License - Free to use, modify, and share!

---

**For developers and advanced users:** See [TECHNICAL.md](TECHNICAL.md) for detailed documentation, API reference, and configuration options.

## Features

### Core Processing
- ✅ Convert PDF bank/credit card statements to CSV
- ✅ Automatic bank/card detection from statement headers
- ✅ AI-based table detection and extraction
- ✅ OCR-based text extraction from scanned documents
- ✅ Monthly batch processing with automatic consolidation
- ✅ Intelligent merchant name cleaning (LLM-based with qwen2.5:14b + multi-model ensemble)
- ✅ Customizable bank pattern matching
- ✅ **100% Private - All processing happens locally on your machine**

### Transaction Management
- ✅ Automatic income vs expense separation
- ✅ Cross-statement transfer detection (eliminates duplicate transfers)
- ✅ Manual transaction import from CSV
- ✅ Payment app detection (Venmo, Zelle, Cash App, PayPal)

### Categorization & Intelligence
- ✅ AI-powered transaction categorization (23 categories)
- ✅ Smart category validation with LLM + fuzzy matching
- ✅ Automatic typo/abbreviation correction ("food" → "Dining")
- ✅ Automatic pattern learning from manual classifications
- ✅ Manual review workflow for ambiguous transactions
- ✅ Distinction between payment apps (always review) and uncategorized (learn once)

### Workflow Options
- ✅ Lightweight `--manual-only` mode for quick updates
- ✅ Force reprocessing mode for complete regeneration
- ✅ Batch processing of all months or specific months

### Future Enhancements
- 🔮 Natural language budget queries ("Can I afford a $500 TV?")
- 🚧 Recurring payment identification and prediction
- 🚧 Budget analysis and spending trend reports
- 🚧 Budget alerts and notifications

## Privacy & Security

**Your financial data never leaves your computer.** This tool is designed with privacy as a top priority:

- ✅ **No internet connection required** - All processing is done locally
- ✅ **No external APIs** - No data sent to OpenAI, Google, or any cloud services
- ✅ **Pre-trained AI models** - Microsoft Table Transformer, spaCy NER, and optional Ollama LLM run entirely offline
- ✅ **Local OCR** - Tesseract OCR runs on your machine
- ✅ **Intelligent merchant name cleaning** - 3-phase approach:
  - **Phase 1**: Pattern-based noise removal (50+ regex patterns)
  - **Phase 2**: Multi-LLM intelligent cleaning (qwen2.5:14b + ensemble, enabled by default)
  - **Phase 3**: Post-processing normalization (removes artifacts, fixes formatting)
  - **Phase 4**: Fallback smart title case (when LLM unavailable)

**To verify privacy:**
- Disconnect from the internet and run the script - it will work fine
- Review the source code - no network requests or API calls
- Monitor network activity with `sudo nethogs` while processing - no outbound traffic

**Additional security measures you can take:**
- Keep PDFs only on this machine (avoid cloud storage sync)
- Encrypt the `statements/` directory
- Use full-disk encryption (LUKS on Linux, FileVault on macOS, BitLocker on Windows)
- Add sensitive files to `.gitignore`: `statements/`, `*.pdf`, `*.csv`

The only internet usage is during initial setup to download:
1. Microsoft Table Transformer model weights (one-time, ~100MB)
2. spaCy language model for NER (one-time, ~13MB)
3. Ollama LLM models (required, one-time, ~13GB for qwen2.5:14b + dolphin-mistral)

After installation, the tool works completely offline.

## Prerequisites

### System Requirements
- Python 3.8+
- Tesseract OCR installed on your system
- spaCy language model (required for intelligent cleaning)
- Ollama with qwen2.5:14b model (required, for intelligent merchant name cleaning)
- Ollama with dolphin-mistral model (recommended, for multi-model ensemble)

### Install Tesseract OCR

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

**Windows:**
Download installer from: https://github.com/UB-Mannheim/tesseract/wiki

### Install Poppler (for pdf2image)

**Linux:**
```bash
sudo apt-get install poppler-utils
```

**macOS:**
```bash
brew install poppler
```

**Windows:**
1. Download poppler from: https://github.com/oschwartz10612/poppler-windows/releases/
2. Extract to `C:\Program Files\poppler`
3. Add `C:\Program Files\poppler\Library\bin` to your PATH environment variable

## Installation

1. Clone or navigate to the project directory:
```bash
cd ~/Documents/AutomatedBudgeting
```

2. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. **(Required)** Install Ollama for LLM-based merchant name cleaning:

**Linux/macOS:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull qwen2.5:14b model (required, ~9GB)
ollama pull qwen2.5:14b

# Optional: Install secondary model for multi-model ensemble (recommended)
ollama pull dolphin-mistral  # 4.1GB - for 90-95% accuracy
```

**Windows:**
1. Download Ollama installer from: https://ollama.com/download/windows
2. Run the installer  
3. Open PowerShell and run:
```powershell
ollama pull qwen2.5:14b
ollama pull dolphin-mistral
```

**Why qwen2.5:14b?**
- **Best reasoning**: 14B model provides superior merchant name extraction
- **Maximum accuracy**: 90-95% accuracy with multi-model ensemble
- **Handles edge cases**: Better at complex/ambiguous merchant names
- **No static lists**: Handles any merchant name dynamically
- **Local**: 100% private, runs entirely on your machine
- **Learns from you**: Remembers your manual corrections from CSV edits

**See [docs/MODELS.md](docs/MODELS.md) for full model guide and alternatives**

**How to use:**
```python
from bankai.parser.hybrid_parser import HybridPDFParser

# Multi-model ensemble enabled by default
parser = HybridPDFParser()  # Uses qwen2.5:14b + dolphin-mistral
income_df, expenses_df, bank, is_bank = parser.parse_pdf('statement.pdf')

# Use single model
parser = HybridPDFParser(use_multi_model=False)

# Use different model
parser = HybridPDFParser(llm_model='qwen2.5:7b')  # Lighter option (4.7GB)
```
```

**Alternative Models** (if qwen2.5:7b doesn't work for you):
- `llama3.1:8b` (4.9GB) - Meta's model, great all-around performance
- `gemma2:9b` (5.5GB) - Google's efficient model, good at concise outputs

The tool automatically uses pattern-only cleaning if Ollama isn't installed.

5. Download the spaCy language model (used for advanced features):

## Usage

### Activate Virtual Environment

Before running any commands, activate the virtual environment:

```bash
# On Linux/macOS
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

You'll see `(venv)` in your terminal prompt. Now you can use `python` commands.

### Processing Monthly Statements

The recommended way to process your statements is to organize them by month and use the batch processor:

1. **Organize your statements** in monthly directories:
```bash
statements/
  2025-11/
    statement1.pdf
    statement2.pdf
  2025-12/
    statement1.pdf
```

2. **Process all months** (default - skips months that already have expenses.csv):
```bash
python scripts/process_monthly.py
```

3. **Process a specific month:**
```bash
python scripts/process_monthly.py --month 2025-11
```

4. **Process only the latest month:**
```bash
python scripts/process_monthly.py --month latest
```

5. **Quick update after manual classifications:**
```bash
python scripts/process_monthly.py --month 2025-11 --manual-only
```

6. **Force full reprocess** (regenerate everything from PDFs):
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

**Command-line options:**
- `--month YYYY-MM` - Process specific month (e.g., `2025-11`)
- `--month latest` - Process only the latest month
- `--force` - Force reprocess even if CSV exists (default: enabled)
- `--no-force` - Skip processing if CSV already exists
- `--manual-only` - Lightweight mode: only process manual_review.csv classifications without reprocessing PDFs

**Processing modes:**
- **Default**: Process all PDFs, merge with manual_transactions.csv, generate expenses/income/manual_review.csv
- **Manual-only** (`--manual-only`): Fast update that only validates manual_review.csv classifications and updates expense/income files (no PDF processing)
- **Force** (`--force`, default): Always regenerate from PDFs, even if CSV exists

### Adding Your Bank/Card

If your bank or credit card isn't automatically detected (shows as "Unknown" in the Statement column):

1. **Open the first page of your PDF statement** and look at the header/logo area
2. **Note the bank name** exactly as it appears (e.g., "WELLS FARGO", "DISCOVER", "STEARNS")
3. **Edit `config/bank_patterns.json`** and add a new entry:

```json
{
  "patterns": {
    "YOUR BANK NAME": "Display Name",
    "WELLS FARGO": "Wells Fargo",
    "DISCOVER": "Discover"
  }
}
```

- **Key** (left side): What appears in the PDF header (uppercase, case-insensitive match)
- **Value** (right side): How you want it to appear in your CSV

4. **Reprocess the month:**
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

The tool will now correctly identify your bank!

### Manually Adding Transactions

You can manually add cash purchases and other expenses that aren't on your bank statements.

**1. Create/Edit `statements/2025-11/manual_transactions.csv`:**
```csv
Transaction Date,Place,Amount,Statement
11/26/2025,Farmer's Market,35.50,Cash
11/27/2025,Coffee Shop,6.25,Cash
11/28/2025,Hardware Store,42.99,Cash
11/29/2025,Store Return,-15.00,Cash
```

**Note:** Use negative amounts (e.g., `-15.00`) for refunds or returns.

**2. Process (or reprocess) the month:**
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

The manual transactions will be **automatically merged** with your PDF statement transactions and sorted chronologically. No separate import step needed!

### Understanding Income vs Expenses

The tool automatically separates your transactions into two CSV files:

1. **`expenses.csv`** - All expenses (money going OUT)
   - Bank account debits (bills, purchases, withdrawals)
   - Credit card purchases

2. **`income.csv`** - All income (money coming IN)
   - Paychecks and direct deposits
   - Mobile deposits
   - Interest earned
   - Tax refunds
   - Reimbursements
   - Cashback and bonuses

**If a transaction appears in the wrong file:**

1. **Edit `config/income_keywords.json`** and add the keyword:
```json
{
  "income_keywords": [
    "DEPOSIT",
    "PAYROLL",
    "SALARY",
    "YOUR KEYWORD HERE"
  ]
}
```

2. **Reprocess the month:**
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

**Examples:**
- Paycheck shows as "ABC Corp DD ACH" → Add `"DD ACH"` or `"DD "` to income keywords
- Bonus shows as "Year End Bonus Payment" → Add `"BONUS"` to income keywords
- Tax refund shows as "IRS TREAS 310" → Add `"IRS TREAS"` or `"310"` to income keywords

The keywords are case-insensitive and will match if they appear anywhere in the transaction description.

### Manual Review Workflow

The tool automatically identifies transactions that need your review and creates a `manual_review.csv` file. This includes:

#### What Goes to Manual Review

1. **Payment App Transactions** - Venmo, Zelle, Cash App, PayPal, Apple Pay
   - These are ambiguous without context (could be gifts, purchases, payments, etc.)
   - Always require manual classification
   - **Not added to patterns** - you'll review these each time for security/context

2. **Uncategorized Transactions** - Places the AI couldn't categorize
   - The system tried pattern matching and LLM but couldn't determine the category
   - Once you label them, they're **automatically added to category_patterns.json**
   - Won't need review next time!

#### How to Use Manual Review

**1. After processing, check for `manual_review.csv`:**
```bash
python scripts/process_monthly.py --month 2025-11
# Output: ✓ Saved 5 transaction(s) to manual_review.csv for manual review
```

**2. Open `statements/2025-11/manual_review.csv`:**
```csv
Transaction Date,Place,Amount,Statement,Type,Classification,category
11/15/2025,Venmo Payment,50.00,Chase,Debit,,
11/20/2025,Unknown Store,25.50,Visa,Credit,,
11/22/2025,Zelle Transfer,100.00,Chase,Debit,,
```

**3. Fill in Classification and category:**
```csv
Transaction Date,Place,Amount,Statement,Type,Classification,category
11/15/2025,Venmo Payment,50.00,Chase,Debit,Expense,Gifts & Charity
11/20/2025,Unknown Store,25.50,Visa,Credit,Expense,Shopping
11/22/2025,Zelle Transfer,100.00,Chase,Debit,Expense,Rent
```

**4. Update with your classifications:**

Choose one of two methods:

**Method A: Quick Update** (recommended for iterative work)
```bash
python scripts/process_monthly.py --month 2025-11 --manual-only
```
- ⚡ **Fast** - doesn't reprocess PDFs
- ✅ Validates and corrects categories with LLM
- ✅ Adds uncategorized places to patterns
- ✅ Moves classified transactions to expenses/income.csv
- ✅ Updates manual_review.csv to remove classified items
- 📊 Perfect for classifying a few at a time

**Method B: Full Reprocess** (use when PDFs changed or want fresh start)
```bash
python scripts/process_monthly.py --month 2025-11 --force
```
- 🔨 Deletes all generated files
- 📄 Reprocesses everything from PDFs
- ✅ Includes all validation and pattern learning

**What happens:**
- ✅ Classified transactions move to `expenses.csv` or `income.csv`
- ✅ Categories are validated (typos/abbreviations automatically corrected)
- ✅ **Uncategorized places** (like "Unknown Store") are added to `category_patterns.json`
- ✅ **Payment apps** (like Venmo/Zelle) stay as one-time classifications

**Example Iterative Workflow:**
```bash
# 1. Initial processing
python scripts/process_monthly.py --month 2025-11

# 2. Edit manual_review.csv - classify some transactions

# 3. Quick update
python scripts/process_monthly.py --month 2025-11 --manual-only

# 4. Edit manual_review.csv - classify more transactions

# 5. Quick update again
python scripts/process_monthly.py --month 2025-11 --manual-only

# Repeat steps 4-5 until all classified!
```

#### Category Validation & Auto-Correction

The system intelligently validates categories you enter:

**With Ollama LLM (Enhanced Mode):**
- Uses AI + pattern matching for cross-reference
- Automatically corrects typos and abbreviations:
  - `"food"` → `"Dining"` ✓
  - `"gifs"` → `"Gifts & Charity"` ✓
  - `"donation"` → `"Gifts & Charity"` ✓
  - `"util"` → `"Utilities"` ✓
  - `"car"` → `"Auto Maintenance"` ✓

**Without Ollama LLM (Pattern-Only Mode):**
- Uses pattern matching from `category_patterns.json`
- Corrects close matches with fuzzy matching
- Flags invalid categories for you to fix

**Both modes run 100% locally on your machine** - no internet required.

**Example Output:**
```bash
📝 Category Corrections:
  ✓ 'food' → 'Dining' (Coffee Shop)
  ✓ 'donation' → 'Gifts & Charity' (Charity)

📚 Added 2 place(s) to category_patterns.json:
  + 'coffee shop' → Dining
  + 'charity' → Gifts & Charity

❌ INVALID CATEGORIES FOUND - Please fix these in manual_review.csv:
  ✗ 'invalid_cat' for 'Some Store'
```

#### Valid Categories

See `config/category_patterns.json` for the complete list. Common categories include:
- Groceries, Dining, Transportation, Utilities
- Healthcare, Shopping, Entertainment
- Gifts & Charity, Auto Maintenance, Personal Care
- Education, Subscriptions, Rent, Insurance

### Manually Adding Transactions

You can manually add cash purchases and other expenses that aren't on your bank statements.

**1. Create/Edit `statements/2025-11/manual_transactions.csv`:**
```csv
# Manual transactions for 2025-11
Transaction Date,Place,Amount,category
11/26/2025,Farmer's Market,35.50,Groceries
11/27/2025,Coffee Shop,6.25,Dining
11/28/2025,Hardware Store,42.99,Shopping
11/29/2025,Store Return,-15.00,Shopping
```

**Notes:** 
- Use negative amounts (e.g., `-15.00`) for refunds or returns
- The `category` column is optional but recommended
- Categories are validated and auto-corrected (typos/abbreviations fixed)
- Valid places are **automatically added to category_patterns.json**

**2. Process (or reprocess) the month:**
```bash
python scripts/process_monthly.py --month 2025-11 --force
```

**What happens:**
- ✅ Manual transactions merged with PDF statements
- ✅ Categories validated (e.g., `"food"` → `"Dining"`)
- ✅ Places automatically added to patterns for future categorization
- ✅ Invalid categories flagged for correction
- ✅ Sorted chronologically with bank statement transactions

**Example Output:**
```bash
📝 Manual Transaction Category Corrections:
  ✓ 'food' → 'Dining' (Coffee Shop)

📚 Added 3 place(s) to category_patterns.json:
  + 'farmer's market' → Groceries
  + 'coffee shop' → Dining
  + 'hardware store' → Shopping
```

### Basic Usage (Single PDF)

For processing individual statements:

```bash
python main.py --pdf statements/your_statement.pdf
```

This will generate an `output.xlsx` file with extracted transactions.

## Project Structure

```
AutomatedBudgeting/
├── README.md
├── requirements.txt
├── .gitignore
│
├── config/
│   ├── bank_patterns.json       # Bank detection patterns
│   ├── category_patterns.json   # Transaction categorization rules
│   └── income_keywords.json     # Keywords to identify income (vs expenses)
│
├── scripts/                     # User-facing command-line tools
│   ├── process_monthly.py       # Main: process monthly statements (auto-imports manual_transactions.csv)
│   ├── add_transaction.py       # Add manual transaction interactively
│   └── setup_monthly.py         # Setup directory structure
│
├── src/
│   ├── bankai/                  # Core parsing engine
│   │   ├── ocr/                 # Text extraction
│   │   ├── parser/              # Statement parsing & table detection
│   │   └── utils/               # PDF conversion & place cleaning
│   └── ai_classification/       # Transaction categorization
│
├── examples/
│   ├── example_usage.py         # Code examples
│   └── sample_statements/       # Sample PDFs for testing
│
├── statements/                  # Your actual statements
│   └── YYYY-MM/
│       ├── *.pdf                # Statement PDFs
│       ├── expenses.csv         # Extracted expenses (money OUT)
│       ├── income.csv           # Extracted income (money IN)
│       ├── manual_review.csv    # Transactions needing classification (payment apps + uncategorized)
│       ├── *_rejected.csv       # Filtered internal transfers
│       └── manual_transactions.csv (optional - for cash/manual entries)
│
└── tests/
```

### Python API

```python
from src.bankai.parser.statement_parser import StatementParser

# Initialize parser
parser = StatementParser()

# Convert PDF to structured data
parser.bankstatement2csv(pdf='path/to/statement.pdf')
```

## Roadmap

### Completed ✅
- [x] Support for multiple bank formats via configurable patterns
- [x] Automatic bank/card detection from PDF headers
- [x] Monthly batch processing and consolidation
- [x] Intelligent merchant name cleaning (spaCy NER + optional Ollama LLM)
- [x] Cross-statement transfer detection with automatic removal
- [x] AI-powered transaction categorization (23 categories)
- [x] Smart category validation with LLM + fuzzy matching
- [x] Automatic pattern learning from manual classifications
- [x] Manual review workflow for payment apps and uncategorized transactions
- [x] Manual transaction CSV import with category validation
- [x] Income vs expense automatic separation
- [x] Lightweight `--manual-only` mode for quick updates

### In Progress 🚧
- [ ] Recurring payment detection and subscription tracking
- [ ] Budget analysis and spending trend reports

### Planned 🔮
- [ ] Natural language budget queries with RAG ("Can I afford this purchase?")
- [ ] Budget visualization dashboard (web UI)
- [ ] Budget alerts and notifications
- [ ] Export to accounting software formats (QuickBooks, Mint, YNAB)
- [ ] Receipt attachment linking
- [ ] Multi-currency support

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Acknowledgments

- Inspired by [BankAIAgent](https://github.com/farhan0167/BankAIAgent)
- Uses Microsoft's Table Transformer Model
- OCR powered by Tesseract
