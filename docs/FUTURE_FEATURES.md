# Future Features & Roadmap

---

## Recently Completed ✅

### Dashboard UI (2025)
- Interactive web dashboard (React + FastAPI)
- Expense pie chart with category filtering
- Month-over-month trend line charts
- Income vs. expense comparison chart
- Manual transaction entry via UI
- Inline editing of merchant names and categories
- Investment tab for tracking investment transactions
- Statement upload and processing via UI

### Data Consolidation (2026)
- Unified data directory: all PDFs, CSVs, and reports under `src/ui/data/`
- Single Docker volume mount
- Statements and monthly reports co-located by month

### Parser & Classification
- pdfplumber-based text extraction (replacing Table Transformer approach)
- Multi-model LLM ensemble for merchant name cleaning
- CR suffix detection for credit card returns/reimbursements
- Cross-statement transfer detection
- CSV learning system: loads merchant history from processed CSVs
- Frequency-based confidence scoring for merchant cache
- State/province abbreviation stripping before LLM
- Payment app detection and manual review routing

### AI Chatbot Assistant
- RAG-based budget Q&A (`src/ai_analysis/chatbot_assistant.py`)
- Answers natural-language questions about spending patterns

---

## Planned Features

### 1. Recurring Transaction Detection
**Priority:** High  
**Complexity:** Medium

Automatically detect subscriptions and recurring payments.

- Identify transactions that appear on roughly the same date each month
- Flag subscription services (Netflix, Spotify, gym memberships, etc.)
- Show a "Subscriptions" view in the dashboard
- Alert when a subscription amount changes (price increase detection)
- Calculate annual cost of all subscriptions

**Implementation notes:**
- Group transactions by merchant + approximate amount
- Use date clustering to identify monthly/annual recurrence
- Add a `recurring` flag to the expenses CSV
- Surface in dashboard as a dedicated "Subscriptions" widget

---

### 2. Budget Limits & Alerts
**Priority:** High  
**Complexity:** Low–Medium

Let users set per-category budget limits and get notified when approaching them.

- Set monthly limits per category (e.g., Dining: $300/month)
- Visual indicator in dashboard when >80% of limit reached
- Alert badge/toast when limit is exceeded
- Optional: email or system notification
- Budget configuration stored in `config/budget_limits.json`

---

### 3. AI Budget Q&A Improvements
**Priority:** Medium  
**Complexity:** Medium

Expand the existing chatbot assistant (`src/ai_analysis/chatbot_assistant.py`):

- Integrate into the dashboard UI as a sidebar chat panel
- Add context about current month's budget limits
- Answer questions like:
  - "Can I afford a $500 TV this month?"
  - "What's my average monthly dining expense?"
  - "Which category am I overspending in?"
  - "How does this month compare to last month?"
- Improve response accuracy with better context chunking

---

### 4. Merchant Name Improvements

#### 4a. Difficult Merchants Config
Allow users to pre-define patterns for consistently challenging merchant names:

```json
// config/difficult_merchants.json
{
  "patterns": {
    "BP#*": "BP Gas",
    "SQSP* INV*": "Squarespace",
    "WL*STEAM*": "Steam"
  }
}
```

#### 4b. Time-Based Cache Weighting
Weight recent months more heavily than older months:
- Last 3 months: 100% weight
- 4–6 months ago: 75% weight
- 7–12 months ago: 50% weight
- 13+ months ago: 25% weight

Benefit: adapts when a familiar merchant closes and a new one takes its place.

#### 4c. Fuzzy Merchant Matching
Use fuzzy string matching (Levenshtein distance) for cache lookups:
- Input: `"WALMART SUPERCTR #1234"` → fuzzy matches `"Walmart"` (edit distance < threshold)
- Reduces LLM calls for known merchants with minor variations

---

### 5. Multi-Bank Statement Merging
**Priority:** Medium  
**Complexity:** Medium

When multiple statements are uploaded for the same month, automatically detect and remove cross-account transfers so they don't appear as both income and expense.

Current state: basic transfer keyword detection exists.  
Improvement: amount + date matching across statements to catch transfers not caught by keywords.

---

### 6. Monthly Report CSV Export
**Priority:** Medium  
**Complexity:** Low

Allow users to export any processed month as a standalone CSV directly from the dashboard.

- Select a month (e.g. January 2025) and click **Export CSV**
- Exported file contains the columns: `Date`, `Type`, `Merchant`, `Amount`, `Category`, `Source`
  - `Type` — `expense`, `income`, or `transfer`
  - `Source` — the originating statement filename (e.g. `chase_jan2025.pdf`)
- Export includes all transaction types for the month (expenses, income, transfers)
- Option to filter by type before exporting (e.g. expenses only)
- Backend endpoint: `GET /api/export/monthly?month=2025-01`
- Filename format: `budget_export_2025-01.csv`

**Implementation notes:**
- Read from the existing `monthly_reports/` CSVs (or DB once migrated)
- Use FastAPI's `StreamingResponse` with `text/csv` content type to return the file
- Add an Export button to the dashboard's month selector toolbar

