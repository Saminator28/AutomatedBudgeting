# File Inventory

This inventory is grouped by directory and reflects the current tracked repository layout.

## Root
- [.dockerignore](/.dockerignore): Docker ignore patterns.
- [.gitignore](/.gitignore): Git ignore patterns.
- [Dockerfile](/Dockerfile): App image build, Python deps, React build, uvicorn launch.
- [LICENSE](/LICENSE): Project license.
- [Makefile](/Makefile): Operator shortcuts for build, up, logs, processing, aggregation, testing.
- [README.md](/README.md): End-user install and usage guide.
- [requirements.txt](/requirements.txt): Python dependencies.
- [docker-compose.yml](/docker-compose.yml): Base compose service definition.
- [docker-compose.linux.yml](/docker-compose.linux.yml): Linux host-network override for Ollama reachability.
- [docker-entrypoint.sh](/docker-entrypoint.sh): Startup probe for Ollama and model availability.
- [docker-setup.sh](/docker-setup.sh): Interactive Docker setup helper.

## GitHub Metadata
- [.github/workflows/release.yml](/.github/workflows/release.yml): Release-triggered CI job that installs deps, runs tests if present, and uploads a test report.

## AI Repo Skill Pack
- [.github/skills/repo-architecture/SKILL.md](/.github/skills/repo-architecture/SKILL.md): Architecture and navigation skill entrypoint.
- [.github/skills/repo-architecture/references/overview.md](/.github/skills/repo-architecture/references/overview.md): Runtime architecture and subsystem map.
- [.github/skills/repo-architecture/references/current-state-notes.md](/.github/skills/repo-architecture/references/current-state-notes.md): Drift notes and current-code truths.
- [.github/skills/repo-architecture/references/file-inventory.md](/.github/skills/repo-architecture/references/file-inventory.md): This file.
- [.github/skills/statement-processing/SKILL.md](/.github/skills/statement-processing/SKILL.md): Statement ingest and persistence skill entrypoint.
- [.github/skills/statement-processing/references/pipeline.md](/.github/skills/statement-processing/references/pipeline.md): PDF-to-DB ingest pipeline.
- [.github/skills/statement-processing/references/persistence-and-learning.md](/.github/skills/statement-processing/references/persistence-and-learning.md): DB write, correction, and learning behavior.
- [.github/skills/dashboard-api-surface/SKILL.md](/.github/skills/dashboard-api-surface/SKILL.md): UI and API surface skill entrypoint.
- [.github/skills/dashboard-api-surface/references/ui-and-routes.md](/.github/skills/dashboard-api-surface/references/ui-and-routes.md): React/FastAPI mapping.
- [.github/skills/dashboard-api-surface/references/analytics-and-chat.md](/.github/skills/dashboard-api-surface/references/analytics-and-chat.md): Analytics and chatbot stack.
- [.github/skills/database-schema-safety/SKILL.md](/.github/skills/database-schema-safety/SKILL.md): Database and migration-safe editing skill entrypoint.
- [.github/skills/database-schema-safety/references/schema-map.md](/.github/skills/database-schema-safety/references/schema-map.md): Current table ownership and dependencies.
- [.github/skills/database-schema-safety/references/migration-workflow.md](/.github/skills/database-schema-safety/references/migration-workflow.md): Current schema evolution workflow.
- [.github/prompts/map-ui-action-to-backend.prompt.md](/.github/prompts/map-ui-action-to-backend.prompt.md): Prompt for tracing a dashboard interaction to backend ownership.
- [.github/prompts/plan-database-schema-change.prompt.md](/.github/prompts/plan-database-schema-change.prompt.md): Prompt for planning or implementing migration-safe DB changes.
- [.github/prompts/trace-statement-processing-bug.prompt.md](/.github/prompts/trace-statement-processing-bug.prompt.md): Prompt for tracing import and parsing defects.

## Config
- [config/llm_models.json](/config/llm_models.json): Current model selection and role notes for the primary, secondary, and financial-analysis models.

## Documentation
- [docs/README.md](/docs/README.md): Documentation index.
- [docs/ARCHITECTURE.md](/docs/ARCHITECTURE.md): System architecture narrative.
- [docs/CATEGORIZATION.md](/docs/CATEGORIZATION.md): Categorization pipeline narrative.
- [docs/CHATBOT_PIPELINE.md](/docs/CHATBOT_PIPELINE.md): Two-model chatbot explanation.
- [docs/DASHBOARD.md](/docs/DASHBOARD.md): Dashboard/API overview.
- [docs/DATABASE.md](/docs/DATABASE.md): Database narrative.
- [docs/DEVELOPER_GUIDE.md](/docs/DEVELOPER_GUIDE.md): Developer setup and local workflow.
- [docs/FUTURE_FEATURES.md](/docs/FUTURE_FEATURES.md): Roadmap and planned architecture.
- [docs/LLM_MERCHANT_CLEANING.md](/docs/LLM_MERCHANT_CLEANING.md): Merchant cleaning design.
- [docs/PARSING.md](/docs/PARSING.md): Parsing pipeline narrative.

