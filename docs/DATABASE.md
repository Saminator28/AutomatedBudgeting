# Database Interactions

Automated Budgeting uses a single SQLite database (`src/ui/data/budget.db`) as its sole authoritative data store. All API endpoints read from and write to this database. There are no CSV fallbacks.

---

## Schema

### `transactions`

The primary table. One row per transaction.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment row ID |
| `tx_hash` | TEXT UNIQUE | SHA-256 of `report_month\|tx_date\|PLACE\|cents\|tx_type\|statement\|seq` — deduplication key |
| `report_month` | TEXT | Month this transaction belongs to (`YYYY-MM`) |
| `tx_type` | TEXT | `expense` or `income` |
| `tx_date` | TEXT | Transaction date (`MM/DD/YYYY`) |
| `place` | TEXT | Cleaned merchant name |
| `amount` | REAL | Transaction amount (positive for expenses and income; negative for reimbursements) |
| `category` | TEXT | Assigned category |
| `label` | TEXT | Sub-label: `recurring`, `one-time`, `bonus`, or `reimbursement` |
| `statement` | TEXT | Source statement filename |
| `user_corrected` | INTEGER | `1` if a user manually corrected this row; `0` otherwise |

#### `tx_hash` derivation

```python
amount_cents = int(round(amount * 100))
raw = f"{report_month}|{tx_date}|{PLACE_UPPER}|{amount_cents}|{tx_type}|{statement}|{seq}"
tx_hash = hashlib.sha256(raw.encode()).hexdigest()[:24]
```

`seq` handles genuinely duplicate rows (same merchant, same amount, same day on the same statement). `INSERT OR IGNORE` is used on import so re-processing the same PDF never creates duplicates.

---

### `transfers`

Investment and account-transfer rows. Rebuilt from `statements/*/transfers.csv` plus investment-tagged rows in `transactions` whenever a statement month is imported or an investment category is updated.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment row ID |
| `tx_hash` | TEXT UNIQUE | Stable hash (same derivation as `transactions`) |
| `report_month` | TEXT | Month (`YYYY-MM`) |
| `tx_date` | TEXT | Transaction date |
| `place` | TEXT | Merchant / brokerage name |
| `amount` | REAL | Transfer amount (always positive) |
| `direction` | TEXT | `In` (investment return / deposit) or `Out` (investment purchase) |
| `statement` | TEXT | Source statement filename |
| `label` | TEXT | `Retirement`, `Personal`, or `null` (user-set via the Investments tab) |

---

### `merchant_metadata`

Per-merchant learned data. Updated whenever the LLM cleans a new raw merchant string.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment row ID |
| `merchant_key` | TEXT UNIQUE | Normalised key (lower-case, punctuation stripped, numbers removed) |
| `is_investment_platform` | BOOLEAN | `True` if this merchant is an investment platform |
| `tags` | TEXT | JSON array of free-form strings (reserved for future use) |
| `user_corrected` | BOOLEAN | `True` if a user manually updated this record |

---

### Keyword tables

All keyword lists that were previously stored as JSON config files are now stored in the DB so they can be edited live from the UI without a container restart.

| Table | Replaces | Purpose |
|-------|----------|---------|
| `investment_keywords` | `config/investment_platforms.json` | Detect investment-platform transactions |
| `income_keywords` | `config/income_keywords.json` | Detect incoming credits (payroll, deposits) |
| `ignore_keywords` | `config/ignore_transactions.json` | Silently drop matching transactions |
| `payment_app_keywords` | `config/payment_apps.json` | Flag peer-to-peer payment app transactions for manual review |
| `transfer_keywords` | `config/transfer_keywords.json` | Exclude inter-account transfers from totals |

Each table has `id` (INTEGER PK) and `keyword` (TEXT UNIQUE).

On first startup, the application is responsible for ensuring these tables are populated with an initial keyword set (if desired). The exact seeding mechanism is implementation-defined and may change over time; consult the current application configuration or release notes for details. New installations can also be initialized manually via the UI or SQL migrations.

---

### `institution_cache`

Maps a stable statement header fingerprint to the institution name so the same account always gets the same name across months.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment row ID |
| `header_fp` | TEXT UNIQUE | Short hash of the statement header block |
| `institution_name` | TEXT | Resolved institution name |

---

## Write Flows

### 1. Statement Processing (`process_monthly.py` / `/api/process-statements`)

