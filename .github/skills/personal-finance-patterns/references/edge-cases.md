# Transaction and Data Edge Cases

These are the most common sources of bugs and data integrity issues in personal-finance systems. Before completing a fix or review, check each edge case that is relevant to the code under change.

---

## Duplicate Transactions

**Cause**: re-importing the same PDF, statement date-range overlap between months, or a failure in the import pipeline's idempotency guard.

**Detection**: `tx_hash` is a content hash of (date, merchant, amount, source_file). A hash collision should be a silent no-op — the row must not be inserted again.

**Risk**: inflated spending totals, false budget overruns, doubled transaction counts.

**Check**: does the DB write use `INSERT OR IGNORE` or `ON CONFLICT DO NOTHING` semantics? Does `tx_hash` computation use consistent inputs across all import paths?

---

## Amount Sign Convention

**Convention in this repo**: both expenses and income are stored as **positive absolute values**. The sign of a transaction is encoded in `tx_type` ("expense" vs "income"), not in the `amount` column.

**Parser risk**: bank PDFs often show credits as negative numbers or with a "CR" suffix. The parser must normalize to a positive amount before writing to the DB.

**Display risk**: if sign is flipped anywhere between the DB and the display layer, income appears as an expense or vice versa.

**Check**: is `amount` always a positive float in the `transactions` table? Does every parser path normalize sign before writing?

---

## Transfer Detection

**Transfers** are internal money movements (e.g., checking → savings, Venmo top-up to own account). They must not be counted as expenses or income.

**Both legs required**: a transfer has a debit leg and a credit leg. Both must be labeled `tx_type = "transfer"`. If only one leg is detected, the other leg is silently counted as income or expense.

**Payment-app risk**: Venmo, PayPal, and Zelle payments to other people may look like transfers but are actually expenses. Transfer detection must distinguish own-account movements from person-to-person payments.

**Ordering risk**: transfer detection must run **before** categorization. If categorization runs first, a transfer may be assigned a spending category and the transfer override is never applied.

**Check**: does `process_monthly.py` / the import pipeline apply transfer detection before the categorization step?

---

## Reimbursement Inflation

**Reimbursements** are expenses paid by the user and later refunded (employer expense reports, friend repayments, insurance claims).

**Inflation risk**: if the original expense is included in spending totals AND the reimbursement is counted as income, the user appears to have spent more than they did and received unexpected income — both figures are wrong.

**Convention**: reimbursed transactions should carry `tx_type = "reimbursement"` and be excluded from category spending totals. They may optionally be shown as a separate line item.

**Check**: does the analytics/aggregate layer filter out `tx_type = "reimbursement"` rows from spending calculations? Does the dashboard's category breakdown exclude them?

---

## Balance-as-Amount Rows

**Cause**: some bank PDF formats include a "running balance" row at the bottom of each page or at the end of each month — these are account balance snapshots, not transactions.

**Risk**: a balance row typically has no merchant name and a very large amount. If ingested, it massively inflates one category (often "Uncategorized") and skews totals.

**Check**: does the parser exclude rows where the merchant field is blank or the amount exceeds a plausible single-transaction ceiling? Is there a specific filter for known balance-row patterns?

---

## Cross-Month Statement Overlap

**Cause**: PDFs with a date range like "Dec 29 – Jan 3" span two calendar months. If both the December and January PDFs are imported, transactions from the overlap period appear twice.

**Detection**: `tx_hash` deduplication handles this correctly if hashing is consistent across both import runs.

**Risk**: if the hash function changed between the two imports (e.g., source_file is included in the hash and the filename changed), overlapping transactions insert as duplicates.

**Check**: is `tx_hash` computed with a stable set of inputs that does not include mutable fields like import timestamp or file path?

---

## Zero-Amount Rows

**Cause**: fee reversals, zero-balance adjustments, or parsing artifacts from empty lines in a PDF.

**Risk**: zero-amount rows are categorized (consuming a merchant-rule lookup and possibly an LLM call), which skews category transaction counts without affecting totals. Large numbers of them slow down the import pipeline.

**Convention**: rows with `amount = 0.00` should be filtered out or labeled `tx_type = "ignored"` before categorization runs.

---

## Negative Income

**Cause**: bank account interest reversals, returned deposits, or corrections to prior income entries.

**Risk**: a negative income row reduces net income totals. If the display layer flips the sign for income rows (to show as positive), a negative-income row shows up as a large positive expense.

**Convention**: treat negative income rows as `tx_type = "adjustment"` and exclude them from standard income totals. Show them separately if needed.

---

## User Correction Preservation

**This is the most critical data integrity invariant in the system.**

Any field on a transaction row that has `user_corrected = 1` must NEVER be overwritten by any automated process — LLM categorization, re-import, merchant rule application, or bulk recategorization.

**Check**: does every code path that writes `category`, `merchant`, or `tx_type` first check `user_corrected`? Is there a test for this?
