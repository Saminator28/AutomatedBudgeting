# Future Features & Enhancements

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

## Potential Enhancements

### 2. Web Dashboard
**Priority:** Low  
**Complexity:** High  
**Description:** Interactive web UI for visualizing spending, managing manual reviews, and querying budgets.

### 3. Budget Alerts & Notifications
**Priority:** Low  
**Complexity:** Low  
**Description:** Email/SMS alerts when approaching category budget limits.

### 4. Recurring Transaction Detection
**Priority:** Medium  
**Complexity:** Medium  
**Description:** Auto-detect subscriptions and recurring payments (Netflix, gym, etc.).

### 5. Multi-Currency Support
**Priority:** Low  
**Complexity:** Low  
**Description:** Handle statements with foreign transactions and currency conversion.

### 6. Export to Quickbooks/Mint
**Priority:** Low  
**Complexity:** Medium  
**Description:** Export processed transactions to popular financial software.

### 7. Receipt Attachment Linking
**Priority:** Low  
**Complexity:** Medium  
**Description:** Link scanned receipts to transactions for record-keeping.

### 8. Spending Prediction Model
**Priority:** Low  
**Complexity:** High  
**Description:** ML model to predict future spending based on historical patterns.

---

## Recently Completed ✓
- Category validation with LLM + fuzzy matching
- Automatic pattern learning from manual classifications
- Payment app distinction from uncategorized transactions
- Cross-statement transfer detection
- Lightweight `--manual-only` mode for quick updates
- Investment category support