---

### 7. Data Encryption at Rest
**Priority:** Medium  
**Complexity:** Medium–High

Encrypt sensitive financial data stored on disk to protect against unauthorized access.

**Scope:**
- Uploaded statement PDFs (`src/ui/data/statements/*/`)
- Processed transaction CSVs (expenses, income, transfers, manual review)
- Monthly report CSVs (`monthly_reports/`)
- Merchant history cache

**Proposed approach:**
- Use AES-256 encryption (via Python's `cryptography` library — `Fernet` symmetric key)
- User sets a passphrase on first launch; a derived key (PBKDF2 or Argon2) is used to encrypt/decrypt files
- The key is held in memory only — never written to disk
- Docker volume data remains encrypted at rest; decrypted in-memory only when needed
- Files are re-encrypted after every write

**Considerations:**
- Passphrase prompt could be integrated into the dashboard startup screen
- Without the passphrase, the Docker volume contents are unreadable even if the host machine is accessed
- Adds complexity to the processing pipeline — all file reads/writes go through an encrypt/decrypt wrapper
- Key rotation would require re-encrypting all stored files

---

### 8. Export to Financial Software
**Priority:** Low  
**Complexity:** Medium

Export processed transactions to popular formats:

- **YNAB** (You Need A Budget) — `.csv` in YNAB import format
- **QuickBooks** — IIF or CSV format
- **Mint** — CSV export compatible
- **OFX/QFX** — universal bank format

---

### 9. Mobile-Friendly Dashboard
**Priority:** Medium  
**Complexity:** Low–Medium

The current React UI works on desktop. Responsive design improvements for phone/tablet:
- Touch-friendly transaction editing
- Swipe gestures on the pie chart
- Compact table view for small screens

---

### 10. Multi-Currency Support
**Priority:** Low  
**Complexity:** Low–Medium

Handle statements that include foreign currency transactions:
- Detect currency symbols and codes (€, £, ¥, CAD, etc.)
- Store original currency alongside USD value
- Show exchange rate used on transaction date (using free historical API like Open Exchange Rates)

---

### 11. Receipt Attachment Linking
**Priority:** Low  
**Complexity:** Medium

Allow users to attach receipt images or PDFs to individual transactions:
- Upload receipt via dashboard
- Store in `src/ui/data/statements/YYYY-MM/receipts/`
- Link receipt to transaction by date + amount
- View receipt from transaction detail panel

---

### 12. Performance: Parallel LLM Processing
**Priority:** Low  
**Complexity:** Medium

Currently, transactions are processed one at a time through the LLM. Processing in parallel batches would significantly reduce first-run time for large statements.

- Use `asyncio` + async Ollama client for concurrent requests
- Configurable batch size (default: 5 concurrent)
- Expected improvement: 50–70% reduction in processing time

---

### 13. Smart Cache Preloading
**Priority:** Low  
**Complexity:** Low

Bundle a `config/common_merchants.json` with the top 500 national merchants already pre-cleaned:
- Walmart, Target, Costco, Amazon, etc.
- Gas stations (Shell, BP, Chevron, Exxon, etc.)
- Fast food chains
- Streaming services

Benefit: instant recognition for common merchants on first run, before any CSV history exists.

---

### 14. PDF Preview Panel
**Priority:** Medium  
**Complexity:** Low–Medium

Display the original statement PDF alongside parsed transactions so users can spot-check extraction accuracy directly in the dashboard.

- Upload flow opens a split view: PDF viewer on the left, parsed transaction table on the right
- Clicking a transaction row highlights the corresponding line in the PDF (where page/position metadata is available)
- Helps users catch parser errors without hunting for the original file
- PDF rendered using a lightweight viewer (e.g. `react-pdf`)
- Stored PDFs already exist in `src/ui/data/statements/YYYY-MM/` — no new storage needed

---

### 15. Financial Goals Tracking
**Priority:** Medium  
**Complexity:** Medium

Allow users to define savings or spending targets and track progress against real transaction data.

- Create goals such as "Save $5,000 by June 2026" or "Keep Dining under $200/month"
- Dashboard widget shows progress bar: amount saved or remaining vs. target
- Goals stored in `config/goals.json`
- Two goal types:
  - **Savings goal** — tracks cumulative surplus (income − expenses) toward a target amount
  - **Spending cap** — tracks a category's monthly spend against a ceiling (overlaps with Budget Limits feature — can be unified)
- Automatically updates each time a month is processed

---

### 16. Chatbot Session History
**Priority:** Medium  
**Complexity:** Low

Persist chatbot conversations so users can return to a previous analysis session.

- Each session saved as a JSON file under `src/ui/data/chat_sessions/YYYY-MM-DD_HH-MM.json`
- Session list shown in a sidebar with timestamps and auto-generated titles (based on first message)
- Users can rename, delete, or resume any session
- On resume, full message history is reloaded into the chat context
- Sessions are scoped to the local machine — no cloud sync

---

### 17. Debt Payoff Tracker
**Priority:** Low  
**Complexity:** Medium

Track outstanding loans and credit balances and project payoff timelines based on monthly income surplus.

- User enters: debt name, current balance, interest rate (APR), minimum payment
- Dashboard shows:
  - Current balance and projected payoff date at minimum payment
  - How much faster payoff would be with extra monthly contribution
  - Total interest paid over the life of the debt
- Multiple debts supported; ranked by highest-interest-first (avalanche) or lowest-balance-first (snowball)
- Debt config stored in `config/debts.json`
- Integrates with monthly income surplus calculated from processed statements

---

## Technical Debt

### High Priority
- **Migrate transaction storage from CSV to a database**  
  Currently all transaction data is stored in flat CSV files under `src/ui/data/statements/` and `src/ui/data/monthly_reports/`. This approach has several pain points:
  - Concurrent read/write is fragile (no atomic transactions, race conditions during `classify_manual_review`)
  - Category corrections and user flags (`user_corrected`) require re-reading and rewriting entire files
  - Merchant history is rebuilt from scratch on every aggregate run by scanning all CSVs
  - No indexing, so queries (e.g. "all transactions for merchant X") require full scans

  **Recommended approach:** SQLite (via SQLAlchemy) — single-file, no separate server, zero-config, and accessible from both the FastAPI backend and the processing scripts. Schema would be roughly:
  - `transactions` table: `id`, `month`, `type` (expense/income/transfer), `date`, `place`, `amount`, `category`, `label`, `statement`, `user_corrected`, `created_at`
  - `merchant_metadata` table: `merchant_key`, `display_name`, `category`, `tags` (JSON array), `user_corrected`, `updated_at`
  - Migration script to import existing CSVs on first run, seeding `merchant_metadata` from monthly report history

  The CSV files could be kept as export artifacts for compatibility, generated on demand rather than used as the primary store.

  **How this directly resolves the `_INVESTMENT_PLATFORM_KEYWORDS` hardcoding problem:**

  The keyword list exists to bootstrap investment detection: income from platforms like Cash App or Robinhood has no category when it first arrives, so we can't detect it by category alone. We use name matching as a stand-in. The DB removes the need for that stand-in entirely:

  - The hardcoded keyword list becomes the **one-time seed** for `merchant_metadata` — on migration, any merchant matching a keyword gets `tags = ["investment_platform"]` written to the DB.
  - From that point, the detection logic changes from `if any(kw in place for kw in HARDCODED_LIST)` to `if merchant_metadata.get(place).has_tag("investment_platform")`.
  - When the user sets a new income source as "Investment Return" via the UI, `/api/income/categorize` writes `tags = ["investment_platform"]` to `merchant_metadata` for that merchant key — **permanently and automatically**. No list to maintain.
  - The chicken-and-egg problem (category doesn't exist yet → can't detect by category) is solved because the DB tag is set once at classification time and persists. The next time that merchant appears in any future statement, it is immediately routed to transfers without any keyword matching or manual step.
  - The duplicate constant in `main.py` and `aggregate_monthly.py` both disappear — both query `merchant_metadata` from the same DB instead.

- Unit tests for `StatementParser` (`src/statement_parser/parser.py`)
- Unit tests for `TransactionCategorizer` (`src/ai_classification/categorizer.py`)
- Integration tests for full PDF → dashboard workflow

### Medium Priority
- **Move `_INVESTMENT_PLATFORM_KEYWORDS` to `config/investment_platforms.json`**  
  The list of investment platform name keywords (`robinhood`, `cash app`, `vanguard`, etc.) is currently hardcoded in two places: `src/ui/backend/main.py` and `scripts/aggregate_monthly.py`. The list is used to auto-detect income rows that should appear as Direction=In in the Investments tab without manual tagging.

  **Proposed change:**
  - Create `config/investment_platforms.json`: `{ "keywords": ["robinhood", "cash app", ...] }`
  - Both `main.py` and `aggregate_monthly.py` load the list at startup from `_CONFIG_ROOT`
  - Remove the duplicate constant from both files
  - Longer term: replace keyword matching entirely with a category-driven approach once `Investment Return` is reliably auto-assigned (see database migration item above)

- Type hints throughout `process_monthly.py` (currently partially typed)
- Centralize Ollama host configuration (currently spread across multiple files)
- Replace hardcoded debug keyword filters in `classify_transactions` with a proper debug flag

### Low Priority
- CI/CD pipeline (GitHub Actions: run tests on push)
- Docker image size reduction (multi-stage build to exclude dev dependencies)
- API rate limiting / authentication for production deployments

---

## Ideas Under Consideration

These don't have a clear implementation plan yet but have been requested:

- **Spending prediction** — ML model to forecast next month's spend by category based on history
- **Tax categorization** — tag transactions as potentially tax-deductible (home office, business meals, etc.)
- **Shared expense splitting** — handle joint accounts and split expenses between people
- **Net worth tracking** — include investment account balances alongside spending data
- **Dark mode** — for the dashboard UI