## Scripts
- [scripts/aggregate_monthly.py](/scripts/aggregate_monthly.py): Reclassifies and aggregates persisted transactions.
- [scripts/launch_dashboard.sh](/scripts/launch_dashboard.sh): Browser launcher helper.
- [scripts/process_monthly.py](/scripts/process_monthly.py): Main import orchestration from statements to DB.
- [scripts/setup_monthly.py](/scripts/setup_monthly.py): Statement folder setup helper.

## Core Python Packages
- [src/merchant_history.py](/src/merchant_history.py): Learns merchant corrections from historical data.

### AI Analysis
- [src/ai_analysis/__init__.py](/src/ai_analysis/__init__.py): Package marker.
- [src/ai_analysis/budget_advisor.py](/src/ai_analysis/budget_advisor.py): Budget suggestions and category budget logic.
- [src/ai_analysis/chatbot_assistant.py](/src/ai_analysis/chatbot_assistant.py): Intent parsing, pandas-backed fact computation, finance response generation.
- [src/ai_analysis/forecaster.py](/src/ai_analysis/forecaster.py): Forecasts and trend analysis.
- [src/ai_analysis/insights_generator.py](/src/ai_analysis/insights_generator.py): Monthly insights generation.
- [src/ai_analysis/model_loader.py](/src/ai_analysis/model_loader.py): Ollama-backed financial model loader.
- [src/ai_analysis/model_loader_hf.py](/src/ai_analysis/model_loader_hf.py): Hugging Face financial model loader.
- [src/ai_analysis/outlier_detector.py](/src/ai_analysis/outlier_detector.py): Outlier detection and large purchase classification.

### AI Classification
- [src/ai_classification/__init__.py](/src/ai_classification/__init__.py): Package marker.
- [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py): Transaction categorization and fallback LLM use.

### Database
- [src/database/__init__.py](/src/database/__init__.py): Package marker.
- [src/database/db_utils.py](/src/database/db_utils.py): Hashing, seeding, merchant rules, auto-delete logic, DB writers.
- [src/database/models.py](/src/database/models.py): SQLAlchemy table definitions.
- [src/database/session.py](/src/database/session.py): Engine creation and schema initialization.

### Statement Parser
- [src/statement_parser/__init__.py](/src/statement_parser/__init__.py): Package exports.
- [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py): Ollama REST helpers and merchant cleaning ensemble.
- [src/statement_parser/parser.py](/src/statement_parser/parser.py): Statement parsing logic and heuristics.
- [src/statement_parser/pdf_extractor.py](/src/statement_parser/pdf_extractor.py): Text extraction with OCR fallback.

## Backend
- [src/ui/backend/deps.py](/src/ui/backend/deps.py): Shared DB access, paths, in-memory job state, keyword reloads, transfer rebuild helpers.
- [src/ui/backend/export_excel.py](/src/ui/backend/export_excel.py): Excel export endpoint.
- [src/ui/backend/main.py](/src/ui/backend/main.py): FastAPI bootstrap, middleware, router registration, static serving.

### Backend Routes
- [src/ui/backend/routes/__init__.py](/src/ui/backend/routes/__init__.py): Route package marker.
- [src/ui/backend/routes/analytics.py](/src/ui/backend/routes/analytics.py): Insights, forecasts, budgets, and chat endpoints.
- [src/ui/backend/routes/expenses.py](/src/ui/backend/routes/expenses.py): Expense browse/edit/category/manual transaction endpoints.
- [src/ui/backend/routes/income.py](/src/ui/backend/routes/income.py): Income views and reclassification endpoints.
- [src/ui/backend/routes/keywords.py](/src/ui/backend/routes/keywords.py): Keyword and merchant-rule CRUD endpoints.
- [src/ui/backend/routes/settings.py](/src/ui/backend/routes/settings.py): Auto-filter and whitelist endpoints.
- [src/ui/backend/routes/statements.py](/src/ui/backend/routes/statements.py): Statement upload, delete, process, and job status endpoints.
- [src/ui/backend/routes/transfers.py](/src/ui/backend/routes/transfers.py): Transfer list and manual transfer endpoints.

## Frontend
- [src/ui/package.json](/src/ui/package.json): React package manifest.
- [src/ui/package-lock.json](/src/ui/package-lock.json): Locked frontend dependency graph.
- [src/ui/public/index.html](/src/ui/public/index.html): HTML shell for the SPA.
- [src/ui/src/App.js](/src/ui/src/App.js): Main dashboard shell, month selection, uploads, and cross-tab orchestration.
- [src/ui/src/index.js](/src/ui/src/index.js): React entrypoint.
- [src/ui/src/InsightsPanel.css](/src/ui/src/InsightsPanel.css): Styling for the insights-heavy dashboard surface.
- [src/ui/src/InsightsPanel.js](/src/ui/src/InsightsPanel.js): Insights, budgets, forecasts, report card, and chatbot UI.
- [src/ui/src/SettingsTab.js](/src/ui/src/SettingsTab.js): Settings and keyword/category management UI.
- [src/ui/src/TransactionsTab.js](/src/ui/src/TransactionsTab.js): Transactions table, inline edits, manual transactions, and review flow.

## Tracked Runtime Artifacts In Tree
- [logs/llm_prompt_debug.txt](/logs/llm_prompt_debug.txt): Prompt/debug log checked into the repo tree.
