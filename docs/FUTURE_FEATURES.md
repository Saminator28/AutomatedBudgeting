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
- Hierarchical two-model pipeline: intent/reasoning model (primary_model, e.g. qwen) parses user
  message into structured JSON intent, then a finance advisor model (financial_analysis_model)
  composes the conversational response using pandas-computed facts — no hallucinated numbers
- Stateful conversation context (`ConversationState`) carries period, category, and window across
  follow-up turns without re-querying the intent model
- Regex-based intent fallback when the intent model is unavailable
- **Persistent chat sessions** — conversation history and `ConversationState` stored in
  `chat_sessions` DB table; server-side session cache (`_SESSION_CACHE`) reuses live
  `ChatbotAssistant` instances so no cold-start on every request
- **Hermes memory model** — optional `memory_model` in `config/llm_models.json`; when set,
  long sessions are automatically summarised so context survives beyond the finance advisor's
  context window
- **Batch categorization session** — `categorizer.py` `categorize_batch_with_session()` runs
  an entire batch of merchants through a single persistent Ollama session instead of one call
  per merchant, improving consistency and reducing cold-start overhead

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
- Limits configured in the Dashboard Settings page

---

### 3. AI Budget Q&A Improvements
**Priority:** Medium  
**Complexity:** Medium

Expand the existing chatbot assistant (`src/ai_analysis/chatbot_assistant.py`):

- ~~Add context about current month's budget limits~~ *(ConversationState tracks budget_targets)*
- Answer questions like:
  - "Can I afford a $500 TV this month?"
  - "What's my average monthly dining expense?"
  - "Which category am I overspending in?"
  - "How does this month compare to last month?"
- Improve response accuracy with better context chunking
- ~~Persist conversations across requests~~ *(Done — chat_sessions DB table)*

**Remaining work:**
- Wire budget-limit data from `budget_goals` into the chatbot system prompt so
  the advisor can compare spending against user-set limits
- Add a "Can I afford X?" intent type to the intent parser
- Month-over-month comparison intent type

---

### 4. Merchant Name Improvements

#### 4a. Difficult Merchants Config
Allow users to pre-define patterns for consistently challenging merchant names via a
Merchant Aliases page in Settings:
- Add a pattern (e.g. `BP#*`) and the clean name to display (e.g. `BP Gas`)
- Patterns are previewed live against recent transactions before saving

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

Pre-load a bundled merchant database (seeded into the DB on first run) with the top 500 national merchants already pre-cleaned:
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
- Goals created and managed via the Dashboard Goals tab
- Two goal types:
  - **Savings goal** — tracks cumulative surplus (income − expenses) toward a target amount
  - **Spending cap** — tracks a category's monthly spend against a ceiling (overlaps with Budget Limits feature — can be unified)
- Automatically updates each time a month is processed

---

### 16. Chatbot Session History
**Priority:** Medium  
**Complexity:** Low

~~Persist chatbot conversations so users can return to a previous analysis session.~~

**Status: Core persistence is implemented** — the `chat_sessions` DB table stores every
session.  The session endpoints are live:

| Endpoint | Description |
|----------|-------------|
| `GET /api/chat/sessions` | List all sessions (id, title, timestamps, message count) |
| `GET /api/chat/sessions/{id}` | Full message history for one session |
| `DELETE /api/chat/sessions/{id}` | Delete a session |
| `POST /api/chat` (with `session_id`) | Continue an existing session |

**Remaining UI work:**
- Session sidebar in the chatbot panel: list sessions with timestamps and auto-titles
- Click to resume: load session messages into the chat panel and send `session_id`
  with subsequent messages
- Rename and delete buttons per session row
- "New chat" button that clears `session_id` from the client state

---

### 17. Debt Payoff Tracker
**Priority:** Medium  
**Complexity:** Medium

Track loan and installment debt payments as they appear in bank statements, then project
payoff timelines and total interest. This is how Mint, Rocket Money, and Copilot handle debt
without Plaid — they don't connect to the loan servicer; they watch your checking account for
the recurring payment and work backwards from user-supplied balance + APR.

#### How non-Plaid apps do it
- User enters the debt once: name, current balance, APR, and payment day-of-month
- The app scans existing transactions for a payment matching the merchant keyword on
  roughly that day each month (e.g. "ALLY AUTO" every 15th)
- Each matched payment is recorded; principal vs. interest split is derived from the
  amortization schedule the app calculates internally
- Balance decreases automatically each month as payments are detected
- No access to the loan servicer is ever needed

#### What to implement

**Debts entered via the Dashboard Debts tab:**
- Name, type (auto / personal / student), current balance as of a start date, APR, minimum payment, payment day of month, and a merchant keyword to match against transactions

**Statement payment detection:**
- At `aggregate_monthly.py` time, scan expense transactions for `merchant_keyword` matches
- Auto-tag matched rows with `category='Debt Payment'` and `debt_id` label
- Calculate principal portion: `interest = balance × (apr/12)`, `principal = payment - interest`
- Write a running balance ledger to `src/ui/data/debt_ledger.json`

**Dashboard — new Debts tab:**
- Summary card per debt: current balance, payoff date, total interest remaining
- Amortization bar: months paid vs. months remaining
- Avalanche vs. snowball toggle — shows which debt to overpay and by how much
- "What if I pay $X extra/month?" slider — recomputes payoff date live
- 12-month payment history chart (detected payments from statements)
- If a payment month is missing (no match found), highlight it as a warning

**Payoff strategy integration:**
- Pull monthly surplus from income vs. expense totals already calculated
- Show how much surplus is available to apply to debt extra payments
- Rank debts by avalanche (highest APR first) or snowball (lowest balance first)

**Limitations (by design — no Plaid needed):**
- Balance and APR are user-entered; app does not pull from the loan servicer
- Refinances or rate changes require a manual config update
- Works for fixed-rate installment loans (auto, personal, student); credit card revolving
  balances are harder since the minimum payment changes monthly

---

### 18. Investment Tab — Contribution Tracking & Account Breakdown
**Priority:** Medium  
**Complexity:** Medium

