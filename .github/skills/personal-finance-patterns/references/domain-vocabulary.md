# Domain Vocabulary for AutomatedBudgeting

Use this reference when reading or writing code that touches the `transactions` table, analytics routes, or any categorization/labeling logic. The definitions here are canonical for this codebase — they may differ from generic personal-finance terminology.

---

## transactions Table Fields

| Field | Type | Meaning in this repo |
|-------|------|----------------------|
| `tx_hash` | TEXT (primary key) | SHA-256 content hash of (date, merchant, amount, source_file). A collision means the row already exists — use INSERT OR IGNORE. |
| `date` | TEXT (ISO 8601) | The transaction date as parsed from the statement. Not the import date. |
| `place` | TEXT | Raw merchant string as it appeared on the statement, after minimal normalization. Preserved for audit. |
| `merchant` | TEXT | Cleaned merchant name after LLM or rule-based cleaning. Used for category rule matching. |
| `amount` | REAL | Absolute monetary value. Always positive. Sign/direction is encoded in `tx_type`. |
| `category` | TEXT | Assigned spending category (e.g., "Groceries", "Utilities"). Editable by the user. DB-backed — canonical list lives in the `categories` table, not a JSON file. |
| `tx_type` | TEXT | Controls how the transaction is counted in analytics. See tx_type values below. |
| `label` | TEXT | Free-form user annotation. Not used in any calculation. Optional. |
| `user_corrected` | INTEGER (0 or 1) | Set to 1 when the user manually edits this row. A field with `user_corrected = 1` must NEVER be overwritten by automation. |
| `source_file` | TEXT | Filename of the imported PDF. Used for provenance tracking and re-import detection. |
| `month` | TEXT (YYYY-MM) | Derived from `date`. Used as the primary key for monthly rollups and budget comparisons. |

---

## tx_type Values

| Value | Meaning | Counted in spending? | Counted in income? |
|-------|---------|---------------------|-------------------|
| `"expense"` | Normal spending | Yes | No |
| `"income"` | Money received (paycheck, interest, deposit) | No | Yes |
| `"transfer"` | Internal movement between own accounts | No | No |
| `"reimbursement"` | Expense later repaid by a third party | No (excluded) | No |
| `"investment"` | Investment account contribution or withdrawal | No (tracked separately) | No |
| `"ignored"` | Explicitly excluded row (zero-amount, balance row, parsing artifact) | No | No |

---

## Key DB-Backed State

These settings live in `budget.db`, not in JSON config files. Do not assume a checked-in file is the source of truth.

| Concept | Table | Notes |
|---------|-------|-------|
| Spending categories | `categories` | Canonical list. Editable via Settings UI. |
| Expense keywords | `expense_keywords` | Keywords used to classify expenses. |
| Income keywords | `income_keywords` | Keywords used to detect income rows. |
| Investment keywords | `investment_keywords` | Keywords used to detect investment rows. |
| Merchant rules | `merchant_rules` | Maps `merchant_key` → `category`. Applied before LLM. |
| Budget goals | `budget_goals` | Maps `category` → monthly spending target. User-set. |

---

## File-Backed State (Exceptions)

These are NOT DB-backed — they are the exceptions to the rule above:

| Concept | File | Notes |
|---------|------|-------|
| Transfer labels | `src/ui/data/transfer_labels.json` | Short list of known transfer merchant patterns. Loaded at runtime. |
| LLM model config | `config/llm_models.json` | Which Ollama models to use for each task. Edited by the user manually. |

---

## Other Key Terms

**`user_corrected` flag**: The single most important integrity invariant. If `user_corrected = 1` on any field, no automated process may overwrite it. Every write path must check this flag first.

**Merchant rule**: A row in `merchant_rules` mapping a lowercased cleaned merchant name (`merchant_key`) to a `category`. Applied as a deterministic shortcut before LLM categorization.

**Category**: A string like "Groceries" or "Utilities". The canonical list is in the `categories` table. When code reads available categories, it reads from the DB — not from a hardcoded list or JSON file.

**Budget goal**: A row in `budget_goals` mapping a `category` to a monthly spending target. Set by the user via the Settings UI. Not a JSON file.

**Statement source**: A PDF stored under `src/ui/data/statements/YYYY-MM/`. Once imported, the DB is the source of truth for transaction data — not the PDF.

**`tx_hash` stability**: The hash must be computed from stable inputs (date, merchant, amount, source_file) every time a given transaction is seen, regardless of import order or file rename. If the hash inputs change, deduplication breaks and cross-month overlap creates duplicate rows.
