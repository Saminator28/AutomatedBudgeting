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

Persist chatbot conversations so users can return to a previous analysis session.

- Each session saved as a JSON file under `src/ui/data/chat_sessions/YYYY-MM-DD_HH-MM.json`
- Session list shown in a sidebar with timestamps and auto-generated titles (based on first message)
- Users can rename, delete, or resume any session
- On resume, full message history is reloaded into the chat context
- Sessions are scoped to the local machine — no cloud sync

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

### 23. Annual Expense Amortization
**Priority:** High  
**Complexity:** Low–Medium

When a large payment covers an entire year (car insurance, HOA dues, software subscriptions
billed annually, etc.) it distorts the month it lands in — that month looks drastically
over-budget while every other month looks artificially cheap. Amortization spreads the cost
evenly so monthly budgets reflect the true recurring cost.

**How it works:**
- User flags a transaction as an annual expense and sets the coverage period
  (e.g., car insurance paid Jan 15, 2026 — covers Jan 2026 – Dec 2026, $1,200)
- The app divides the amount by 12 and creates a **virtual monthly allocation** of $100
  in each covered month under the same category
- The original transaction is kept intact and visible (labelled `annual_lump_sum`), but the
  dashboard's monthly totals use the amortized $100 figure instead of the full $1,200

**User workflow:**
- On any transaction row, click **⋯ → Amortize annually**
- Drawer opens with pre-filled fields: amount, category, start month, end month (defaults
  to 11 months after start), and a friendly label (e.g., "Car Insurance 2026")
- Save — the allocation is stored in a new `annual_allocations` table

**Dashboard changes:**
- Monthly expense totals on Overview and the category breakdown charts reflect amortized
  amounts when the "Amortized view" toggle is on (default: on)
- Toggle off to see raw transaction totals (useful for cash-flow planning)
- A small `÷12` badge appears on the category bar/slice that has active amortized entries
  so the user knows the figure has been adjusted
- **Annual Expenses** section in the Budgeting tab lists all active amortizations with
  status (coverage months remaining), next renewal alert, and an edit/delete option

**Renewal alerts:**
- 60 days before a coverage period ends, a banner appears in the dashboard:
  "Car Insurance renewal coming up in ~60 days — last year's cost was $1,200"
- After the new payment is detected from the next statement, the old allocation auto-closes
  and the user is prompted to create the new one

**Implementation notes:**
- `annual_allocations` table: `id`, `tx_hash` (links to the source transaction),
  `label`, `category`, `total_amount`, `monthly_amount`, `start_month`, `end_month`,
  `created_at`
- `GET /api/annual-allocations` — list all; `POST` to create; `DELETE /:id` to remove
- Monthly totals endpoint adds amortized amounts when `?amortized=true` (default)
- The source transaction's `label` is set to `annual_lump_sum` so it can be excluded from
  raw totals when amortized view is active

---

## Ideas Under Consideration

These don't have a clear implementation plan yet but have been requested:

- **Spending prediction** — ML model to forecast next month's spend by category based on history
- **Tax categorization** — tag transactions as potentially tax-deductible (home office, business meals, etc.)
- **Shared expense splitting** — handle joint accounts and split expenses between people
- **Net worth tracking** — include investment account balances alongside spending data
- **Dark mode** — for the dashboard UI