When a PDF is uploaded and processed:

1. `StatementParser` extracts raw rows from the PDF.
2. `llm_utils.py` cleans merchant names (LLM ensemble + cache).
3. `categorizer.py` assigns categories.
4. `write_month_to_db(engine, month, expenses_df, income_df)` in `src/database/db_utils.py` writes rows into `transactions`.
   - Existing non-user-corrected rows for the month are replaced.
   - Rows with `user_corrected = 1` have their `category`, `label`, and `place` restored after the wipe.
5. `_rebuild_transfers_for_month(month)` re-runs after each import and rewrites the `transfers` table for that month.
6. The source CSV is written to `statements/YYYY-MM/` as a reference copy but is not read back by the API.

### 2. Re-aggregation (`aggregate_monthly.py`)

Reads all transactions for each month from the `transactions` table, re-applies classification and labelling, and writes the results back with `write_month_to_db`. No CSV I/O.

### 3. User Edits (API write endpoints)

| Endpoint | DB operation |
|----------|-------------|
| `PATCH /api/expense/edit` | `UPDATE transactions SET place=?, category=?, amount=? ... user_corrected=1` |
| `POST /api/expense/label` | `UPDATE transactions SET label=? ... user_corrected=1` |
| `POST /api/income/label` | `UPDATE transactions SET label=? ... user_corrected=1` |
| `POST /api/manual-transactions` | `INSERT INTO transactions ... statement='Manual'` |
| `DELETE /api/manual-transactions/{id}` | `DELETE FROM transactions WHERE tx_hash=?` |
| `DELETE /api/statements/{month}` | `DELETE FROM transactions WHERE report_month=?` + `DELETE FROM transfers WHERE report_month=?` |

Setting `user_corrected = 1` ensures the next re-import of the same statement preserves the user's changes.

---

## Read Flows

All API read endpoints use the `_query_df(tx_type, months=None)` helper in `main.py`:

```python
def _query_df(tx_type: str, months: list[str] | None = None) -> pd.DataFrame:
    """Read transactions from DB, optionally filtered by month(s)."""
    ...
```

If the DB is unavailable, endpoints return an empty result or an HTTP error — there is no CSV fallback.

Key read endpoints:

| Endpoint | Query |
|----------|-------|
| `GET /api/all-expenses` | `SELECT ... FROM transactions WHERE tx_type='expense'` |
| `GET /api/income-entries` | `SELECT ... FROM transactions WHERE tx_type='income'` |
| `GET /api/expense-categories` | Aggregates expense amounts by category for a month |
| `GET /api/expenses-by-month` | Per-category totals for every available month (trend chart) |
| `GET /api/available-months` | `SELECT DISTINCT report_month FROM transactions ORDER BY report_month DESC` |
| `GET /api/transfers` | `SELECT ... FROM transfers ORDER BY report_month, tx_date` |

---

## `user_corrected` Flag Semantics

The `user_corrected` flag on `transactions` rows controls whether the pipeline may overwrite a row on re-import:

- **`0` (default):** Row may be updated when the same statement PDF is reprocessed.
- **`1`:** Row was manually edited by the user. Re-processing wipes and rewrites all non-corrected rows for the month, then reapplies saved corrections (category, label, place) by matching on `tx_hash`.

This means you can safely re-import a statement PDF to pick up newly parsed rows without losing manual corrections.

---

## Transfer Detection

After every statement import for a month, `_rebuild_transfers_for_month(month)` in `main.py`:

1. Reads raw transfer rows from `statements/*/transfers.csv` for the month.
2. Reads investment expense rows from `transactions` (category = `Investment` or `Investment Transfer`) → `direction = Out`.
3. Reads investment income rows from `transactions` (category = `Investment Return` or place matches an investment keyword) → `direction = In`.
4. Deduplicates and writes all rows to the `transfers` table via `write_transfers_to_db`.

---

## Starting Fresh

Since there is no CSV migration path, the DB starts empty. Import statement PDFs via the web UI — each upload triggers the processing pipeline and populates the DB directly.

If you need to wipe and restart: delete `src/ui/data/budget.db` and restart the application. The schema is recreated automatically on startup.

---

## Schema Changes

No migration tool (e.g. Alembic) is in place. For schema changes, either:
- Add `ALTER TABLE` statements to `session.py:init_db()`, or
- Delete `budget.db` and re-import all statements (data is always reproducible from the source PDFs).
