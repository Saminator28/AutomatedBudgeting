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
├── config/                     # Checked-in runtime configuration
│   └── llm_models.json         # Ollama model selection
├── scripts/                    # CLI scripts and utilities
│   ├── process_monthly.py      # Main CLI entry point — processes PDFs and writes to DB
│   ├── setup_monthly.py        # First-time setup helper
│   └── aggregate_monthly.py    # Re-classifies all DB transactions and writes results back
├── src/
│   ├── database/               # DB schema, session, and utilities
│   │   ├── models.py           # SQLAlchemy table definitions
│   │   ├── session.py          # Engine and init_db()
│   │   └── db_utils.py         # Hash utilities, seed functions, DataFrame writers
│   ├── statement_parser/       # PDF parsing pipeline
│   │   ├── parser.py           # StatementParser class
│   │   ├── llm_utils.py        # LLM merchant cleaning
│   │   └── pdf_extractor.py    # pdfplumber wrapper
│   ├── ai_classification/      # Transaction categorization
│   │   └── categorizer.py      # TransactionCategorizer class
│   └── ui/
│       ├── backend/
│       │   └── main.py         # FastAPI server
│       ├── src/                # React source files
│       │   ├── App.js
│       │   ├── TransactionsTab.js
│       │   └── ...
│       └── public/
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
ollama serve                 # if not already running as a service
ollama pull gemma4:31b       # or whichever model is set in config/llm_models.json
```

Check `config/llm_models.json` for the current `primary_model` setting. Browse available models at [https://ollama.com/search](https://ollama.com/search). Larger models (e.g. `qwen2.5:32b`) produce cleaner merchant names but require more RAM. Update `config/llm_models.json` after pulling a different model.

> **Docker mode:** The container entrypoint auto-pulls any configured model that is not already present — no manual pull needed.

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
5. Write transactions directly to `budget.db` via `write_month_to_db`
6. Write a reference copy of parsed rows to `statements/YYYY-MM/` (not read back by the API)

### Other useful scripts

```bash
# Re-classify all existing DB transactions and update categories in place
python scripts/aggregate_monthly.py
```

---

## Configuration Files

### `config/llm_models.json`
Controls which Ollama model(s) are used.

```json
{
  "primary_model": "qwen3.5:9b",
  "secondary_model": "",
  "financial_analysis_model": "ALIENTELLIGENCE/financialadvisor"
}
```

Set `secondary_model` to a non-empty model name to enable ensemble merchant cleaning. Set to `""` to use only the primary model.

### Live DB-backed settings
Categories, keyword lists, merchant rules, auto-filters, and budget settings are stored in SQLite tables, not in checked-in JSON files.

Main tables:
- `config_categories` — category names and parent/child hierarchy
- `investment_keywords`, `income_keywords`, `ignore_keywords`, `payment_app_keywords`, `transfer_keywords` — editable keyword lists
- `merchant_rules` — merchant-level force-income, force-expense, or ignore overrides
- `budget_goals`, `budget_settings`, `budget_history`, `budget_goals_monthly` — saved budget state and history

The FastAPI startup path seeds these tables when needed, and the Settings UI edits them live without rebuilding the container.

---

## Adding a New Category

1. Open the Settings tab in the dashboard.
2. Add or rename categories there; this writes to the `config_categories` table.
3. Re-categorize existing transactions if needed, or reprocess statements so new imports use the updated category list.
4. If you are changing startup defaults for brand-new databases, update the category seed logic in `src/database/db_utils.py`.

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