The current Investments tab shows raw cash flows (money out to brokerages, money in from them)
and lets you label transfers as Retirement or Personal. The next step is making those labels
actionable — contribution limit progress, account-level tracking, and a clearer picture of
how investment activity relates to the rest of the budget.

#### 18a. Annual Contribution Limit Progress Bars
Display IRS contribution limits alongside YTD totals for transfers that actually hit a bank
account. **Note:** 401(k) and HSA contributions taken as payroll deductions never appear in
bank statements — they are pre-tax deductions processed by the employer before the paycheck
is deposited, so there is nothing to detect here. What *is* trackable from statements:

- **Roth IRA / Traditional IRA** — manual transfers from checking to IRA custodian
  ($7,000 limit for 2025, $8,000 if age 50+)
- **Personal brokerage** — transfers to a taxable account (no statutory limit; user sets
  their own annual target)
- **HSA via bank transfer** — only if you fund your HSA manually from a bank account
  (self-employed or post-tax HSA top-up); payroll-deducted HSA contributions are invisible

Progress bar and percentage filled for each trackable account type.  
Limits configurable in Dashboard Settings > Investment Limits (pre-filled with current IRS values, adjustable per year).

**Implementation notes:**
- Sum `direction=Out, label=Retirement` transfers for the current calendar year
- Display as a single "Progress toward limits" card on the Investments tab
- Backend endpoint: `GET /api/investment-summary?year=YYYY`

#### 18b. Account-Level Breakdown
Users often have multiple investment accounts (e.g., Fidelity 401k + Robinhood personal +
Betterment IRA). Currently all transfers show as a flat list under one "Firm" column with no
grouping.

- Allow users to assign a **firm name** and **account type** (401k / Roth IRA / Taxable /
  HSA / Other) to each transfer row, configured in Dashboard Settings > Investment Accounts
- Group the Investments tab table by account, showing per-account subtotals
- At parse time, auto-assign account type from saved settings; user can override per-row in the UI
- Retirement/Personal label remains for the two-bucket summary; account type gives finer detail

#### 18c. Monthly Investment Rate Chart
Add a bar chart to the Investments tab showing monthly investment outflows over the last 12
months, similar to the income vs. expense comparison chart on the Overview tab:

- Bars stacked by account type (Retirement blue, Personal teal)
- Overlaid line: investment as a % of that month's income
- Helps visualize whether contribution pace is on track for the year

#### 18d. Savings Rate Metric on Overview
Surface the investment data on the main Overview tab:

- Add **Savings Rate** = (investment outflows + net bank surplus) / total income
- Show in the summary stat strip alongside Total Income / Total Expenses
- Compare against the 15–20% rule-of-thumb guideline from personal finance literature

---

## Technical Debt

### High Priority
- **Migrate transaction storage from CSV to a database** *(Phase 1 complete — v1.1.0)*

  **Phase 1 (implemented):**
  - `src/database/` package: `models.py` (SQLAlchemy Core tables), `session.py` (engine/session factory), `migrate.py` (`sync_from_csvs` / `sync_month`)
  - `src/ui/data/budget.db` — SQLite DB, populated on startup and after every aggregate/process run
  - DB is used for `/api/available-months`, `/api/all-expenses`, `/api/income-by-month`, `/api/income-entries` with CSV fallback if DB is unavailable
  - All write endpoints (`/api/expense/edit`, `/api/expense/label`, `/api/income/label`, category and reclassify endpoints) call `sync_month()` after writing to CSV to keep DB in sync
  - `scripts/aggregate_monthly.py` syncs the DB at the end of every run
  - CSV files remain the authoritative write target for backward compatibility

  **Phase 2 (remaining):**
  - Migrate complex read endpoints (`/api/expenses-by-month`, `/api/expense-categories`, `/api/income-breakdown`) to DB — these involve reimbursement cross-table logic and subcategory roll-up that need careful porting
  - Have write endpoints write to DB as primary, generate CSVs as exports
  - Replace the keyword-based investment platform detection with `merchant_metadata.is_investment_platform` DB lookups (config/investment_platforms.json is the bridge — already done)
  - Have `process_monthly.py` write new transactions directly to DB (currently only `aggregate_monthly.py` syncs)
  - Have `chatbot_assistant.py` load expense data from DB instead of scanning CSVs

- Unit tests for `StatementParser` (`src/statement_parser/parser.py`)
- Unit tests for `TransactionCategorizer` (`src/ai_classification/categorizer.py`)
- Integration tests for full PDF → dashboard workflow

### Medium Priority
- ~~**Move `_INVESTMENT_PLATFORM_KEYWORDS` to `config/investment_platforms.json`**~~ *(Done — v1.1.0)*
  `config/investment_platforms.json` now exists; both `main.py` and `aggregate_monthly.py`
  load keywords from it at startup.  The duplicate hardcoded constant has been removed from
  both files.  Longer term, replace keyword matching entirely with `merchant_metadata` DB
  tags once `Investment Return` is reliably auto-assigned (see database migration item above).

- Type hints throughout `process_monthly.py` (currently partially typed)
- Centralize Ollama host configuration (currently spread across multiple files)
- Replace hardcoded debug keyword filters in `classify_transactions` with a proper debug flag

### Low Priority
- CI/CD pipeline (GitHub Actions: run tests on push)
- Docker image size reduction (multi-stage build to exclude dev dependencies)
- API rate limiting / authentication for production deployments

---

### 19. Receipt Tracking & Attachment
**Priority:** High  
**Complexity:** Medium

Capture and link receipts to individual transactions so every line item has a paper trail.

**Upload & storage:**
- Upload receipt photo or PDF from the transaction detail panel in the dashboard
- Stored at `src/ui/data/statements/YYYY-MM/receipts/<tx_hash>.<ext>` — one file per transaction
- Supported formats: JPEG, PNG, PDF
- Auto-link to the transaction by `tx_hash` so the attachment survives re-aggregation

**OCR parsing (optional AI enhancement):**
- Run the receipt image through Tesseract OCR on upload
- Extract total amount and date for verification — flag if they don't match the parsed transaction
- Extract individual line items (for grocery/restaurant receipts) and store as structured JSON
  under `src/ui/data/receipts/<tx_hash>_items.json`
