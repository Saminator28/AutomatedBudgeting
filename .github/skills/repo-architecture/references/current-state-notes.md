# Current-State Notes

These notes capture the current code reality that future AI work should prefer over older narrative docs when they disagree.

## Code Over Docs: Important Drift
- Keyword lists and categories are DB-backed in the live app, even though multiple docs still describe JSON config files such as `config/categories.json`, `config/income_keywords.json`, `config/payment_apps.json`, and `config/transfer_keywords.json`.
- The only actively tracked config file in the current tree for AI model selection is [config/llm_models.json](/home/desktop/Documents/AutomatedBudgeting/config/llm_models.json).
- The frontend codebase currently consists of [src/ui/src/App.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/App.js), [src/ui/src/InsightsPanel.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/InsightsPanel.js), [src/ui/src/SettingsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/SettingsTab.js), and [src/ui/src/TransactionsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/TransactionsTab.js). Older docs mention `OverviewTab.js`, `BudgetTab.js`, `StatementsTab.js`, and `InvestmentsTab.js`, but those are not present in the current tree.
- Linux Docker behavior now relies on [docker-compose.linux.yml](/home/desktop/Documents/AutomatedBudgeting/docker-compose.linux.yml), which switches the app to `network_mode: host` and sets `OLLAMA_HOST=http://localhost:11434`. The base compose file does not itself use host mode.

## Backend Reality Checks
- Route modules live under [src/ui/backend/routes](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes), but [src/ui/backend/export_excel.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/export_excel.py) also registers an API route: `GET /api/transactions/export`.
- Write-endpoint auth is optional and enforced centrally in [src/ui/backend/main.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/main.py) through `AUTOBUDGET_API_KEY`.
- Shared mutable keyword lists, DB access helpers, and in-memory background job state live in [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py).

## Database Reality Checks
- The schema in [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py) is broader than older docs suggest. In addition to transactions and keyword tables, it includes `auto_deleted_transactions`, `merchant_rules`, `budget_goals`, `budget_settings`, `budget_history`, `budget_goals_monthly`, and `config_categories`.
- Categories are sourced from `config_categories` rows, not just a flat JSON list.
- Transfer and whitelist behavior uses `auto_deleted_transactions` plus settings endpoints, not just static transfer keyword matching.

## Frontend/Backend Mismatch To Watch
- [src/ui/src/TransactionsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/TransactionsTab.js) still references `/api/manual-review` and `/api/manual-review/classify`.
- A repo-wide search in current backend Python files does not show matching backend endpoints for those paths. Treat this as a drift or unfinished surface before assuming the endpoints exist.
- Many frontend fetches use explicit `http://localhost:8000/...` URLs rather than a shared relative API base. Any deployment or proxy changes need a full grep of the frontend.

## Networking Notes
- The container entrypoint in [docker-entrypoint.sh](/home/desktop/Documents/AutomatedBudgeting/docker-entrypoint.sh) probes several candidate Ollama URLs and exports the working one for child processes.
- On Linux, the compose override is the current primary workaround for host Ollama instances that only listen on `127.0.0.1:11434`.

## Safe Source Priority
1. Source code in `src/`, `scripts/`, and Docker files.
2. This skill pack and its references.
3. Existing docs under `docs/`.
4. Comments in README files when they conflict with code.
