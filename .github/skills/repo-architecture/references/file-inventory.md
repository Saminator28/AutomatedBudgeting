# File Inventory

This inventory is grouped by directory and reflects the current tracked repository layout.

## Root
- [.dockerignore](/home/desktop/Documents/AutomatedBudgeting/.dockerignore): Docker ignore patterns.
- [.gitignore](/home/desktop/Documents/AutomatedBudgeting/.gitignore): Git ignore patterns.
- [Dockerfile](/home/desktop/Documents/AutomatedBudgeting/Dockerfile): App image build, Python deps, React build, uvicorn launch.
- [LICENSE](/home/desktop/Documents/AutomatedBudgeting/LICENSE): Project license.
- [Makefile](/home/desktop/Documents/AutomatedBudgeting/Makefile): Operator shortcuts for build, up, logs, processing, aggregation, testing.
- [README.md](/home/desktop/Documents/AutomatedBudgeting/README.md): End-user install and usage guide.
- [requirements.txt](/home/desktop/Documents/AutomatedBudgeting/requirements.txt): Python dependencies.
- [docker-compose.yml](/home/desktop/Documents/AutomatedBudgeting/docker-compose.yml): Base compose service definition.
- [docker-compose.linux.yml](/home/desktop/Documents/AutomatedBudgeting/docker-compose.linux.yml): Linux host-network override for Ollama reachability.
- [docker-entrypoint.sh](/home/desktop/Documents/AutomatedBudgeting/docker-entrypoint.sh): Startup probe for Ollama and model availability.
- [docker-setup.sh](/home/desktop/Documents/AutomatedBudgeting/docker-setup.sh): Interactive Docker setup helper.

## GitHub Metadata
- [.github/workflows/release.yml](/home/desktop/Documents/AutomatedBudgeting/.github/workflows/release.yml): Release-triggered CI job that installs deps, runs tests if present, and uploads a test report.

## AI Repo Skill Pack
- [.github/skills/repo-architecture/SKILL.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/repo-architecture/SKILL.md): Architecture and navigation skill entrypoint.
- [.github/skills/repo-architecture/references/overview.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/repo-architecture/references/overview.md): Runtime architecture and subsystem map.
- [.github/skills/repo-architecture/references/current-state-notes.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/repo-architecture/references/current-state-notes.md): Drift notes and current-code truths.
- [.github/skills/repo-architecture/references/file-inventory.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/repo-architecture/references/file-inventory.md): This file.
- [.github/skills/statement-processing/SKILL.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/statement-processing/SKILL.md): Statement ingest and persistence skill entrypoint.
- [.github/skills/statement-processing/references/pipeline.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/statement-processing/references/pipeline.md): PDF-to-DB ingest pipeline.
- [.github/skills/statement-processing/references/persistence-and-learning.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/statement-processing/references/persistence-and-learning.md): DB write, correction, and learning behavior.
- [.github/skills/dashboard-api-surface/SKILL.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/dashboard-api-surface/SKILL.md): UI and API surface skill entrypoint.
- [.github/skills/dashboard-api-surface/references/ui-and-routes.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/dashboard-api-surface/references/ui-and-routes.md): React/FastAPI mapping.
- [.github/skills/dashboard-api-surface/references/analytics-and-chat.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/dashboard-api-surface/references/analytics-and-chat.md): Analytics and chatbot stack.
- [.github/skills/database-schema-safety/SKILL.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/database-schema-safety/SKILL.md): Database and migration-safe editing skill entrypoint.
- [.github/skills/database-schema-safety/references/schema-map.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/database-schema-safety/references/schema-map.md): Current table ownership and dependencies.
- [.github/skills/database-schema-safety/references/migration-workflow.md](/home/desktop/Documents/AutomatedBudgeting/.github/skills/database-schema-safety/references/migration-workflow.md): Current schema evolution workflow.
- [.github/prompts/map-ui-action-to-backend.prompt.md](/home/desktop/Documents/AutomatedBudgeting/.github/prompts/map-ui-action-to-backend.prompt.md): Prompt for tracing a dashboard interaction to backend ownership.
- [.github/prompts/plan-database-schema-change.prompt.md](/home/desktop/Documents/AutomatedBudgeting/.github/prompts/plan-database-schema-change.prompt.md): Prompt for planning or implementing migration-safe DB changes.
- [.github/prompts/trace-statement-processing-bug.prompt.md](/home/desktop/Documents/AutomatedBudgeting/.github/prompts/trace-statement-processing-bug.prompt.md): Prompt for tracing import and parsing defects.