- Line items can be split across multiple categories (e.g., one Walmart receipt has both groceries
  and household supplies)

**Dashboard:**
- Paperclip icon on transaction rows that have an attachment
- Click to view the receipt image / PDF inline
- "Missing receipt" filter — show all transactions above $X with no attachment
- Export receipts as a ZIP for expense reporting or tax prep

**Backend:**
- `POST /api/receipt/upload` — multipart upload, returns attachment URL
- `GET /api/receipt/<tx_hash>` — serve the file
- `DELETE /api/receipt/<tx_hash>` — remove attachment
- New `receipt_path` column on the `transactions` table

---

### 20. Savings Goal Tracker
**Priority:** High  
**Complexity:** Medium

Define savings goals and watch real transaction data fill them automatically.

**How it works:**
- User creates a goal: name, target amount, target date, and optionally a funding account keyword
  (e.g. "savings" to watch transfers to a savings account)
- Every month, the app measures either:
  - **Surplus-based:** income − expenses for the month is treated as implicit savings
  - **Transfer-based:** transactions matching the funding keyword are counted as explicit
    contributions (e.g., "Online Transfer to Savings XXXXXXX7950" → maps to the goal)
- Running balance displayed as a progress bar toward the target

**Goals created and managed via the Dashboard Goals tab:**

**Dashboard — Goals widget:**
- Progress bar per goal: amount saved / target, % complete, projected completion date
- On-track vs. behind-pace indicator based on linear interpolation to target date
- "What if I save $X more/month?" quick calculator
- Contributions timeline — bar chart of monthly contributions
- Mark a goal as complete; archive it but keep the history

**Implementation notes:**
- Goals are stored in the DB; contributions are derived from the `transactions` table at read time
- No new DB table required for Phase 1 — compute on the fly from `tx_type='transfer'` rows
  matching the keyword or from monthly surplus totals
- Later: store a computed `contributions` ledger JSON for faster dashboard load

---

### 21. Credit Card Payment Detection
**Priority:** High  
**Complexity:** Low–Medium

When you pay your credit card bill from your checking account, that payment shows up as an
expense in the checking statement. But the individual purchases on the credit card are
*already* counted as expenses — so the payment is pure double-counting if both statements
are loaded.

**Detection approach:**
- At `aggregate_monthly.py` time, scan for transactions that match the pattern of a credit
  card payment:
  - Description matches known card issuer keywords: "Chase", "Discover", "Capital One",
    "Citi", "Amex", "American Express", "Bank of America", "Synchrony", "Barclays", etc.
  - Or description matches transfer keywords: "Online Payment", "Bill Payment", "ACH Payment"
  - And the transaction is a large round(ish) debit from a checking account
- Cross-reference: if the same month already has a credit card statement loaded (expense rows
  with `statement` matching the issuer), the checking debit is almost certainly a payment
- Auto-tag matched rows as `tx_type='transfer'`, `category='Credit Card Payment'` so they
  disappear from the expense total

**Card issuers managed in Dashboard Settings > Credit Cards:**
- Pre-populated with common issuers (Chase, Discover, Capital One, Citi, Amex, Bank of America, Synchrony, etc.)
- Add or remove keywords for less common cards from the settings page

**User control:**
- Toggle per-transaction in the UI — if a keyword false-positive fires, click to mark it
  as a real expense (sets `user_corrected=1`)
- A new "Credit Card Payments" section in the Settings page to manage keywords and review
  auto-detected payments

**Limitations:**
- Works best when both the checking account statement AND the credit card statement are
  uploaded for the same month — the cross-reference check then eliminates false positives
- If only the checking account is uploaded, uses keyword-only detection (more false positives)

---

### 22. Tax-Season Receipt Export
**Priority:** High  
**Complexity:** Low–Medium

