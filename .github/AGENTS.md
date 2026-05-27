# AutomatedBudgeting Agent Notes

AutomatedBudgeting is a local-first budgeting application built from these main layers:
- FastAPI backend in `src/ui/backend/`
- React frontend in `src/ui/src/`
- SQLite persistence in `src/database/`
- Statement ingestion in `src/statement_parser/` and `scripts/process_monthly.py`
- Local Ollama integrations for merchant cleaning, categorization fallback, insights, and chat

Before making substantial changes, prefer the repo skill that matches the task:
- `repo-architecture`: project structure, owning files, runtime topology, current-state drift notes
- `statement-processing`: PDF import path, merchant cleaning, categorization, DB writes, re-import behavior
- `dashboard-api-surface`: React tabs, FastAPI routes, analytics, budgets, chatbot, frontend/backend mapping
- `database-schema-safety`: SQLAlchemy models, SQLite schema, additive migrations, DB-backed config tables, and migration-safe persistence edits

Important current-state guidance:
- Categories and keyword lists are DB-backed in the current code path even though some docs still describe JSON config files.
- Linux Docker runs with a compose override that uses host networking for host Ollama reachability.
- Some older docs mention frontend files that are no longer present; use the actual files under `src/ui/src/` as the source of truth.
- `TransactionsTab.js` references `/api/manual-review` endpoints that are not present in the current backend route tree. Confirm ownership before assuming those endpoints exist.

Reusable prompts are available under `.github/prompts/` for common workflows such as tracing statement-processing bugs, mapping UI actions to backend ownership, and planning schema changes safely.

## Repo-Wide Instructions

- Prefer current source code over prose docs when they conflict. If code and docs disagree, trust the active files under `src/`, `scripts/`, and Docker config, then update the docs when practical.
- Use the repo skills as the first navigation layer:
  - `repo-architecture` for ownership and current-state drift
  - `statement-processing` for import, parsing, cleaning, and categorization
  - `dashboard-api-surface` for React/FastAPI/UI wiring
  - `database-schema-safety` for schema and DB-backed configuration changes
- Treat categories, keywords, merchant rules, auto-filters, and budget settings as DB-backed runtime state. Do not assume checked-in JSON config files are the source of truth unless the code still reads them.

## Validation Guidance

- For Docker or compose changes:
  - Validate shell scripts with `bash -n` when editing entrypoints or setup helpers.
  - Validate compose rendering with `docker compose config` or the Make target dry run.
  - Prefer `make up`, `make down`, `make logs`, and `make status` for end-to-end checks because the Makefile contains platform-aware compose selection.
- For Ollama connectivity changes:
  - Check host availability first with `curl http://localhost:11434/api/tags`.
  - Then check runtime behavior with `make logs` or the narrowest container-side connectivity check.
  - On Linux, remember the repo uses `docker-compose.linux.yml` with host networking so loopback-bound host Ollama instances remain reachable.
- For documentation changes:
  - Remove stale references instead of layering new text around them.
  - Prefer wording that matches the current runtime path: DB-backed settings, actual route names, actual frontend files, and current compose behavior.
