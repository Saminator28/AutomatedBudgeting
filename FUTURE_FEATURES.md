# Future Features & Enhancements

## Recently Completed ✅

### Multi-Model LLM Ensemble (December 2025)
- **qwen2.5:14b** as primary model for maximum accuracy
- Multi-model validation with 3-prompt system
- Post-processing normalization to fix LLM artifacts
- 90-95% accuracy on merchant name cleaning

### CSV Learning System (December 2025)
- Automatic learning from previous months' CSV corrections
- Frequency-based confidence scoring (high/medium/low)
- Similar merchant detection provides context to LLM
- Scans ALL previous months in <0.03 seconds
- Accuracy improves from 90% → 98% over time

### Historical Cache with Frequency Tracking (December 2025)
- Tracks merchant appearance frequency across all months
- High confidence (5+ occurrences): Instant recognition
- Medium confidence (2-4): Good context for LLM
- Low confidence (1): Full LLM processing with examples
- Example: "Cashwise - West Fargo" appears 45x = perfect accuracy

---

## Planned Features

### 1. Budget Analysis Q&A Tool (RAG-based)
**Priority:** Medium  
**Complexity:** Medium-High  
**Description:** Intelligent budget advisor using RAG (Retrieval Augmented Generation) to answer natural language questions about spending patterns and budget availability.

**Use Cases:**
- "Can I afford to buy a $500 TV this month?"
- "What's my average monthly dining expense?"
- "How much have I spent on groceries compared to last month?"
- "Do I have room in my Entertainment budget?"
- "What's my biggest expense category this year?"

**Implementation Approach:**
```bash
# After extraction workflow
python process_monthly.py --month 2025-11  # → expenses.csv, income.csv

# Query budget data with natural language
python query_budget.py "Can I afford a $300 purchase in Electronics?"
```

**Technical Details:**
- Load all expenses/income CSVs from multiple months into vector database
- Use embeddings (sentence-transformers) for semantic search
- Leverage Ollama LLM (dolphin-mistral) for natural language responses
- Calculate budget limits per category (average spending + threshold)
- Compare requested purchase against:
  * Historical spending patterns
  * Current month spending
  * Remaining budget in category
  * Overall financial health (income vs expenses)

**Required Components:**
1. `scripts/query_budget.py` - CLI for budget Q&A
2. `src/budget_analyzer/` - RAG pipeline:
   - `vector_store.py` - Load CSVs into embeddings
   - `budget_calculator.py` - Analyze spending patterns
   - `qa_engine.py` - LLM-powered Q&A
3. Add budget limits to `config/budget_limits.json` (optional)

**Benefits:**
- Natural language interface for financial insights
- Helps with purchasing decisions
- Identifies spending trends and anomalies
- Works with existing CSV data structure

**Dependencies:**
- `chromadb` or `qdrant-client` (vector database)
- `sentence-transformers` (embeddings)
- Already using Ollama (dolphin-mistral)

---

### 2. Merchant Name Enhancements

#### 2a. Focus Mode for Low-Confidence Merchants
**Priority:** Medium  
**Complexity:** Low  
**Description:** After processing, create a `review_needed.csv` containing only merchants with low confidence (appeared once, unclear naming).

**Benefits:**
- Batch-review uncertain merchants instead of scanning entire CSV
- Focus manual corrections where they matter most
- Skip high-confidence merchants (Target, Walmart, etc.)

**Implementation:**
```python
# After processing, generate review file
parser.export_low_confidence_transactions('statements/2025-01/review_needed.csv')
```

#### 2b. Time-Based Weighting
**Priority:** Low  
**Complexity:** Low  
**Description:** Weight recent months more heavily than older months for confidence scoring.

**Example:**
- Last 3 months: 100% weight
- 4-6 months ago: 75% weight
- 7-12 months ago: 50% weight
- 13+ months: 25% weight

**Benefits:** Adapts to changing merchant patterns (store closures, new favorites)

#### 2c. Difficult Merchants Configuration
**Priority:** Low  
**Complexity:** Low  
**Description:** Manual configuration file for consistently challenging merchants.

**File:** `config/difficult_merchants.json`
```json
{
  "patterns": {
    "BP#*": "BP",
    "SQSP* INV*": "Squarespace",
    "WL*Steam*": "Steam"
  }
}
```

**Benefits:** Pre-define known difficult patterns without waiting for CSV history

#### 2d. Fuzzy Matching for Similar Merchants
**Priority:** Medium  
**Complexity:** Medium  
**Description:** Use fuzzy string matching (Levenshtein distance) to find similar merchants when exact cache miss.

**Example:**
- Input: "WALMART SUPERCTR #1234 FARGO"
- Fuzzy match: "Walmart - Fargo" (edit distance: 15)
- Suggest: Use cached name if similarity > 80%

**Benefits:** Catches minor variations in merchant names

---

### 3. Web Dashboard (✅ Implemented)

