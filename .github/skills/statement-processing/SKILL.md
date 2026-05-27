---
name: statement-processing
description: 'Use when working on PDF parsing, OCR fallback, merchant cleaning, categorization, transfer detection, process_monthly.py, aggregate_monthly.py, statement uploads, or DB writes from imported statements.'
argument-hint: 'Ask for the parsing stage, failure mode, or import path you want traced'
user-invocable: true
---

# Statement Processing

Use this skill when you need the end-to-end ingest path from uploaded PDF to database rows.

## When To Use
- A statement fails to parse or amounts/dates are wrong.
- Merchant cleaning, category assignment, transfer detection, or manual review behavior needs changes.
- You need to trace `process_monthly.py`, `StatementParser`, `llm_utils.py`, `categorizer.py`, or DB write logic.
- You need to understand how re-imports preserve user changes.

## Procedure
1. Read [pipeline](./references/pipeline.md) for the ordered ingest path.
2. Read [persistence-and-learning](./references/persistence-and-learning.md) for table writes, correction preservation, and merchant learning.
3. Patch the narrowest owning layer:
   - Text extraction: `pdf_extractor.py`
   - Row parsing and heuristics: `parser.py`
   - Merchant cleaning and Ollama calls: `llm_utils.py`
   - Category assignment: `categorizer.py`
   - Import orchestration: `process_monthly.py` or `statements.py`
   - DB post-processing and transfer rebuilds: `db_utils.py` or `deps.py`
