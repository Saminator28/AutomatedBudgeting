# UI And Routes Map

## Backend Bootstrap
- FastAPI bootstrap: [src/ui/backend/main.py](/src/ui/backend/main.py)
- Shared backend state and helpers: [src/ui/backend/deps.py](/src/ui/backend/deps.py)
- Router registration order in main:
  - export Excel
  - income
  - expenses
  - transfers
  - statements
  - keywords
  - analytics
  - settings

## Current Frontend Files
- [src/ui/src/index.js](/src/ui/src/index.js): React mount.
- [src/ui/src/App.js](/src/ui/src/App.js): Main shell, month selection, statement upload/process flow, cross-tab state.
- [src/ui/src/TransactionsTab.js](/src/ui/src/TransactionsTab.js): Transaction list, edits, manual rows, some review/reclassification flows.
- [src/ui/src/SettingsTab.js](/src/ui/src/SettingsTab.js): Keyword, category, merchant rule, and auto-filter UI.
- [src/ui/src/InsightsPanel.js](/src/ui/src/InsightsPanel.js): Overview analytics, budgets, forecasts, report card, committed costs, and chatbot UI.
- [src/ui/src/InsightsPanel.css](/src/ui/src/InsightsPanel.css): Shared visual styling for the insights-heavy surface.

## Route Modules And Ownership
- [src/ui/backend/routes/statements.py](/src/ui/backend/routes/statements.py)
  - `GET /api/statements`
  - `POST /api/statements/{month}/upload`
  - `DELETE /api/statements/{month}/{filename}`
  - `DELETE /api/statements/{month}`
  - `POST /api/statements/{month}/process`
  - `GET /api/jobs/{job_id}`
  - `POST /api/aggregate`
- [src/ui/backend/routes/expenses.py](/src/ui/backend/routes/expenses.py)
  - `GET /api/one-time-expenses`
  - `POST /api/expense/label`
  - `GET /api/available-months`
  - `GET /api/all-expenses`
  - `DELETE /api/transactions/{tx_hash}`
  - `PATCH /api/expense/edit`
  - `GET /api/categories/full`
  - `PUT /api/categories`
  - `GET /api/categories`
  - `GET /api/category-subcategories`
  - `GET /api/expense-categories`
  - `GET /api/expenses-by-month`
  - `GET /api/manual-transactions`
  - `POST /api/manual-transactions`
  - `DELETE /api/manual-transactions/{tx_id}`
- [src/ui/backend/routes/income.py](/src/ui/backend/routes/income.py)
  - `GET /api/income-by-month`
  - `GET /api/income-breakdown`
  - `GET /api/income-entries`
  - `POST /api/income/label`
  - `POST /api/income/reclassify-as-reimbursement`
  - `POST /api/expense/reclassify-as-income`
- [src/ui/backend/routes/transfers.py](/src/ui/backend/routes/transfers.py)
  - `GET /api/transfers`
  - `POST /api/transfers/label`
  - `POST /api/transfers/manual`
  - `DELETE /api/transfers/manual/{tx_id}`
- [src/ui/backend/routes/keywords.py](/src/ui/backend/routes/keywords.py)
  - keyword CRUD for investment, income, ignore, payment-app, and transfer tables
  - merchant-rule CRUD under `/api/merchant-rules`
- [src/ui/backend/routes/settings.py](/src/ui/backend/routes/settings.py)
  - `GET /api/auto-filters`
  - `PATCH /api/auto-filters/{record_id}/whitelist`
  - `DELETE /api/auto-filters/{record_id}`
- [src/ui/backend/export_excel.py](/src/ui/backend/export_excel.py)
  - `GET /api/transactions/export`
- [src/ui/backend/routes/analytics.py](/src/ui/backend/routes/analytics.py)
  - insights, forecasts, budget goals/history, committed costs, category history, chat availability, and chat response endpoints

## Frontend To Backend Mapping
- [src/ui/src/App.js](/src/ui/src/App.js)
  - loads categories, months, investment keywords, expenses by month, income by month, statements, transfers, and income entries
  - uploads statement files and polls `/api/jobs/{job_id}` during processing
  - applies labels through `/api/expense/label` and `/api/transfers/label`
- [src/ui/src/TransactionsTab.js](/src/ui/src/TransactionsTab.js)
  - reads manual transactions, months, income entries, and expenses
  - edits expenses through `PATCH /api/expense/edit`
  - reclassifies income and expenses through income routes
  - deletes rows through `/api/transactions/{tx_hash}`
  - creates and deletes manual transactions
  - exports transactions through `/api/transactions/export`
- [src/ui/src/SettingsTab.js](/src/ui/src/SettingsTab.js)
  - manages auto-filters, whitelist toggles, merchant rules, all keyword tables, and categories
- [src/ui/src/InsightsPanel.js](/src/ui/src/InsightsPanel.js)
  - reads insights, forecast, trends, budget suggestions, budget goals, budget history, category history, committed costs, rollover, one-time expenses, and chat availability
  - posts budget goals, budget debrief, and chat messages

## Operational Notes
- CORS allows `http://localhost:3000` in [src/ui/backend/main.py](/src/ui/backend/main.py) for local React dev.
- Write-endpoint auth is optional through `AUTOBUDGET_API_KEY`.
- Background job state is stored in memory in [src/ui/backend/deps.py](/src/ui/backend/deps.py); restarting the backend clears job metadata.
- The frontend frequently hardcodes `http://localhost:8000` rather than using a single configurable API base.

## Drift Note
- [src/ui/src/TransactionsTab.js](/src/ui/src/TransactionsTab.js) references `/api/manual-review` endpoints that are not present in the current backend route search results. Treat that code path as stale or incomplete until confirmed otherwise.
