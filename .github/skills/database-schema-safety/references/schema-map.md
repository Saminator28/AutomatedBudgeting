# Schema Map

## Schema Owners
- Table definitions live in [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py).
- Engine creation and startup migration logic live in [src/database/session.py](/home/desktop/Documents/AutomatedBudgeting/src/database/session.py).
- Most write-side behavior, seed logic, and backfills live in [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py).
- Backend consumers are concentrated in [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py) plus route modules under [src/ui/backend/routes](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes).

## Core Tables
- `transactions`: primary ledger for expenses, income, and transfer-tagged rows.
- `merchant_metadata`: learned merchant attributes.
- `transfers`: derived investment and transfer movement rows.
- `investment_keywords`, `income_keywords`, `ignore_keywords`, `payment_app_keywords`, `transfer_keywords`: DB-backed editable keyword lists.
- `institution_cache`: statement header fingerprint to institution mapping.
- `auto_deleted_transactions`: audit and whitelist store for auto-filtered rows.
- `merchant_rules`: merchant-level forced action overrides.
- `budget_goals`, `budget_settings`, `budget_history`, `budget_goals_monthly`: budget planning and history tables.
- `config_categories`: live category list and parent-child hierarchy.

## High-Value Relationships
- `config_categories` drives category lists surfaced by the API and used by the UI.
- Keyword tables are reloaded into shared in-memory lists by helpers in [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py).
- `transactions` writes often trigger transfer rebuilds into `transfers`.
- `auto_deleted_transactions` and `merchant_rules` affect whether rows remain visible as expenses/income or are filtered/restored.
- Budget routes in [src/ui/backend/routes/analytics.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/analytics.py) depend on the budget tables being present and shaped as current code expects.

## Practical Ownership By Concern
- Hashing and dedupe: [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py)
- Startup table creation and additive migrations: [src/database/session.py](/home/desktop/Documents/AutomatedBudgeting/src/database/session.py)
- Category list and hierarchy edits: [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py), [src/ui/backend/routes/expenses.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/expenses.py), [src/ui/src/SettingsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/SettingsTab.js)
- Auto-filter/whitelist flows: [src/ui/backend/routes/settings.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/settings.py)
- Merchant override rules: [src/ui/backend/routes/keywords.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/keywords.py)
