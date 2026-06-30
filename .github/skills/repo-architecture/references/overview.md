# AutomatedBudgeting Overview

## Current Runtime Topology
- Single Python application image built from [Dockerfile](/Dockerfile).
- FastAPI app boots from [src/ui/backend/main.py](/src/ui/backend/main.py) and serves both `/api/*` and the built React app.
- React source lives under [src/ui/src](/src/ui/src); production build is generated during Docker build with `npm run build`.
- Persistent app data lives in [src/ui/data](/src/ui/data): statement folders, transfer labels JSON, and `budget.db` at runtime.
- SQLite is the authoritative store. The API reads and writes through DB helpers, not through CSV fallbacks.
- Ollama runs outside the app container and is contacted over HTTP. Model selection comes from [config/llm_models.json](/config/llm_models.json).

## Runtime Entry Points
- Docker start path: [docker-compose.yml](/docker-compose.yml) plus [docker-compose.linux.yml](/docker-compose.linux.yml) on Linux.
- Container bootstrap: [docker-entrypoint.sh](/docker-entrypoint.sh).
- Backend app: [src/ui/backend/main.py](/src/ui/backend/main.py).
- CLI import path: [scripts/process_monthly.py](/scripts/process_monthly.py).
- Re-aggregation path: [scripts/aggregate_monthly.py](/scripts/aggregate_monthly.py).
- Common operator commands: [Makefile](/Makefile).

## Core Subsystems
- Statement ingestion:
  - [src/statement_parser/pdf_extractor.py](/src/statement_parser/pdf_extractor.py)
  - [src/statement_parser/parser.py](/src/statement_parser/parser.py)
  - [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py)
- Categorization and learning:
  - [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py)
  - [src/merchant_history.py](/src/merchant_history.py)
  - [src/database/db_utils.py](/src/database/db_utils.py)
- Analysis and AI features:
  - [src/ai_analysis/insights_generator.py](/src/ai_analysis/insights_generator.py)
  - [src/ai_analysis/forecaster.py](/src/ai_analysis/forecaster.py)
  - [src/ai_analysis/budget_advisor.py](/src/ai_analysis/budget_advisor.py)
  - [src/ai_analysis/chatbot_assistant.py](/src/ai_analysis/chatbot_assistant.py)
  - [src/ai_analysis/model_loader.py](/src/ai_analysis/model_loader.py)
  - [src/ai_analysis/model_loader_hf.py](/src/ai_analysis/model_loader_hf.py)
- Persistence:
  - [src/database/models.py](/src/database/models.py)
  - [src/database/session.py](/src/database/session.py)
  - [src/database/db_utils.py](/src/database/db_utils.py)
- Web surface:
  - Backend routing in [src/ui/backend/routes](/src/ui/backend/routes)
  - Shared backend state in [src/ui/backend/deps.py](/src/ui/backend/deps.py)
  - Frontend components in [src/ui/src](/src/ui/src)

## End-To-End Data Flow
1. PDFs are uploaded or placed under `src/ui/data/statements/YYYY-MM/`.
2. [scripts/process_monthly.py](/scripts/process_monthly.py) orchestrates parsing and categorization.
3. [src/statement_parser/pdf_extractor.py](/src/statement_parser/pdf_extractor.py) extracts text with OCR fallback.
4. [src/statement_parser/parser.py](/src/statement_parser/parser.py) detects bank/account context and extracts transaction rows.
5. [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py) cleans merchant names and institution hints through Ollama.
6. [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py) applies pattern rules, payment-app/manual-review logic, and LLM fallback.
7. [src/database/db_utils.py](/src/database/db_utils.py) writes transactions and related metadata into SQLite.
8. FastAPI endpoints read those DB tables through [src/ui/backend/deps.py](/src/ui/backend/deps.py) and route modules.
9. React fetches those endpoints and renders dashboard views.

## High-Value Files To Start With
- Infra or startup issue: [Makefile](/Makefile), [docker-compose.yml](/docker-compose.yml), [docker-compose.linux.yml](/docker-compose.linux.yml), [docker-entrypoint.sh](/docker-entrypoint.sh)
- API behavior: [src/ui/backend/main.py](/src/ui/backend/main.py), [src/ui/backend/deps.py](/src/ui/backend/deps.py), route module under [src/ui/backend/routes](/src/ui/backend/routes)
- Import defects: [scripts/process_monthly.py](/scripts/process_monthly.py), [src/statement_parser/parser.py](/src/statement_parser/parser.py)
- Category or merchant defects: [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py), [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py), [src/database/db_utils.py](/src/database/db_utils.py)
- Analytics or chatbot defects: [src/ui/backend/routes/analytics.py](/src/ui/backend/routes/analytics.py), [src/ai_analysis/chatbot_assistant.py](/src/ai_analysis/chatbot_assistant.py)

## Common Commands
- Build and start: `make build`, `make up`
- Stop: `make down`
- Logs: `make logs`
- Import a month: `make process MONTH=YYYY-MM`
- Re-aggregate: `make aggregate`
- Open container shell: `make shell`
- Frontend local dev: `cd src/ui && npm install && npm start`
- Backend local dev: `uvicorn src.ui.backend.main:app --reload --host 0.0.0.0 --port 8000`
