# Migration Workflow

## Current Migration Strategy
This repo does not use Alembic or a dedicated migration framework.

The current safe path is:
1. Define or update tables in [src/database/models.py](/src/database/models.py).
2. Add additive, idempotent migration statements in [src/database/session.py](/src/database/session.py) inside `init_db()`.
3. Backfill or reconcile data in the same startup path or in narrowly owned helpers such as [src/database/db_utils.py](/src/database/db_utils.py).
4. Validate startup and the narrowest route or script that touches the changed table.

## Safe Edit Rules
- Prefer additive columns and new tables.
- Keep `ALTER TABLE` operations idempotent; this repo currently tolerates duplicate-column failures by catching exceptions and continuing.
- When a new column needs existing data, add a small backfill statement after the column migration.
- Avoid destructive schema edits unless the repo can fully regenerate the table from source inputs and the user explicitly wants that path.
- Preserve `user_corrected` data semantics in `transactions` when changing import behavior.

## Files To Update Together
- New column or table shape: [src/database/models.py](/src/database/models.py)
- Startup creation or backfill: [src/database/session.py](/src/database/session.py)
- Write/read code depending on the new field: [src/database/db_utils.py](/src/database/db_utils.py), [src/ui/backend/deps.py](/src/ui/backend/deps.py), or the owning route file
- UI forms or API contracts when surfaced to users: [src/ui/src](/src/ui/src) and the owning FastAPI route

## Validation Suggestions
- Backend startup validation: run the app or import `init_db()` through a narrow command.
- Route validation: hit the specific endpoint whose query or insert path changed.
- Import-path validation: run `make process MONTH=...` if schema changes touch `transactions`, transfer rebuilds, or import metadata.
- If a destructive reset is acceptable, deleting `src/ui/data/budget.db` and re-importing statements remains the repo fallback, but only use that path intentionally.
