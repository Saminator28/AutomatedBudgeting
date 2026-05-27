---
name: database-schema-safety
description: 'Use when working on SQLite schema, SQLAlchemy models, init_db migrations, DB-backed categories or keyword tables, budget tables, merchant rules, auto-deleted transactions, or migration-safe edits in AutomatedBudgeting.'
argument-hint: 'Ask for the table, migration, or schema-safe edit you need planned or implemented'
user-invocable: true
---

# Database Schema Safety

Use this skill when a task touches persistence, table definitions, DB-backed configuration, or migration-safe edits.

## When To Use
- You are adding or modifying a table or column.
- You need to trace how DB-backed categories, keyword tables, or budget tables are used.
- You need to edit `models.py`, `session.py`, `db_utils.py`, or route code that depends on schema shape.
- You need to preserve existing user data while evolving the schema.

## Procedure
1. Read [schema map](./references/schema-map.md) for current table ownership and dependencies.
2. Read [migration workflow](./references/migration-workflow.md) before changing schema.
3. Make schema edits in the narrowest owning files:
   - table definitions: `src/database/models.py`
   - startup creation and lightweight migrations: `src/database/session.py`
   - write/read behaviors and backfills: `src/database/db_utils.py` or backend routes/helpers
4. Prefer additive, idempotent changes over destructive rewrites.
5. Validate by checking app startup or the narrowest command that exercises the touched table or endpoint.
