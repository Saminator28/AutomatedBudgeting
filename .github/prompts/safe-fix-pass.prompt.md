---
name: "Safe Fix Pass"
description: "Conservative bug-fix pass for AutomatedBudgeting: implement only must-fix items from a prior code review, no architecture changes, no unsolicited improvements."
---

Apply a safe, conservative fix pass to the code or findings provided.

## Rules
- Implement **must-fix items only** — data correctness, data-loss risk, security issues.
- Do **not** refactor, rename, reorganize, or make architectural changes unless explicitly instructed.
- Do **not** add new features, improve logging, or clean up style beyond what is strictly necessary to correct the bug.
- If a fix requires a schema change, **stop and flag it** — do not proceed without explicit approval from the user.
- If a fix touches stored user financial data (transactions, corrections, budget history), state the risk before making any change.

## Steps
1. List each must-fix item with its file and line reference.
2. For each item, state the proposed fix and confirm it is reversible — or explain the recovery path if it is not.
3. Apply the fix using the narrowest possible change.
4. Run validation after all changes:
   - Python: `ruff check src/ scripts/`
   - React: `cd src/ui && npm run lint`
   - Shell scripts: `bash -n <script>`
   - Backend or Docker: `make up && make logs`
5. Report:
   - What was changed (file, line, nature of fix)
   - What was intentionally not changed (should-fix and nice-to-have items deferred)
   - Any risks or follow-up items the user should be aware of
