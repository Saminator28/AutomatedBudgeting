---
name: personal-finance-patterns
description: Use when reasoning about financial data correctness, transaction edge cases, amount handling, categorization failure modes, domain-specific vocabulary, or cross-platform personal-finance engineering patterns in AutomatedBudgeting.
---

This skill provides domain reference for personal-finance engineering patterns specific to AutomatedBudgeting. Load it when:
- Reasoning about whether a transaction will be handled correctly (sign, type, category, deduplication)
- Checking whether a calculation (spending total, aggregate, budget rollup) is financially sound
- Looking up what a specific field name or type value means in this codebase vs. generic finance terminology
- Reviewing code for common personal-finance data-handling pitfalls before committing a fix

## Reference Files

- `references/edge-cases.md` — transaction and data edge cases that commonly cause bugs in personal-finance systems, with detection guidance and risk descriptions
- `references/domain-vocabulary.md` — canonical field names, `tx_type` values, and key concepts as defined in this codebase specifically
