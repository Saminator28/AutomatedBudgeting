---
name: "Code Review: Finance Logic"
description: "Review personal-finance code in AutomatedBudgeting for data correctness, transaction edge cases, cross-platform safety, backend performance, and security. Returns a prioritized finding list."
applyTo: "src/**/*.py, src/**/*.js"
---

Review the selected code or file against the following dimensions, then return a structured finding list.

## 1. Finance Data Correctness
- Check for all patterns in the Finance Engineering Patterns section of the Personal Finance Engineer agent.
- Specifically: duplicate-transaction risk (`tx_hash` collision handling), amount sign consistency, transfer-leg completeness, reimbursement exclusion at the aggregate layer, balance-row exclusion, and payment-app bypass risk.
- Verify that `user_corrected = 1` fields are never silently overwritten by any automated path.

## 2. Cross-Platform Safety
- All file paths must use `pathlib` and the `/` operator — flag any `os.path.join`, hardcoded `\\` or `/` separators, or `open()` calls with string-concatenated paths.
- Docker networking: `host.docker.internal` for Windows/macOS, `localhost` via host-mode on Linux — flag any hardcoded networking that only works on one platform.
- Shell scripts that open a browser must support all three platforms; flag single-platform `xdg-open` or `open` calls without a fallback.

## 3. Backend Performance
- Flag `async def` route handlers that contain synchronous blocking I/O (SQLAlchemy sync queries, `open()`, `requests.get()`).
- Flag `DataFrame.iterrows()` loops on transaction-sized data.
- Flag unbounded full-table queries in route handlers (`SELECT *` with no `WHERE` on the transactions table).
- Flag per-row DB writes inside a loop.

## 4. Security
- Flag any user-supplied input used in a query without parameterization (SQL injection risk).
- Flag any file path constructed from user input without sanitization (path traversal risk).
- Flag hardcoded credentials, tokens, API keys, or secrets anywhere in source files.

## 5. UX & Frontend (React files only)
- Flag any `fetch` or `axios` call with no loading state.
- Flag any API call with no error state — a failed request should never leave the user with a blank or stale view.
- Flag wide tables or card layouts with no responsive handling at narrow viewports.

## Output Format
Return findings grouped by severity:

**Must-fix** (data correctness, data-loss risk, security):
- Location: `<file>:<line>`
- Issue: one-sentence description
- Finance impact: what financial data or user trust is affected
- Recommended fix: concrete change

**Should-fix** (performance, UX, cross-platform):
- Location, issue, recommended fix (no finance impact required)

**Nice-to-have** (style, minor improvements):
- Brief list only; do not implement
