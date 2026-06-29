---
name: "Add Finance Tests"
description: "Generate pytest test stubs for personal-finance logic in AutomatedBudgeting: categorization, transfer detection, amount calculations, duplicate handling, and user-correction preservation."
applyTo: "src/**/*.py"
---

Generate pytest test stubs for the financial logic in the selected file or module.

## Test Coverage Priorities (highest to lowest)
1. **Amount correctness**: sign handling, rounding, aggregation totals match expected values
2. **Transfer detection**: both legs identified, no false positives from similar amounts, no real expenses mislabeled as transfers
3. **Categorization**: known merchants land in the correct category; `user_corrected = 1` rows are never overwritten by automation
4. **Duplicate detection**: same `tx_hash` is not inserted twice; a re-import of the same PDF is idempotent
5. **Reimbursement exclusion**: reimbursed transactions (`tx_type = "reimbursement"`) do not appear in category spending totals
6. **Edge cases**: zero-amount rows, negative income, cross-month statement overlap, missing merchant name, balance-as-amount rows

## Test Structure
- Use `pytest` with standard fixtures; do not introduce third-party test libraries unless they are already in `requirements.txt`.
- Each test function must have a docstring stating the specific financial behavior under test.
- Use an in-memory SQLite database (`:memory:`) for any DB-backed tests; never touch the user's real `budget.db`.
- Mark tests that require Ollama or any external service with `@pytest.mark.integration` so they can be excluded in CI with `-m "not integration"`.
- Place test files under `tests/` (create the directory if it does not exist); mirror the source module path (e.g., `tests/test_categorizer.py` for `src/ai_classification/categorizer.py`).

## Output Format
Return:
1. The full test file path
2. All import statements needed
3. Any fixture definitions (keep them minimal and reusable)
4. One test function per coverage item above, with clear docstrings
5. A list of any gaps where a meaningful test is not feasible without refactoring the source — describe the gap without making unsolicited changes to the source file
