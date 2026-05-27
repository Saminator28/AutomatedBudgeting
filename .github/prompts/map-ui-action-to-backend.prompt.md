---
name: "Map UI Action To Backend"
description: "Trace a dashboard action from React through FastAPI routes and into DB or AI ownership in AutomatedBudgeting."
argument-hint: "Describe the UI action, screen, tab, button, fetch call, or endpoint you want mapped"
agent: "agent"
---
Map this AutomatedBudgeting UI action to its owning backend and persistence path.

Use [dashboard-api-surface](../skills/dashboard-api-surface/SKILL.md) and [repo-architecture](../skills/repo-architecture/SKILL.md).

Requirements:
- Identify the frontend component and the exact fetch or event flow.
- Identify the FastAPI route module and endpoint(s) involved.
- Identify any shared backend helpers, DB tables, or AI modules that complete the behavior.
- Note mismatches between frontend expectations and backend reality if they exist.
- If I asked for a change, implement the smallest coherent end-to-end fix and validate it.

Return:
- Frontend owner
- Backend owner
- Persistence or AI dependencies
- Any contract mismatch or bug found
- Validation performed
