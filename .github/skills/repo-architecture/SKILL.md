---
name: repo-architecture
description: 'Use when navigating AutomatedBudgeting, locating owning files, tracing Docker/FastAPI/React/SQLite/Ollama architecture, understanding repo structure, or reconciling current code with older docs.'
argument-hint: 'Ask for the subsystem, entrypoint, or behavior you need to trace'
user-invocable: true
---

# Repo Architecture

Use this skill when you need the current architecture and file ownership map for the AutomatedBudgeting repository.

## When To Use
- You need to find where a behavior lives before editing.
- You need the current runtime topology: Docker, FastAPI, React, SQLite, Ollama.
- You need to understand which docs match the current code and which details have drifted.
- You need commands, entrypoints, or file ownership by directory.

## Procedure
1. Read [overview](./references/overview.md) for the current runtime model and subsystem map.
2. Use [file inventory](./references/file-inventory.md) to locate the exact file that owns a behavior.
3. Check [current-state notes](./references/current-state-notes.md) before relying on older docs.
4. For parser/import work, switch to the `statement-processing` skill.
5. For UI, route, analytics, or chatbot work, switch to the `dashboard-api-surface` skill.
6. For schema or persistence changes, switch to the `database-schema-safety` skill.
