# Statement Processing Pipeline

## Primary Entry Paths
- CLI import: [scripts/process_monthly.py](/scripts/process_monthly.py)
- UI-triggered processing: [src/ui/backend/routes/statements.py](/src/ui/backend/routes/statements.py)
- Core parser: [src/statement_parser/parser.py](/src/statement_parser/parser.py)
- Merchant cleaning: [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py)
- Category assignment: [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py)
- DB writes: [src/database/db_utils.py](/src/database/db_utils.py)

## Ordered Flow
1. Statement files are uploaded to `src/ui/data/statements/YYYY-MM/` by [src/ui/backend/routes/statements.py](/src/ui/backend/routes/statements.py) or placed manually for CLI processing.
2. [scripts/process_monthly.py](/scripts/process_monthly.py) enumerates statement month directories, loads valid categories from DB, checks Ollama availability, and drives the import.
3. [src/statement_parser/pdf_extractor.py](/src/statement_parser/pdf_extractor.py) extracts raw text with `pdfplumber`; it falls back to OCR via `pytesseract` when extraction is empty or insufficient.
4. [src/statement_parser/parser.py](/src/statement_parser/parser.py) detects institution and account type, parses transaction rows, infers dates and amounts, strips state suffixes, splits dense all-caps merchant strings, bypasses known bank operations, and flags suspicious balance-as-amount rows.
5. [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py) optionally pulls missing models, sends merchant-cleaning prompts to Ollama, parses responses, and supports ensemble cleaning via primary plus secondary model.
6. [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py) applies income, transfer, payment-app, cache, pattern, and LLM-based category logic.
7. [scripts/process_monthly.py](/scripts/process_monthly.py) also performs cross-statement transfer detection and category validation against DB-backed categories.
8. [src/database/db_utils.py](/src/database/db_utils.py) persists transactions, merchant metadata, transfer rows, auto-delete history, and merchant rules side effects.
9. [src/ui/backend/deps.py](/src/ui/backend/deps.py) rebuilds transfers for the processed month after import.

## Parsing Heuristics That Matter
- Institution detection: parser header inspection plus institution cache support.
- Account type detection: header keywords distinguish credit-card style statements from deposit-account statements.
- Date normalization: parser handles multiple formats and repairs edge cases.
- Multi-line merchant rows: row parsing buffers continuation lines.
- Suspicious-balance routing: rows whose parsed amount matches the previous running balance are flagged for manual review.
- Bank operation bypass: known patterns such as direct or mobile deposit skip merchant-cleaning LLM calls and are assigned canonical names.
- All-caps merchant splitting: long space-free uppercase strings are split before LLM cleaning.

## Cleaning And Categorization Ownership
- Merchant text extraction or OCR issue: [src/statement_parser/pdf_extractor.py](/src/statement_parser/pdf_extractor.py)
- Bank detection, date handling, amount extraction, transfer/payment-app heuristics: [src/statement_parser/parser.py](/src/statement_parser/parser.py)
- Ollama request/response behavior, prompt parsing, ensemble selection: [src/statement_parser/llm_utils.py](/src/statement_parser/llm_utils.py)
- Category selection, income detection, transfer labeling, review routing: [src/ai_classification/categorizer.py](/src/ai_classification/categorizer.py)
- Month orchestration and cross-statement transfer pairing: [scripts/process_monthly.py](/scripts/process_monthly.py)

## Runtime Config Sources
- Model roles and names come from [config/llm_models.json](/config/llm_models.json).
- Categories, keyword lists, and hierarchy are now DB-backed through `config_categories` and keyword tables, not through checked-in JSON files.
- Current Ollama base URL is supplied through `OLLAMA_HOST`, often set or corrected by [docker-entrypoint.sh](/docker-entrypoint.sh).

## Validation Anchors
- CLI import path: run `make process MONTH=YYYY-MM`.
- Background job path: trigger statement processing through the statements API and poll `/api/jobs/{job_id}`.
- Ollama connectivity during container startup: inspect `make logs` and [docker-entrypoint.sh](/docker-entrypoint.sh).
- Prompt-level debugging for chatbot and some AI flows: [logs/llm_prompt_debug.txt](/logs/llm_prompt_debug.txt).