A dedicated workflow for bundling all receipts attached to transactions (see feature #19) into
a clean, organized package ready for a tax preparer or personal records.

**Export flow — triggered from Dashboard > Settings > Export Receipts:**
- Choose a date range (e.g., Jan 1 – Dec 31 2025) or select individual months
- Optionally filter by category (e.g., only Business, Medical, Home Office)
- Optionally filter to only transactions flagged `tax_deductible=true` (see tagging below)
- Click **Export for Tax Season** — downloads a ZIP immediately

**ZIP structure:**
```
tax_receipts_2025/
  index.csv                          ← master ledger (date, merchant, amount, category, receipt filename)
  01_January/
    2025-01-15_Walgreens_$42.17.pdf
    2025-01-22_CVS_$18.00.jpg
  02_February/
    ...
  Uncategorized/                     ← receipts with no date match
```
- Each receipt file is renamed to `YYYY-MM-DD_<Merchant>_$<Amount>.<ext>` for easy scanning
- `index.csv` lists every transaction in the range, with a `receipt_attached` column (Yes/No)
  so gaps are immediately visible to the tax preparer

**Tax-deductible tagging:**
- Add a `💼 Tax` toggle button on each transaction row (appears on hover, like the existing
  Label button)
- Tags the transaction with `label='tax_deductible'` in the DB — persists across re-aggregates
- Filter in the export UI: "Tax-tagged only" vs "All with receipts" vs "All in range"
- A summary line in `index.csv` shows subtotals per category for deduction worksheets

**Backend:**
- `GET /api/export/receipts?start=2025-01&end=2025-12&tax_only=true` — streams a ZIP
- Uses Python's `zipfile` module; receipts read from `src/ui/data/statements/YYYY-MM/receipts/`
- `index.csv` generated on the fly from the `transactions` table — no pre-computation needed

---

### 24. Event-Based Spending Tracking
**Priority:** Medium  
**Complexity:** Low–Medium

Group individual transactions under a named event (e.g. "Texas Vacation", "Wedding", "Home Renovation") so you can see exactly how much a specific event cost across all categories and dates.

**How it works:**
- User creates an event: name, optional date range, optional description
- Transactions are tagged to an event manually from the All Transactions tab — either one at a time or with a bulk-select checkbox
- Multiple events can coexist; a transaction can belong to at most one event
- Event totals are computed live from the tagged transactions — no separate ledger needed

**Events managed via a new Dashboard Events tab:**
- Create / rename / delete events
- Summary card per event: total spent, date range, # of transactions, breakdown by category
- Expand an event to see the full transaction list (same inline-edit controls as the Transactions tab)
- Remove a transaction from an event without deleting it

**Tagging transactions from the Transactions tab:**
- New "Event" column in the transaction table (blank if untagged)
- Clicking the cell opens a dropdown of existing events + "New event…" option
- Bulk-tag: select multiple rows via checkboxes → "Assign to event" action in the toolbar

**Chatbot integration:**
- "How much did I spend on the Texas vacation?" → chatbot filters by event tag and reports totals/breakdown
- Intent model gains a new `event` field: `"event": "<event name or null>"`

**Implementation notes:**

*Database:*
- New `events` table: `id`, `name` (unique), `description`, `date_start` (optional), `date_end` (optional), `created_at`
- New `event_id` column on the `transactions` table (`INTEGER`, nullable, FK to `events.id`)
- Index on `transactions.event_id` for fast event summaries

*Backend:*
- `GET /api/events` — list all events with computed totals (total_amount, tx_count, category breakdown)
- `POST /api/events` — create event (`{ name, description, date_start, date_end }`)
- `PATCH /api/events/:id` — rename / update description
- `DELETE /api/events/:id` — delete event (clears `event_id` on linked transactions, does not delete transactions)
- `POST /api/events/:id/transactions` — bulk-assign tx_hashes to an event (`{ tx_hashes: [...] }`)
- `DELETE /api/events/:id/transactions` — bulk-remove tx_hashes from an event
- Existing `/api/all-expenses` response gains an `event_id` and `event_name` field per row

*Frontend:*
- New `EventsTab.js` component, registered in the tab nav as `🎫 Events`
- `TransactionsTab.js` — add "Event" column with the same inline-dropdown pattern used for category edits; add checkbox column + "Assign to event" toolbar button for bulk tagging

---

## Ideas Under Consideration

These don't have a clear implementation plan yet but have been requested:

- **Spending prediction** — ML model to forecast next month's spend by category based on history
- **Tax categorization** — tag transactions as potentially tax-deductible (home office, business meals, etc.)
- **Shared expense splitting** — handle joint accounts and split expenses between people
- **Net worth tracking** — include investment account balances alongside spending data
- **Dark mode** — for the dashboard UI

---

## Implementation Design: Budget & Goals Tab Redesign

### Problem Statement

The current "Budget & Goals" tab (`InsightsPanel.js` → `planSection === 'budget'`) has the right bones but the wrong mental model. The key issues:

1. **Wrong baseline** — AI suggestions currently use `average_spend ± 10%`. They are not anchored to income at all unless Ollama is running, and even then the prompt uses gross income rather than the after-tax take-home that actually flows through bank statements.
2. **No budget philosophy** — the user has no guide for *how* to set a budget. The table just dumps AI numbers with no context.
3. **Post-month-only feedback** — because statements are processed at month-end, there is nothing to track *during* the month. The design should lean into this reality rather than fighting it.
4. **Goals are fragile** — goals are stored in `config/budgets.json` as a flat `{category: amount}` map. There is no history, no variance tracking, no concept of "did I actually improve this quarter?"
5. **No savings rate visibility** — income is used only to warn "goals exceed income." There is no savings rate metric, no surplus target, no connection between budget goals and long-term goals.
6. **Forecast and Budget are separate but shouldn't be** — the forecast panel shows what you *will* spend; the budget panel shows what you *want* to spend. These should be on the same screen so the gap is obvious.

---

### Proposed Budget Philosophy

**Use a hybrid of three well-established strategies, applied in order:**

#### Step 1 — Pay Yourself First (foundation)
Before allocating any category budgets, reserve savings first. The user sets a monthly savings target (either a dollar amount or a % of income). This comes off the top. Whatever remains is the "spendable income."

> "If you save what's left after spending, you'll spend what's left after saving."
> — classic personal finance principle

#### Step 2 — 50/30/20 guardrails (orientation)
The AI uses the user's **average net monthly income** (from processed income statements, already excluding bonuses) to classify every category as **Needs / Wants / Savings** and compute whether each bucket is in bounds:

| Bucket | Target share of net income |
|--------|---------------------------|
| Needs (housing, groceries, utilities, insurance, healthcare, gas, auto maintenance) | ≤ 50% |
| Wants (dining, entertainment, shopping, alcohol, subscriptions, personal care, gifts) | ≤ 30% |
| Savings + Investments | ≥ 20% |

This gives each category a guardrail value derived from **income**, not from past spending. The app shows both the guardrail and the historical average — the user picks a number between the two.

#### Step 3 — Spend-baseline adjustment (reality check)
For any category where the historical average is already *below* the guardrail (e.g. you already spend only 8% on Dining when the cap is 15%), the AI suggests the historical average as the goal — no reason to set a looser target. For categories above the guardrail, the AI suggests the guardrail amount and flags it red.

#### Why not zero-based budgeting?
Zero-based (every dollar assigned until income = 0) is the most rigorous but also the most brittle for this use case. Because statements are processed monthly rather than in real-time, the user cannot adjust mid-month. A guardrail system that reviews targets quarterly is more practical here.

---

### UX Redesign: Budget & Goals Tab Layout

The "Budget & Forecast" top-level tab should be replaced with two clearly separated tools.

#### Panel A — "My Budget" (monthly spending plan)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  YOUR MONTHLY BUDGET                                    ⚙ Budget Settings    │
│  Based on avg income $5,274/mo  •  Analysis: last 3 months                  │
│                                                                              │
│  💰 Pay Yourself First Target: [  $800  ] / mo  (15.2% of income)     [Set] │
│  Remaining spendable: $4,474/mo                                             │
│                                                                              │
│  📊 50/30/20 HEALTH CHECK                                                   │
│  Needs    ████████████░░░░  $2,650  (50.2% — ⚠ slightly over 50% target)   │
│  Wants    ██████░░░░░░░░░░  $820    (15.6% — ✓ well within 30% cap)         │
│  Savings  ████░░░░░░░░░░░░  $800    (15.2% — ⚠ below 20% target)            │
│                                                                              │
│  ┌─────────────────┬────────────┬────────────┬────────────┬──────────────┐  │
│  │ Category        │ Type       │ 3-mo Avg   │ AI Cap     │ Your Goal    │  │
│  ├─────────────────┼────────────┼────────────┼────────────┼──────────────┤  │
│  │ Rent/Mortgage   │ Need       │ $815       │ $1,582 (30%)│ [  $815  ]  │  │
│  │ Groceries       │ Need       │ $477       │ $790 (15%) │ [  $450  ]  │  │
│  │ Shopping        │ Want 🔴    │ $540       │ $395 (7.5%)│ [  $400  ]  │  │
│  │ …               │ …          │ …          │ …          │ …           │  │
│  └─────────────────┴────────────┴────────────┴────────────┴──────────────┘  │
│                                                                              │
│  [💾 Save Goals]  [🔄 Reset to AI Suggestions]  [📋 Export Budget as CSV]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Panel B — "Month Review" (post-processing report card)

Shown automatically when the currently selected month has been processed:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  JANUARY 2025 — BUDGET REPORT CARD                                          │
│                                                                              │
│  Total Budget: $4,474   Actual Spend: $4,198   Surplus: $276 ✓              │
│                                                                              │
│  Category       Goal       Actual     Diff       Bar                        │
│  ──────────────────────────────────────────────────────                     │
│  Rent/Mortgage  $815       $815       $0         ██████████ 100% ✓          │
│  Groceries      $450       $521       +$71 🔴    ████████████ 116% ⚠        │
│  Shopping       $400       $273       -$127 ✓    ███████ 68% ✓              │
│  Alcohol/Bar    $80        $160       +$80 🔴    ████████████████ 200% 🔴   │
│  …                                                                           │
│                                                                              │
│  📈 Trend: 3-month goal attainment                                           │
│  [Nov] ████████░░ 82%   [Dec] ██████████░ 91%   [Jan] ████████████ 94% ↑   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### No More `config/budgets.json`

Every other JSON config file (`investment_platforms.json`, `income_keywords.json`, etc.) has already been migrated to DB tables managed via the dashboard. Budget goals should follow the same pattern — no disk files, no container rebuilds needed to change a goal, and no drift between what the UI shows and what the file contains.

`config/budgets.json` is **eliminated entirely**. The two tables below replace it.

#### New `budget_goals` DB table (replaces `budgets.json`)

One row per category. This is the single source of truth for what the user wants to spend.

```sql
CREATE TABLE budget_goals (
  id               INTEGER PRIMARY KEY,
  category         TEXT NOT NULL UNIQUE,
  goal_amount      REAL,            -- user's saved goal (null = no goal set)
  ai_cap           REAL,            -- income-anchored 50/30/20 ceiling
  historical_avg   REAL,            -- 3-month rolling average at time of last AI run
  bucket           TEXT,            -- 'Need' | 'Want' | 'Saving'
  bucket_override  BOOLEAN DEFAULT 0, -- true = user manually changed the bucket
  updated_at       TEXT             -- ISO timestamp of last save
);

-- Global budget settings (one row, updated in-place)
CREATE TABLE budget_settings (
  id                      INTEGER PRIMARY KEY,  -- always 1
  savings_target_amount   REAL,
  savings_target_pct      REAL,
  strategy                TEXT DEFAULT '50/30/20',
  avg_monthly_income_used REAL,
  updated_at              TEXT
);
```

Both tables are created in `src/database/models.py` alongside the existing keyword tables, seeded on startup (empty), and managed exclusively through the dashboard UI — the same pattern already used for `investment_keywords`, `income_keywords`, etc.

#### New `budget_history` DB table (attainment tracking)

Populated automatically each time `aggregate_monthly.py` runs:

```sql
CREATE TABLE budget_history (
  id            INTEGER PRIMARY KEY,
  report_month  TEXT NOT NULL,   -- YYYY-MM
  category      TEXT NOT NULL,
  goal          REAL,
  actual        REAL,
  variance      REAL,            -- actual − goal (negative = under budget ✓)
  variance_pct  REAL,
  created_at    TEXT,
  UNIQUE(report_month, category)
);
```

---

### AI Integration Strategy

The 50/30/20 framework provides the *structure*; AI provides the *intelligence within each bucket*. Here is where AI adds real value at each layer:

#### AI Role 1 — Automatic bucket classification
Rather than hard-coding a lookup table of which categories are Needs vs. Wants, the AI classifies each category the user actually has in their data:

- **Heuristic baseline** (no LLM required): a built-in map covers the 80% case —
  `Rent/Mortgage`, `Electric`, `Natural Gas`, `Water/Sewer`, `Internet/Cable`, `Groceries`, `Healthcare`, `Insurance`, `Gas/Fuel`, `Auto Maintenance` → Need;
  `Dining`, `Entertainment`, `Shopping`, `Alcohol/Bar`, `Personal Care`, `Gifts & Donations`, `Subscriptions`, `Travel` → Want;
  `Investment` → Saving.
- **LLM override for unknowns**: any category not in the map is sent to the intent model with a short prompt — "Is '{category}' a household necessity (Need), a discretionary expense (Want), or a savings vehicle (Saving)? One word." This fires once per new category and the answer is cached in `budget_goals.bucket`.
- **User override always wins**: if the user changes a bucket in the UI, `bucket_override = true` and AI never re-classifies that row.

#### AI Role 2 — Smart allocation within the Needs 50% pool
This is the most useful AI contribution. Once the user's 50% Needs ceiling is computed (e.g., 50% of $5,274 = $2,637), the AI distributes that pool across Need-bucket categories proportionally — but with adjustments:

1. **Fixed-cost lock**: categories where the 3-month average has near-zero variance (σ < $10) are locked at their actual average. You can't reduce rent by optimizing a budget goal. These go in first and are subtracted from the pool before anything else is allocated.
2. **Variable-need allocation**: the remaining pool is split among variable Need categories (groceries, gas, healthcare) proportionally to their 3-month averages, then rounded to the nearest $5.
3. **LLM coaching for over-allocated pools**: if fixed-cost Needs alone exceed 50% of income (e.g., rent is 45%, leaving almost nothing), the AI generates a plain-English note — "Your fixed housing and utility costs account for 47% of income, leaving only 3% of income for groceries, gas, and healthcare combined. You may want to adjust your savings target down temporarily." This surfaces in the UI as a callout card, not a blocking error.

#### AI Role 3 — Personalized percentage split suggestion
The standard 50/30/20 split doesn't fit everyone. After computing what the user actually spends, the AI checks whether 50/30/20 is even achievable and suggests an adjusted split if not:

- If fixed Needs already consume >50%: suggest 60/20/20 or 65/15/20 and explain why
- If the user's Want spending is unusually low (<15%): suggest relaxing the savings target to reward good habits without over-restricting
- The suggestion is shown as a banner: "Based on your spending, a **55/25/20** split is more realistic for your income level. [Apply this split]"
- Applying it updates `budget_settings.strategy` to `'custom'` and recalculates all `ai_cap` values

#### AI Role 4 — Trend-aware goal adjustment
A flat 3-month average misses direction. If groceries have been $400 → $450 → $480 over three months, suggesting $443 (the average) sets the user up to fail immediately.

- For each category, compute the month-over-month trend: `slope = linear_regression(monthly_amounts)`
- If slope > +5%/month for two or more consecutive months: `suggested_goal = latest_month_actual × 1.05` (acknowledge the trend, set a mild ceiling)
- If slope < −5%/month: `suggested_goal = avg × 0.95` (you're improving, encourage continuation)
- The trend direction (`📈`, `📉`, `➡`) and the adjustment rationale are shown in the `AI Cap` column tooltip

#### AI Role 5 — Month-end coaching narrative
After each month is processed and `budget_history` rows are written, the LLM generates a 3–5 sentence budget debrief, displayed as a card at the top of the Report Card panel:

> "January was a mixed month. You came in under budget on Shopping (−$127) and Auto Maintenance (−$34), but Groceries ran $71 over your $450 goal — likely due to the holiday stocking-up pattern in late December carried into early January. The most significant miss was Alcohol/Bar at 200% of goal. If that's a one-time event, carry $80 of the overage into a one-time buffer next month. Your overall savings rate was 12.3%, short of the 15% target by $143."

This fires as a POST to `/api/budget/debrief/{month}` and is cached in `budget_history` as a `coaching_note TEXT` column so it doesn't re-run on every page load.

---

### Correlation with the Overview Tab

The Overview tab and the Budget & Forecast tab both call the same `InsightsPanel` component, which hits `/api/budget-suggestions` and `/api/budget/{month}`. They are already sharing data — but there is a subtle mismatch today: the Overview panel re-runs the AI suggestion every load using a fresh 3-month average, while the Budget tab might show goals the user saved weeks ago. They can diverge.

**Fix**: distinguish between "AI suggestions" (ephemeral, always fresh) and "your saved goals" (stable, from the DB):

- `/api/budget-suggestions` → always fresh AI output; used to populate the AI Cap column and the 50/30/20 health bars
- `/api/budget/goals` → the user's saved `budget_goals` rows; used for the "Your Goal" column and the Overview summary widget
- The Overview InsightsPanel "budget snapshot" widget shows goals from `budget_goals`, not the live AI suggestion — so if the user hasn't saved goals yet it says "No budget set — go to the Budget tab to set one" rather than showing a fresh AI estimate that may not match what the user agreed to

This keeps the two panels consistent: the Budget tab is where you *set* goals, the Overview is where you *track* them.

---

### Backend Changes

#### `src/database/models.py`
- Add `budget_goals`, `budget_settings`, and `budget_history` tables
- Migrate on startup: if `config/budgets.json` exists, import its flat `{category: amount}` values into `budget_goals` rows (one-time migration), then delete the file

#### `GET /api/budget/goals` — new endpoint
Returns all rows from `budget_goals` plus the single `budget_settings` row. This is what the Overview widget and the "Your Goal" column read from.

#### `GET /api/budget-suggestions` — improvements
- Accept `strategy`: `50_30_20` (default) | `spending_baseline` | `custom`
- Accept `savings_target` (dollar amount or %; used to compute spendable pool)
- Always return per-category: `ai_cap`, `bucket`, `historical_avg`, `trend_slope`, `trend_direction`
- Return top-level: `need_pct`, `want_pct`, `savings_pct` (actual vs targets), `personalized_split_suggestion`
- Fixed-cost categories flagged with `is_fixed_cost: true` in the response

#### `POST /api/budget/goals` — replaces `POST /api/budget/save`
Writes to `budget_goals` and `budget_settings` tables. Accepts the same category map the UI already sends, extended with `bucket`, `ai_cap`, and the top-level settings fields.

#### `GET /api/budget/{month}` — improvements
- Read goals from `budget_goals` DB table (not the file)
- Include `variance_trend`: last 3 months of `budget_history` rows per category
- Include `overall_attainment_pct`
- Include `savings_rate_actual` = (total_income − total_expenses) / total_income

#### `POST /api/budget/debrief/{month}` — new endpoint
Generates and caches the AI coaching narrative for a given month. Returns the text immediately if already cached in `budget_history.coaching_note`.

#### `GET /api/budget/history` — new endpoint
`GET /api/budget/history?months=6` — returns aggregated `budget_history` rows for the trend chart.

#### `scripts/aggregate_monthly.py` — additions
After writing transactions to DB, snapshot `budget_goals` into `budget_history` rows for the processed month. Also trigger the coaching debrief generation if a finance model is configured.

---

### Frontend Changes (`InsightsPanel.js` / `App.js`)

1. **Pay Yourself First input** — dollar amount or % toggle at the top of the Budget panel. Saves to `budget_settings`. Recomputes spendable pool and the 50/30/20 health bars live as the user types.

2. **50/30/20 health bars** — three stacked horizontal bars (Needs / Wants / Savings) that recompute live as goals are edited. Color: green = in target range, amber = within 5% of boundary, red = over.

3. **`Bucket` column** (Need / Want / Saving) — read from `budget_goals.bucket`. Editable via a small dropdown; saving sets `bucket_override = true`. AI-classified buckets show a subtle "AI" badge that disappears once overridden.

4. **Separate `AI Cap` and `Your Goal` columns** — `AI Cap` is always the income-anchored ceiling from `/api/budget-suggestions`; it updates when you change the savings target. `Your Goal` is your saved value from `budget_goals`.

5. **Fixed-cost rows** — categories flagged `is_fixed_cost` show a lock icon in the Goal cell; the AI Cap column shows their actual average with a tooltip "Fixed cost — AI does not reduce this."

6. **Month Report Card** — shown below the budget table when `selectedMonth` has `budget_history` rows. Includes the AI coaching narrative card at the top, per-category progress bars, and a 3-month attainment trend.

7. **Overview budget widget** — reads from `/api/budget/goals` (saved goals) not from `/api/budget-suggestions` (fresh AI). Shows "No goals set" state with a link to the Budget tab if `budget_goals` is empty.

8. **Persist `planSection` to `localStorage`** — sub-section no longer resets on tab switch.

---

### Implementation Sequence

**Phase 1 — DB migration (no visible UI change)**
- Add `budget_goals`, `budget_settings`, `budget_history` tables to `models.py`
- One-time migration: import `config/budgets.json` flat values into `budget_goals` on startup; delete the file
- Add `GET /api/budget/goals` and `POST /api/budget/goals` endpoints; deprecate `POST /api/budget/save`
- Update `GET /api/budget/{month}` to read from `budget_goals` table
- Update `aggregate_monthly.py` to write `budget_history` rows post-processing

**Phase 2 — AI suggestion improvements (backend only)**
- Add bucket classification (heuristic map + LLM fallback for unknowns)
- Add trend slope computation to `budget_advisor.py`
- Add fixed-cost detection (low-variance categories)
- Smart Needs pool allocation
- Personalized split suggestion
- Update `/api/budget-suggestions` response shape

**Phase 3 — Budget panel UI**
- Pay Yourself First input + live spendable pool
- 50/30/20 health bars
- `Bucket` column with dropdown + AI badge
- Separate `AI Cap` and `Your Goal` columns
- Fixed-cost lock icon

**Phase 4 — Report Card + coaching**
- Month Report Card below budget table
- AI coaching narrative card (POST `/api/budget/debrief/{month}`, cache in DB)
- 3-month attainment trend mini-chart
- Overview widget reads saved goals from DB

**Phase 5 — Strategy picker (optional)**
- Settings > Budget tab: strategy selector (50/30/20 | Spending Baseline | Custom)
- Custom mode: user sets their own Needs/Wants/Savings % targets

---

## AI Architecture: Hermes Memory Management & Persistent Sessions

This section documents the design decisions and integration plan for using
a Hermes-family model as the **memory manager** across both the GUI chatbot and
the transaction categorization/cleaning pipeline.

---

### Background — The Stateless Agent Problem

Every AI feature that currently calls Ollama is **stateless**:

| Feature | Current behaviour | Problem |
|---------|------------------|---------|
| GUI Chatbot `/api/chat` | Creates a new `ChatbotAssistant()` per HTTP request | `ConversationState` rebuilt from scratch via regex fallback; no true in-model memory |
| Transaction categorization | One `requests.post()` per merchant | Model has no memory of what it just categorised — identical logic is re-executed for every merchant |
| Merchant name cleaning | One `requests.post()` per merchant | Same issue — the model cannot learn from merchants it cleaned earlier in the same batch |

The core insight is: **starting a new session per transaction or per API call
forces the model to rediscover context it already established, leading to
inconsistent results and unnecessary latency.**

---

### Solution: Hermes as the Memory Layer

[Hermes](https://huggingface.co/NousResearch) (NousResearch Hermes-3 and
variants) is optimised for **agentic loops, tool calling, and structured memory
management**.  Its system-prompt following and JSON-mode reliability make it a
natural fit as the memory layer.

The memory model is configured in `config/llm_models.json`:

```json
{
  "memory_model": "hermes3"
}
```

Set to an empty string `""` to disable memory summarisation (the system still
works — it just trims to a raw 8-turn window instead of a compressed summary).

---

### Part 1: Chatbot Session Persistence (Implemented)

#### What was built

| Component | Location | Description |
|-----------|----------|-------------|
| `chat_sessions` DB table | `src/database/models.py` | Stores `session_id`, `title`, `messages` (JSON), `conv_state` (JSON), `summary` (Hermes output) |
| `_SESSION_CACHE` | `src/ai_analysis/chatbot_assistant.py` | Module-level dict of live `ChatbotAssistant` instances keyed by `session_id` |
| `get_or_create_assistant()` | `chatbot_assistant.py` | Returns cached instance or reconstructs from DB on server restart |
| `ConversationState.to_dict()` / `from_dict()` | `chatbot_assistant.py` | Serialises/deserialises `active_period`, `active_category`, goals, etc. |
| `save_session()` / `load_session()` | `chatbot_assistant.py` | DB read/write helpers |
| `list_sessions()` / `delete_session()` | `chatbot_assistant.py` | Session management helpers |
| `GET /api/chat/sessions` | `routes/analytics.py` | List all sessions |
| `GET /api/chat/sessions/{id}` | `routes/analytics.py` | Get one session |
| `DELETE /api/chat/sessions/{id}` | `routes/analytics.py` | Delete a session |
| `POST /api/chat` (updated) | `routes/analytics.py` | Accepts `session_id`; persists history and state after each turn |
| `_summarize_session()` | `chatbot_assistant.py` | Calls `memory_model` to compress old turns |

#### How a conversation turn flows (new)

```
Client → POST /api/chat { message, session_id? }
         │
         ▼
get_or_create_assistant(session_id, model_name)
  ├── Cache hit?   → return live ChatbotAssistant (conv_state intact)
  └── Cache miss?  → load DB row → ConversationState.from_dict(conv_state)
         │
         ▼
load_session(session_id) → full messages list from DB
         │
         ▼
chatbot.process_message(month, message, messages, session_summary=summary)
  ├── _generate_ai_response(session_summary=…)
  │     ├── conv_state already populated (no regex rebuild needed)
  │     ├── _parse_intent(user_message, last 4 turns)
  │     ├── conv_state.update_from_intent(intent)
  │     ├── _calculate_facts_with_pandas(…)
  │     └── _call_finance_advisor(…, session_summary=summary)
  │           └── summary injected into system prompt when present
  └── returns { response, conversation_history }
         │
         ▼
Check: assistant_turns >= SESSION_SUMMARY_THRESHOLD and memory_model set?
  └── Yes → _summarize_session(messages) → new Hermes summary
         │
         ▼
save_session(session_id, title, updated_messages, conv_state.to_dict(), summary)
         │
         ▼
Response includes session_id so client can persist it for next turn
```

#### Memory summarisation trigger

When a session reaches `SESSION_SUMMARY_THRESHOLD = 20` assistant turns the
memory model is called.  The prompt:

> "Summarise the following conversation into a single compact paragraph that
> captures: the financial questions asked, the key data points discussed, any
> goals or budgets mentioned, and the time periods referenced. 3–5 sentences."

The summary replaces the `chat_sessions.summary` column.  On subsequent turns
it is injected into the finance advisor's system prompt as a **Session Memory**
block.  The raw `messages` list is still stored in full for the session history
sidebar — only the advisor sees the condensed version.

---

### Part 2: Batch Categorization Session (Implemented)

#### What was built

`TransactionCategorizer.categorize_batch_with_session()` in
`src/ai_classification/categorizer.py` runs an entire list of merchants through
**one persistent Ollama chat session** instead of N independent calls.

```python
results = categorizer.categorize_batch_with_session([
    ("Olive Garden", 45.20),
    ("Texas Roadhouse", 78.50),
    ("Uber Eats", 22.00),
    ("Walmart", 134.17),
])
# → {"Olive Garden": "Dining", "Texas Roadhouse": "Dining",
#    "Uber Eats": "Dining", "Walmart": "Groceries"}
```

The session opens with a system message establishing the full category list and
disambiguation rules.  Each merchant is sent as a `user` turn; the model's
`assistant` reply is fed back so subsequent turns benefit from seeing what
was already categorised.

#### How to integrate into `process_monthly.py`

The batch session method is available now.  To activate it for the main import
pipeline, replace the per-row LLM fallback in `classify_transactions()` with:

```python
# Collect merchants that need LLM categorization
llm_needed = [
    (row["Place"], row.get("Amount"))
    for _, row in df[df["category"] == "Uncategorized"].iterrows()
]

if llm_needed:
    batch_results = categorizer.categorize_batch_with_session(llm_needed)
    for idx, row in df.iterrows():
        if row["category"] == "Uncategorized":
            cat = batch_results.get(row["Place"])
            if cat:
                df.at[idx, "category"] = cat
```

This replaces N independent Ollama calls with one session of N turns —
typically 30–50% faster for batches of 10+ merchants, and more consistent
because the model sees its own prior answers.

---

### Part 3: Merchant Cleaning Batch Session (Planned)

**Status: Not yet implemented**  
**Priority:** Medium  
**Complexity:** Medium

The same persistent-session pattern can be applied to `llm_utils.py`
`clean_merchant_name_llm()`.  Currently every raw merchant string gets its own
Ollama call.  A batch session would let the model:

- Apply the same abbreviation expansion rule consistently across an import
  (e.g. every "WM" → "Walmart")
- Learn from earlier merchants in the batch (e.g. if "STARBUCKS #1234 SEA WA"
  was cleaned to "Starbucks", then "STARBUCKS #5678 PDX OR" benefits from that
  prior example)
- Reduce cold-start overhead when processing 50+ transactions

**Implementation sketch:**

```python
def clean_merchants_batch_with_session(
    merchants: List[Tuple[str, float, str]],   # (raw_name, amount, date)
    model: str,
    known_names: list = None,
) -> Dict[str, str]:
    """
    Clean a list of merchant names in a single Ollama session.
    Returns {raw_name: clean_name}.
    """
    system_msg = (
        "You are a merchant name cleaner.  I will send you raw bank transaction "
        "descriptions one at a time.  For each, reply with ONLY the clean merchant "
        "name in the format: Name | Confidence | Reasoning\n\n"
        "Rules: remove store numbers, locations, payment prefixes; fix capitalization; "
        "expand abbreviations.  Respond with exactly the format above — nothing else."
    )
    messages = [{"role": "system", "content": system_msg}]
    results = {}
    for raw, amount, date in merchants:
        messages.append({"role": "user", "content": raw})
        # ... call Ollama, parse response, feed back as assistant turn
    return results
```

**Integration point:** `scripts/process_monthly.py` `_clean_merchant_names()`
currently loops over merchants and calls `clean_merchant_with_ensemble()` per
merchant.  Switch to batch session when `len(merchants) > 5`.

---

### Part 4: Hermes Agent Loop for Autonomous Financial Review (Future)

**Status: Design only — not implemented**  
**Priority:** Low  
**Complexity:** High

The ultimate vision is a **Hermes agent loop** that can autonomously:

1. Review a newly imported month's transactions
2. Detect anomalies (unusual merchants, large one-time expenses)
3. Flag potential miscategorisations and suggest corrections
4. Draft a monthly financial summary for the user to review

This requires an **agentic tool-calling pattern** where Hermes can:

```
Hermes → call get_transactions(month="2026-05") → receives transaction list
Hermes → call get_category_averages(months=3) → receives historical benchmarks  
Hermes → call flag_transaction(tx_hash, reason) → flags for user review
Hermes → call draft_summary(month) → writes narrative to DB
```

The tool-call schema (OpenAI-compatible function calling) is already supported
by Hermes models via Ollama's `/api/chat` with `tools` payload.

**Prerequisites before implementing:**
- All write endpoints need idempotent, hash-checked operations (already true for
  transactions via `tx_hash`)
- Tool definitions need to be declared in a `config/agent_tools.json`
- The agent loop needs a **human-in-the-loop confirmation step** before any
  bulk category changes are committed — never allow fully autonomous writes to
  user financial data without explicit approval