## Config
- [config/llm_models.json](/home/desktop/Documents/AutomatedBudgeting/config/llm_models.json): Current model selection and role notes for the primary, secondary, and financial-analysis models.

## Documentation
- [docs/README.md](/home/desktop/Documents/AutomatedBudgeting/docs/README.md): Documentation index.
- [docs/ARCHITECTURE.md](/home/desktop/Documents/AutomatedBudgeting/docs/ARCHITECTURE.md): System architecture narrative.
- [docs/CATEGORIZATION.md](/home/desktop/Documents/AutomatedBudgeting/docs/CATEGORIZATION.md): Categorization pipeline narrative.
- [docs/CHATBOT_PIPELINE.md](/home/desktop/Documents/AutomatedBudgeting/docs/CHATBOT_PIPELINE.md): Two-model chatbot explanation.
- [docs/DASHBOARD.md](/home/desktop/Documents/AutomatedBudgeting/docs/DASHBOARD.md): Dashboard/API overview.
- [docs/DATABASE.md](/home/desktop/Documents/AutomatedBudgeting/docs/DATABASE.md): Database narrative.
- [docs/DEVELOPER_GUIDE.md](/home/desktop/Documents/AutomatedBudgeting/docs/DEVELOPER_GUIDE.md): Developer setup and local workflow.
- [docs/FUTURE_FEATURES.md](/home/desktop/Documents/AutomatedBudgeting/docs/FUTURE_FEATURES.md): Roadmap and planned architecture.
- [docs/LLM_MERCHANT_CLEANING.md](/home/desktop/Documents/AutomatedBudgeting/docs/LLM_MERCHANT_CLEANING.md): Merchant cleaning design.
- [docs/PARSING.md](/home/desktop/Documents/AutomatedBudgeting/docs/PARSING.md): Parsing pipeline narrative.

## Scripts
- [scripts/aggregate_monthly.py](/home/desktop/Documents/AutomatedBudgeting/scripts/aggregate_monthly.py): Reclassifies and aggregates persisted transactions.
- [scripts/launch_dashboard.sh](/home/desktop/Documents/AutomatedBudgeting/scripts/launch_dashboard.sh): Browser launcher helper.
- [scripts/process_monthly.py](/home/desktop/Documents/AutomatedBudgeting/scripts/process_monthly.py): Main import orchestration from statements to DB.
- [scripts/setup_monthly.py](/home/desktop/Documents/AutomatedBudgeting/scripts/setup_monthly.py): Statement folder setup helper.

## Core Python Packages
- [src/merchant_history.py](/home/desktop/Documents/AutomatedBudgeting/src/merchant_history.py): Learns merchant corrections from historical data.

### AI Analysis
- [src/ai_analysis/__init__.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/__init__.py): Package marker.
- [src/ai_analysis/budget_advisor.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/budget_advisor.py): Budget suggestions and category budget logic.
- [src/ai_analysis/chatbot_assistant.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/chatbot_assistant.py): Intent parsing, pandas-backed fact computation, finance response generation.
- [src/ai_analysis/forecaster.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/forecaster.py): Forecasts and trend analysis.
- [src/ai_analysis/insights_generator.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/insights_generator.py): Monthly insights generation.
- [src/ai_analysis/model_loader.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/model_loader.py): Ollama-backed financial model loader.
- [src/ai_analysis/model_loader_hf.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/model_loader_hf.py): Hugging Face financial model loader.
- [src/ai_analysis/outlier_detector.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/outlier_detector.py): Outlier detection and large purchase classification.

