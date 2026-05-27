# Persistence And Learning

## Database Tables Most Relevant To Imports
- `transactions`: authoritative expense, income, and transfer-adjacent rows.
- `merchant_metadata`: normalized merchant-level learned flags and tags.
- `transfers`: derived transfer and investment movement rows.
- `investment_keywords`, `income_keywords`, `ignore_keywords`, `payment_app_keywords`, `transfer_keywords`: live keyword sources edited through the UI.
- `institution_cache`: stable statement-header to institution mapping.
- `auto_deleted_transactions`: tracks automatically removed rows and whitelist state.
- `merchant_rules`: user-defined merchant overrides for force-income, force-expense, or ignore behavior.
- `config_categories`: live category names and hierarchy.

## Write Ownership
- Schema and tables: [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py)
- Engine and `init_db()`: [src/database/session.py](/home/desktop/Documents/AutomatedBudgeting/src/database/session.py)
- Hashing, seeding, month writes, transfer writes, auto-delete logging, rule application: [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py)

## Stable Identity And Re-Import Behavior
- `transactions.tx_hash` is the stable deduplication key.
- Hash construction is defined in [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py) and includes month, date, normalized place, amount in cents, transaction type, statement name, and sequence.
- Re-imports are designed to avoid duplicate rows and preserve manual edits.
- `user_corrected` rows are preserved or restored after month rewrites so users do not lose manual merchant, category, or label fixes.

## Learning Surfaces
- Merchant learning:
  - [src/merchant_history.py](/home/desktop/Documents/AutomatedBudgeting/src/merchant_history.py)
  - `merchant_metadata`
- Rule-based persistent overrides:
  - `merchant_rules`
  - CRUD endpoints in [src/ui/backend/routes/keywords.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/keywords.py)
- Auto-delete and whitelist recovery:
  - `auto_deleted_transactions`
  - endpoints in [src/ui/backend/routes/settings.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/settings.py)

## Post-Import Processing
- Month writes happen in `write_month_to_db()` inside [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py).
- Transfer rows are rebuilt with `_rebuild_transfers_for_month()` in [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py).
- Re-aggregation runs through [scripts/aggregate_monthly.py](/home/desktop/Documents/AutomatedBudgeting/scripts/aggregate_monthly.py), which recomputes higher-level classifications and writes results back into the database.

## Settings And Categories Are Live Data
- Categories are not a static JSON file in the current code path. They are stored in `config_categories` and surfaced through [src/ui/backend/routes/expenses.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/expenses.py) plus [src/ui/src/SettingsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/SettingsTab.js).
- Keyword tables are seeded at startup if empty, then reloaded into shared in-memory lists through helpers in [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py).

## Where To Patch Specific Persistence Bugs
- Wrong schema, missing columns, or startup table creation issue: [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py), [src/database/session.py](/home/desktop/Documents/AutomatedBudgeting/src/database/session.py)
- Month import overwrote user changes: [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py)
- Transfer list inconsistent with transactions: [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py), [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py), [src/ui/backend/routes/transfers.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/transfers.py)
- Keywords or categories changed in UI but not reflected at runtime: [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py), [src/ui/backend/routes/keywords.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/keywords.py), [src/ui/backend/routes/expenses.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/expenses.py)
