---
name: "Trace Statement Processing Bug"
description: "Trace a PDF parsing, merchant cleaning, categorization, transfer detection, or statement import bug in AutomatedBudgeting."
argument-hint: "Describe the failing statement behavior, month, file, or log clue"
agent: "agent"
---
Trace this statement-processing problem in AutomatedBudgeting.

Use [statement-processing](../skills/statement-processing/SKILL.md) and [repo-architecture](../skills/repo-architecture/SKILL.md).

Requirements:
- Start from the most concrete anchor in my request: a month, statement file, log line, endpoint, or bad transaction behavior.
- Identify the owning stage in the import path: extraction, parsing, merchant cleaning, categorization, transfer detection, or DB write.
- Call out the exact files and symbols that likely control the behavior.
- If code changes are needed, make the smallest safe fix and validate it with the narrowest relevant check.
- If the issue is actually doc drift, config drift, or missing data, say so explicitly.

Return:
- Root cause
- Owning files
- Fix applied or recommended
- Validation performed
