# System Architecture

This document describes how all components of Automated Budgeting fit together.

---

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                │
│              Browser at http://localhost:8000               │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│              src/ui/backend/main.py  :8000                  │
│                                                             │
│   • Serves React build as static files                      │
│   • REST API: /api/expenses, /api/process-statements, ...   │
│   • Spawns background jobs for statement processing         │
└──────────────┬──────────────────────────────────────────────┘
               │                          │
               │ reads/writes             │ spawns
               ▼                          ▼
┌──────────────────────┐    ┌────────────────────────────────┐
│   Data Directory     │    │  Statement Processing Pipeline │
│  src/ui/data/        │    │                                │
│  ├─ statements/      │◄───┤  1. PDF Upload (browser)       │
│  │  └─ YYYY-MM/      │    │  2. StatementParser            │
│  │     ├─ *.pdf      │    │     src/statement_parser/      │
│  │     ├─ *.csv      │    │     parser.py                  │
│  │     └─ ...        │    │  3. LLM Merchant Cleaning      │
│  └─ monthly_reports/ │    │     src/statement_parser/      │
│     └─ *.csv         │    │     llm_utils.py               │
└──────────────────────┘    │  4. TransactionCategorizer     │
                            │     src/ai_classification/     │
                            │     categorizer.py             │
                            │  5. Write output CSVs          │
                            └──────────┬─────────────────────┘
                                       │
                                       │ HTTP (localhost:11434)
                                       ▼
                            ┌──────────────────────┐
                            │       Ollama          │
                            │  (runs on host OS)    │
                            │  see llm_models.json  │
                            └──────────────────────┘
```

---

## Data Flow: Statement Processing

```
PDF file
   │
   ▼
pdf_extractor.py (pdfplumber)
   │  raw text
   ▼
parser.py - StatementParser
   │  detects bank, parses date/amount/merchant rows
   ▼
_strip_trailing_state()
   │  removes "City ST" suffixes from raw merchant strings
   ▼
llm_utils.py - clean_merchant_with_ensemble()
   │  Ollama: qwen2.5:14b [+ llama3.1:8b if multi-model]
   │  returns cleaned merchant name + confidence score
   ▼
categorizer.py - TransactionCategorizer
   │  pattern matching → Ollama classification
   │  checks income_keywords, payment_apps, transfer_keywords
   ▼
Output CSV (same folder as PDF)
   │  columns: date, type, merchant, category, amount, label
   ▼
monthly_reports/ aggregate CSV
```

---

## Component Map

### `src/statement_parser/`

| File | Responsibility |
|------|---------------|
| `parser.py` | Core parsing class `StatementParser`; date/amount extraction; bank detection |
| `llm_utils.py` | LLM ensemble for merchant name cleaning; Ollama REST client |
| `pdf_extractor.py` | pdfplumber wrapper; raw text extraction from PDFs |

### `src/ai_classification/`

| File | Responsibility |
|------|---------------|
| `categorizer.py` | `TransactionCategorizer`; maps merchants to categories via patterns + LLM |

### `src/ui/`

| File | Responsibility |
|------|---------------|
| `backend/main.py` | FastAPI app; all `/api/` endpoints; serves React static build |
| `src/App.js` | React root; tab navigation |
| `src/TransactionsTab.js` | All Transactions and review table |

### `scripts/`

| File | Responsibility |
|------|---------------|
| `process_monthly.py` | CLI entry point for batch processing a month |
| `setup_monthly.py` | First-run setup helper |
| `aggregate_monthly.py` | Aggregates parsed CSVs into monthly summary reports |
| `launch_dashboard.sh` | Convenience script to start the dashboard |

---

## Data Directory Structure

```
src/ui/data/
├── statements/
│   ├── 2025-01/
│   │   ├── bank_checking_jan.pdf     ← uploaded PDF
│   │   ├── bank_checking_jan.csv     ← parsed output
│   │   └── ...
│   ├── 2025-02/
│   └── ...
└── monthly_reports/
    ├── expenses_2025-01.csv          ← aggregated month report
    ├── expenses_2025-02.csv
    └── ...
```

The React dashboard reads from this data directory. Any CSV written here by the parser immediately becomes available in the UI (after page refresh or next data fetch).

---

## Networking

### Docker Mode

```
Host OS
 ├─ Browser        → http://localhost:8000
 ├─ Ollama         → http://localhost:11434  (host service)
 └─ Docker container (network_mode: host)
      └─ FastAPI   → binds 0.0.0.0:8000
           └─ sends LLM requests to localhost:11434 (same host)
```

Using `network_mode: host` in Docker means the container shares the host's network stack. This is required so that the container can reach Ollama running on the host without extra configuration.

### Local Dev Mode (no Docker)
Same ports, no container. Both FastAPI (port 8000) and React dev server (port 3000) run directly on the host. React dev server proxies `/api/` calls to port 8000.

---

## Authentication

By default, the API has no authentication. If deploying in a shared environment, set the `AUTOBUDGET_API_KEY` environment variable. When set, all write endpoints (`POST`, `PUT`, `DELETE`) require the header:

```
X-API-Key: your-key-here
```

Read endpoints remain unauthenticated.

---

## Concurrency Model

Statement processing is CPU and I/O heavy. When triggered from the UI, FastAPI runs the job in a background thread and returns a `job_id` immediately. The client polls `/api/jobs/{job_id}` to check status.

```
POST /api/process-statements
   │  returns { "job_id": "abc123", "status": "running" }
   │
   ▼ (background thread)
StatementParser.parse() + categorizer.categorize()
   │
   ▼
job state → "completed" or "failed"

GET /api/jobs/abc123
   │  returns { "status": "completed", "result": {...} }
```