### AI Classification
- [src/ai_classification/__init__.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_classification/__init__.py): Package marker.
- [src/ai_classification/categorizer.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_classification/categorizer.py): Transaction categorization and fallback LLM use.

### Database
- [src/database/__init__.py](/home/desktop/Documents/AutomatedBudgeting/src/database/__init__.py): Package marker.
- [src/database/db_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/database/db_utils.py): Hashing, seeding, merchant rules, auto-delete logic, DB writers.
- [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py): SQLAlchemy table definitions.
- [src/database/session.py](/home/desktop/Documents/AutomatedBudgeting/src/database/session.py): Engine creation and schema initialization.

### Statement Parser
- [src/statement_parser/__init__.py](/home/desktop/Documents/AutomatedBudgeting/src/statement_parser/__init__.py): Package exports.
- [src/statement_parser/llm_utils.py](/home/desktop/Documents/AutomatedBudgeting/src/statement_parser/llm_utils.py): Ollama REST helpers and merchant cleaning ensemble.
- [src/statement_parser/parser.py](/home/desktop/Documents/AutomatedBudgeting/src/statement_parser/parser.py): Statement parsing logic and heuristics.
- [src/statement_parser/pdf_extractor.py](/home/desktop/Documents/AutomatedBudgeting/src/statement_parser/pdf_extractor.py): Text extraction with OCR fallback.

## Backend
- [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py): Shared DB access, paths, in-memory job state, keyword reloads, transfer rebuild helpers.
- [src/ui/backend/export_excel.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/export_excel.py): Excel export endpoint.
- [src/ui/backend/main.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/main.py): FastAPI bootstrap, middleware, router registration, static serving.

### Backend Routes
- [src/ui/backend/routes/__init__.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/__init__.py): Route package marker.
- [src/ui/backend/routes/analytics.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/analytics.py): Insights, forecasts, budgets, and chat endpoints.
- [src/ui/backend/routes/expenses.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/expenses.py): Expense browse/edit/category/manual transaction endpoints.
- [src/ui/backend/routes/income.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/income.py): Income views and reclassification endpoints.
- [src/ui/backend/routes/keywords.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/keywords.py): Keyword and merchant-rule CRUD endpoints.
- [src/ui/backend/routes/settings.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/settings.py): Auto-filter and whitelist endpoints.
- [src/ui/backend/routes/statements.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/statements.py): Statement upload, delete, process, and job status endpoints.
- [src/ui/backend/routes/transfers.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/transfers.py): Transfer list and manual transfer endpoints.

## Frontend
- [src/ui/package.json](/home/desktop/Documents/AutomatedBudgeting/src/ui/package.json): React package manifest.
- [src/ui/package-lock.json](/home/desktop/Documents/AutomatedBudgeting/src/ui/package-lock.json): Locked frontend dependency graph.
- [src/ui/public/index.html](/home/desktop/Documents/AutomatedBudgeting/src/ui/public/index.html): HTML shell for the SPA.
- [src/ui/src/App.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/App.js): Main dashboard shell, month selection, uploads, and cross-tab orchestration.
- [src/ui/src/index.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/index.js): React entrypoint.
- [src/ui/src/InsightsPanel.css](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/InsightsPanel.css): Styling for the insights-heavy dashboard surface.
- [src/ui/src/InsightsPanel.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/InsightsPanel.js): Insights, budgets, forecasts, report card, and chatbot UI.
- [src/ui/src/SettingsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/SettingsTab.js): Settings and keyword/category management UI.
- [src/ui/src/TransactionsTab.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/TransactionsTab.js): Transactions table, inline edits, manual transactions, and review flow.

## Tracked Runtime Artifacts In Tree
- [logs/llm_prompt_debug.txt](/home/desktop/Documents/AutomatedBudgeting/logs/llm_prompt_debug.txt): Prompt/debug log checked into the repo tree.
