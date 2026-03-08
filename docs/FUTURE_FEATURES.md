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

### 6. Export to Financial Software
**Priority:** Low  
**Complexity:** Medium

Export processed transactions to popular formats:

- **YNAB** (You Need A Budget) — `.csv` in YNAB import format
- **QuickBooks** — IIF or CSV format
- **Mint** — CSV export compatible
- **OFX/QFX** — universal bank format

---

### 7. Mobile-Friendly Dashboard
**Priority:** Medium  
**Complexity:** Low–Medium

The current React UI works on desktop. Responsive design improvements for phone/tablet:
- Touch-friendly transaction editing
- Swipe gestures on the pie chart
- Compact table view for small screens

---

### 8. Multi-Currency Support
**Priority:** Low  
**Complexity:** Low–Medium

Handle statements that include foreign currency transactions:
- Detect currency symbols and codes (€, £, ¥, CAD, etc.)
- Store original currency alongside USD value
- Show exchange rate used on transaction date (using free historical API like Open Exchange Rates)

---

### 9. Receipt Attachment Linking
**Priority:** Low  
**Complexity:** Medium

Allow users to attach receipt images or PDFs to individual transactions:
- Upload receipt via dashboard
- Store in `src/ui/data/statements/YYYY-MM/receipts/`
- Link receipt to transaction by date + amount
- View receipt from transaction detail panel

---

### 10. Performance: Parallel LLM Processing
**Priority:** Low  
**Complexity:** Medium

Currently, transactions are processed one at a time through the LLM. Processing in parallel batches would significantly reduce first-run time for large statements.

- Use `asyncio` + async Ollama client for concurrent requests
- Configurable batch size (default: 5 concurrent)
- Expected improvement: 50–70% reduction in processing time

---

### 11. Smart Cache Preloading
**Priority:** Low  
**Complexity:** Low

Bundle a `config/common_merchants.json` with the top 500 national merchants already pre-cleaned:
- Walmart, Target, Costco, Amazon, etc.
- Gas stations (Shell, BP, Chevron, Exxon, etc.)
- Fast food chains
- Streaming services

Benefit: instant recognition for common merchants on first run, before any CSV history exists.

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
