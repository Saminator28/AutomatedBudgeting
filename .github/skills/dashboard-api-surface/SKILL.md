---
name: dashboard-api-surface
description: 'Use when working on the React dashboard, FastAPI backend routes, analytics endpoints, budget views, settings UI, statement uploads, chatbot, or frontend-to-backend API wiring in AutomatedBudgeting.'
argument-hint: 'Ask for the tab, endpoint group, or user workflow you need to trace'
user-invocable: true
---

# Dashboard API Surface

Use this skill when you need the current UI and API map for the dashboard application.

## When To Use
- You are changing a React tab or a FastAPI route.
- You need to trace a UI action to the backend endpoint and persistence layer.
- You need the analytics, budget, transfer, or chatbot route map.
- You need to understand frontend/backend drift or API contract risks.

## Procedure
1. Read [ui-and-routes](./references/ui-and-routes.md) for the current component and route map.
2. Read [analytics-and-chat](./references/analytics-and-chat.md) for the budget, forecast, insights, and chatbot stack.
3. Confirm whether the behavior is owned by a route module, shared backend helper, or frontend component before editing.
4. Watch for drift notes called out in the references, especially endpoints referenced by the frontend that are not present in the backend.
