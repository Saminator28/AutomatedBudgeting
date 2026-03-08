# Developer Guide

This guide is for developers who want to run the application locally without Docker, contribute code, or understand the development setup.

For end-user setup, see the main [README](../README.md).

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Backend and parser |
| Node.js | 18+ | React frontend |
| npm | 9+ | JS dependencies |
| Ollama | Latest | LLM inference (merchant cleaning + categorization) |
| pdfplumber | via pip | PDF text extraction |
| tessaract-ocr | system package | OCR fallback for scanned PDFs |

---

## Project Layout

```
AutomatedBudgeting/
├── config/                     # All user-editable config files
│   ├── categories.json         # Category list for classification
│   ├── income_keywords.json    # Keywords that flag income
│   ├── payment_apps.json       # Venmo/Zelle/etc. detection
│   ├── transfer_keywords.json  # Inter-account transfer detection
│   ├── ignore_transactions.json # Transactions to always skip
│   └── llm_models.json         # Ollama model selection
├── scripts/                    # CLI scripts and utilities
│   ├── process_monthly.py      # Main CLI entry point
│   ├── setup_monthly.py        # First-time setup helper
│   └── compare_models.py       # Model benchmarking
├── src/
│   ├── statement_parser/       # PDF parsing pipeline
│   │   ├── parser.py           # StatementParser class
│   │   ├── llm_utils.py        # LLM merchant cleaning
│   │   └── pdf_extractor.py    # pdfplumber wrapper
│   ├── ai_classification/      # Transaction categorization
│   │   └── categorizer.py      # TransactionCategorizer class
│   ├── bankai/                 # OCR-based parser (legacy/experimental)
│   └── ui/
│       ├── backend/
│       │   └── main.py         # FastAPI server
│       ├── src/                # React source files
│       │   ├── App.js
│       │   ├── TransactionsTab.js
│       │   └── ...
│       └── public/
└── statements/                 # (Legacy) Raw statement input directory
```

---

## Local Development Setup (No Docker)

### 1. Create and activate a virtual environment

```bash
# macOS / Linux
python3.12 -m venv myenv
source myenv/bin/activate

# Windows
python -m venv myenv
myenv\Scripts\activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install system dependencies for OCR

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr

# Windows
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
```

### 4. Install curl (required for Ollama installer on Linux)

```bash
# Ubuntu / Debian
sudo apt install curl
```

On macOS curl is pre-installed. On Windows use the [Ollama Windows installer](https://ollama.com/download).

### 5. Start Ollama and pull the model

```bash
ollama serve          # if not already running as a service
ollama pull qwen2.5:14b
```

Browse available models at [https://ollama.com/search](https://ollama.com/search). Larger models (e.g. `qwen2.5:32b`) produce cleaner merchant names but require more RAM. Update `config/llm_models.json` after pulling a different model.

### 6. Start the backend

```bash
source myenv/bin/activate
uvicorn src.ui.backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

### 7. Start the React frontend (development mode)

In a second terminal:

```bash
cd src/ui
npm install
npm start
```

React dev server runs at `http://localhost:3000` and proxies API requests to port 8000.

> **Note:** In production (Docker), React is pre-built and served as static files by FastAPI — there is no separate port 3000.

---

## Running the Statement Processor from CLI

Place PDFs in `src/ui/data/statements/YYYY-MM/` then:

```bash
source myenv/bin/activate
python scripts/process_monthly.py --month 2025-06
```

This will:
1. Find all PDFs in the specified month folder
2. Extract transactions using `StatementParser`
3. Clean merchant names via Ollama
4. Categorize transactions via `TransactionCategorizer`
5. Write output CSVs back to the same folder

### Other useful scripts

```bash
# Test LLM connection
python scripts/test_llm_direct.py

# Compare model accuracy
python scripts/compare_models.py

# Test normalize pipeline
python scripts/test_normalize.py
```

---

## Configuration Files

### `config/llm_models.json`
Controls which Ollama model(s) are used.

```json
{
  "primary_model": "qwen2.5:14b",
  "secondary_model": "llama3.1:8b",
  "use_multi_model": true
}
```

Set `use_multi_model` to `false` to use only the primary model.

### `config/categories.json`
The list of categories used for classification. Add, remove, or rename categories here.

```json
[
  "Groceries",
  "Dining",
  "Transportation",
  "Utilities",
  ...
]
```

### `config/income_keywords.json`
Keywords found in merchant/description fields that indicate income (not an expense). Edit to match your employer's name or side-income sources.

### `config/payment_apps.json`
Lists payment app names (Venmo, Zelle, Cash App, PayPal, etc.). Transactions matching these are flagged for manual review because the real merchant is usually in the note/memo.

### `config/transfer_keywords.json`
Keywords that indicate an inter-account transfer (e.g., "ACH TRANSFER", "ONLINE TRANSFER TO"). These are excluded from expense totals.

### `config/ignore_transactions.json`
Specific transaction strings to completely ignore (e.g., internal account fees that aren't real expenses).

---

## Adding a New Category

1. Open `config/categories.json`
2. Add the new category name to the array
3. Open `config/category_patterns.json`
4. Add keyword patterns that map merchant names to the new category

---

## API Reference

The FastAPI backend exposes REST endpoints under `/api/`. When the server is running, visit:

```
http://localhost:8000/docs
```

for the auto-generated interactive API documentation (Swagger UI).

---

## Running Tests

```bash
source myenv/bin/activate
python -m pytest tests/ -v
```

> **Note:** Test coverage is currently limited. Expanding tests is a [planned improvement](FUTURE_FEATURES.md).

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `AUTOBUDGET_API_KEY` | _(none)_ | Optional API key for write endpoints |
| `DATA_DIR` | `src/ui/data` | Base data directory |