- Interactive dashboard for visualizing categorized expenses
- Pie chart and table view
- Filter by category
- Easy launch script: `bash scripts/launch_dashboard.sh`
- Data source: `statements/YYYY-MM/expenses.csv`

See README.md for usage.

---

### 4. Budget Alerts & Notifications
**Priority:** Low  
**Complexity:** Low  
**Description:** Email/SMS alerts when approaching category budget limits.

---

### 5. Recurring Transaction Detection
**Priority:** Medium  
**Complexity:** Medium  
**Description:** Auto-detect subscriptions and recurring payments (Netflix, gym, etc.).

**Features:**
- Identify transactions that appear monthly
- Flag subscription services automatically
- Calculate annual subscription costs
- Alert on price changes

---

### 6. Multi-Currency Support
**Priority:** Low  
**Complexity:** Low  
**Description:** Handle statements with foreign transactions and currency conversion.

---

### 7. Export to Quickbooks/Mint
**Priority:** Low  
**Complexity:** Medium  
**Description:** Export processed transactions to popular financial software.

---

### 8. Receipt Attachment Linking
**Priority:** Low  
**Complexity:** Medium  
**Description:** Link scanned receipts to transactions for record-keeping.

---

### 9. Spending Prediction Model
**Priority:** Low  
**Complexity:** High  
**Description:** ML model to predict future spending based on historical patterns.

---

### 10. Advanced LLM Features

#### 10a. Semantic Similarity for Merchants
**Priority:** Medium  
**Complexity:** Medium  
**Description:** Use embeddings to find semantically similar merchants, not just string matching.

**Example:**
- Input: "BK #1234 FARGO"
- Embedding similarity finds: "Burger King" (even without string match)

**Tech:** sentence-transformers, vector database (ChromaDB)

#### 10b. Context-Aware Amount Validation
**Priority:** Low  
**Complexity:** Medium  
**Description:** Use LLM to validate if amount makes sense for merchant.

**Example:**
- "Gas station - $500" → Flag for review (unusually high)
- "Grocery store - $2" → Flag for review (unusually low)

#### 10c. Multi-Model Voting System
**Priority:** Low  
**Complexity:** Medium  
**Description:** Use 5+ models with weighted voting instead of current 3-prompt system.

**Benefits:** Even higher accuracy through diversity

---

### 11. Performance Optimizations

#### 11a. Parallel LLM Processing
**Priority:** Low  
**Complexity:** Medium  
**Description:** Process multiple transactions concurrently to speed up first-month processing.

**Expected:** 50% speed improvement (40min → 20min for 100 transactions)

#### 11b. Smart Cache Preloading
**Priority:** Low  
**Complexity:** Low  
**Description:** Preload cache with common merchant patterns on first run.

**File:** `config/common_merchants.json` (Top 100 US merchants)

---

### 12. Bank-Specific Improvements

#### 12a. Multi-Bank Statement Merging
**Priority:** Medium  
**Complexity:** Medium  
**Description:** Automatically merge statements from multiple banks in same month.

**Example:**
```bash
python scripts/process_monthly.py 2025-01 --merge
# Combines Chase + Wells Fargo + Discover into single expenses.csv
```

#### 12b. Bank-Specific Parser Profiles
**Priority:** Low  
**Complexity:** Low  
**Description:** Optimize parsing for specific bank formats (Chase, BOA, etc.).

---

## Feature Requests

Have an idea? Open an issue on GitHub or add it here!

---

## Technical Debt / Code Cleanup

### Completed Cleanup ✅ (December 2025)
- ~~`src/bankai/parser.backup/`~~ - Removed obsolete Table Transformer approach
- ~~`src/bankai/utils/place_cleaner.py`~~ - Removed static pattern cleaning (replaced by LLM)
- ~~Old documentation files~~ - Consolidated into focused docs/
- ~~68 lines of redundant code~~ - Removed from hybrid_parser.py
- ~~Hardcoded patterns~~ - Refactored to dictionary-based approach

### Future Code Quality Improvements
- Add comprehensive unit tests for HybridPDFParser
- Add integration tests for full workflow
- Add type hints throughout codebase
- Add docstrings to all public methods
- Set up CI/CD pipeline

---

## Past Feature Completions

### 2024-2025 Releases
- ✅ Category validation with LLM + fuzzy matching
- ✅ Automatic pattern learning from manual classifications
- ✅ Payment app distinction from uncategorized transactions
- ✅ Cross-statement transfer detection
- ✅ Lightweight `--manual-only` mode for quick updates
- ✅ Investment category support
- ✅ Multi-LLM validation system (3-prompt with confidence scoring)
- ✅ Dual extraction (pdfplumber + OCR) with cross-referencing
- ✅ Post-processing normalization for LLM outputs
- ✅ CSV learning system with frequency tracking
- ✅ Historical cache with confidence tiers
- ✅ Similar merchant detection for context
