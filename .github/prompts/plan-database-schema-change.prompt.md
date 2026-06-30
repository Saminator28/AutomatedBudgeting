---
name: "Plan Database Schema Change"
description: "Plan or implement a migration-safe SQLite and SQLAlchemy schema change in AutomatedBudgeting."
argument-hint: "Describe the table, column, relationship, or persistence behavior you want changed"
agent: "agent"
---
Plan or implement this AutomatedBudgeting database/schema change safely.

Use [database-schema-safety](../skills/database-schema-safety/SKILL.md) and [repo-architecture](../skills/repo-architecture/SKILL.md).

Requirements:
- Identify the owning schema, startup migration, and write/read paths.
- Prefer additive and idempotent changes that preserve existing user data.
- Update all necessary files together: models, init_db migrations, DB helpers, routes, and UI contracts if applicable.
- Call out whether existing `budget.db` files need a startup migration, backfill, or a full reset.
- Validate with the narrowest executable check available.

Return:
- Proposed or applied schema change
- Files updated
- Migration or backfill strategy
- Risks to existing data
- Validation performed
