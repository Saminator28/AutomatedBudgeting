# Dashboard & Web API

**Frontend:** React (`src/ui/src/`)  
**Backend:** FastAPI (`src/ui/backend/main.py`)  
**URL:** `http://localhost:8000`

---

## Dashboard Tabs

### Overview Tab

The landing page showing a snapshot of the selected month's finances:

- **Income vs. Expenses** — bar chart comparison
- **Spending by Category** — interactive pie chart; click a slice to filter the transaction list
- **Month-over-month trend** — line chart showing expense history across recent months
- **Summary cards** — total income, total expenses, net savings; **avg monthly income** uses the same last-12-months window as the income vs expenses chart

Use the month selector at the top to switch between months.

---

### All Transactions Tab

A full, searchable, sortable table of every transaction for the selected month.

| Column | Description |
|--------|-------------|
| Date | Transaction date |
| Type | DEBIT or CREDIT |
| Merchant | Cleaned merchant name (editable inline) |
| Category | Assigned category (editable via dropdown) |
| Amount | Dollar amount (editable inline for expense rows) |
| Label | expense / income / transfer |

**Features:**
- **Inline editing** — click any expense **Merchant**, **Amount**, or **Category** cell to edit it; changes save to CSV automatically
- **Sort** — click any column header to sort ascending/descending
- **Search / filter** — type in the search box to filter by merchant or category
- **Needs Review section** — transactions flagged for manual attention appear at the top with an amber highlight

---

### Budget Tab

Set monthly spending limits per category and track progress:

- Each category shows a progress bar (spent vs. limit)
- Green when under 80% of limit, yellow at 80–100%, red when over
- Edit limits directly in the tab; limits persist to `config/budget_limits.json`

---

### Investments Tab

Displays transactions categorized as `Investments` separately from regular expenses:

- Contributions to brokerage accounts, retirement accounts, etc.
- Excluded from the main expense total so they don't inflate your "spending"

**Handling individual investment transactions:**

If you have a transaction that should be treated as an investment (e.g., a brokerage transfer, 401k contribution, or stock purchase from your bank statement), categorize it as `Investments` in the All Transactions tab. Once categorized, it automatically moves to the Investments tab and is excluded from your monthly expense totals.

For one-off transactions that are not recurring (e.g., a single stock purchase or a bonus deposited to a brokerage):
1. Find the transaction in the **All Transactions** tab
2. Set the **Category** to `Investments`
3. Optionally set the **Label** to `one-time` if it won't repeat

If the transaction appears as income (e.g., a dividend or capital gain deposited to your account), click the type badge (💵 Income) to cycle it or leave it as income — income transactions do not count against your expense budget regardless of category.

---

### Statements Tab

Upload and process PDF bank statements:

1. Select the target month from the dropdown (or create a new month)
2. Click **Upload Statement** and choose PDF file(s)
3. Click **Process Statements** to start parsing
4. Progress indicator shows parsing, merchant cleaning, and categorization stages
5. Once complete, transactions appear in the All Transactions tab

You can upload multiple PDFs for the same month (e.g., checking account + credit card). The parser processes each independently and merges results.

---

## FastAPI Backend

The backend (`src/ui/backend/main.py`) serves two roles:
1. **REST API** — all `/api/` endpoints for data read/write
2. **Static file server** — serves the pre-built React app for all other routes

### Key API Endpoints

#### Read Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/available-months` | List months that have processed data |
| `GET` | `/api/expenses` | All expense transactions for a month |
| `GET` | `/api/income-entries` | All income transactions for a month |
| `GET` | `/api/expense-categories` | Aggregated totals by category |
| `GET` | `/api/manual-transactions` | Manually entered transactions |
| `GET` | `/api/jobs/{job_id}` | Status of a background processing job |

Query parameters used by most read endpoints: `?month=2025-06`

#### Write Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload-statement` | Upload a PDF file |
| `POST` | `/api/process-statements` | Start background parsing job |
| `PUT` | `/api/update-transaction` | Edit merchant name or category |
| `PATCH` | `/api/expense/edit` | Edit merchant name, category, or amount for an expense row |
| `POST` | `/api/manual-transactions` | Add a manual transaction entry |
| `DELETE` | `/api/manual-transactions/{id}` | Remove a manual transaction |

#### Interactive API Docs

When the application is running, visit:
```
http://localhost:8000/docs
```
for the full Swagger UI with all endpoints, parameters, and response schemas.

---

## Data Store

All data is persisted in a SQLite database at `src/ui/data/budget.db`. The API reads and writes exclusively through the database — there are no CSV data files read back by the backend at runtime.

```
src/ui/data/
├── statements/
│   └── YYYY-MM/
│       ├── *.pdf          ← uploaded PDFs
│       └── *.csv          ← parsed statement CSVs (retained as source records)
└── budget.db              ← sole authoritative data store (transactions, merchant metadata, transfers)
```

---

## Authentication

By default, the API is open — no credentials required. This is appropriate for local use.

For shared or networked deployments, set the environment variable:

```bash
# Linux / macOS
export AUTOBUDGET_API_KEY="your-secret-key"

# Windows
set AUTOBUDGET_API_KEY=your-secret-key
```

When set, all write endpoints require the HTTP header:
```
X-API-Key: your-secret-key
```

Read endpoints remain public.

---

## Background Job System

Statement processing is slow (seconds to minutes depending on PDF size and LLM speed). The API handles this asynchronously:

1. `POST /api/process-statements` — starts a job, returns `{ "job_id": "...", "status": "running" }`
2. The dashboard polls `GET /api/jobs/{job_id}` every few seconds
3. When status changes to `"completed"`, the dashboard refreshes the transaction list

Job state is held in memory; restarting the server clears all job history (completed jobs are not persisted to the DB, but the output transactions remain in `budget.db`).

---

## React Frontend

The React app (`src/ui/src/`) is a single-page application built with Create React App.

**Key source files:**

| File | Purpose |
|------|---------|
| `App.js` | Root component; tab navigation; month selector |
| `TransactionsTab.js` | All Transactions and Review tables |
| `OverviewTab.js` | Charts and summary cards |
| `BudgetTab.js` | Budget limits and progress bars |
| `InvestmentsTab.js` | Investment transaction list |
| `StatementsTab.js` | Upload UI and processing status |

### Building the Frontend

In production (Docker), the React app is built once during the Docker image build:

```dockerfile
RUN npm run build
```

The build output is placed in `src/ui/build/` and served by FastAPI's `StaticFiles` mount.

For local development with live reload, see the [Developer Guide](DEVELOPER_GUIDE.md#6-start-the-react-frontend-development-mode).

---

## Docker Details

The application runs as a single Docker container with:
- `network_mode: host` — shares the host network so the container can reach Ollama at `localhost:11434`
- Volume mount: `./src/ui/data:/app/src/ui/data` — data directory is persisted on the host
- Port: `8000` (both inside and outside the container are identical due to host networking)

**Start:**
```bash
docker compose up --build -d
```

**Stop:**
```bash
docker compose down
```

**View logs:**
```bash
docker compose logs -f
```
