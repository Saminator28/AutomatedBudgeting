# Chatbot Two-Model Pipeline

**Source file:** `src/ai_analysis/chatbot_assistant.py`  
**Entry method:** `ChatbotAssistant.process_message()`

---

## Overview

The chatbot uses a **two-model pipeline** to answer financial questions accurately without hallucinating numbers. The models play separate, non-overlapping roles:

| Role | Model (from `config/llm_models.json`) | Purpose |
|------|---------------------------------------|---------|
| **Intent Parser** | `primary_model` (e.g. `qwen3.5:9b`) | Converts natural language → structured JSON |
| **Finance Advisor** | `financial_analysis_model` (e.g. `ALIENTELLIGENCE/financialadvisor`) | Converts verified data → conversational response |

Python + pandas sits between them and performs all actual calculations — neither model touches raw numbers directly.

---

## Pipeline Diagram

```
User message
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  ConversationState                                          │
│  Carries forward: active_period, active_category,          │
│  active_merchant, savings_goals, budget_targets            │
└──────────────────────────┬──────────────────────────────────┘
                           │ (updated each turn)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Intent Parsing                                     │
│                                                             │
│  Model: primary_model  (temp = 0.0, max 400 tokens)        │
│                                                             │
│  Input:  user message + last 4 messages + today's date     │
│  Output: JSON intent object                                 │
│                                                             │
│  {                                                          │
│    "type": "expense_query | budget_request |               │
│             savings_goal | income_query | general_advice", │
│    "period": "YYYY-MM | YYYY | null",                      │
│    "months_window": 6,                                      │
│    "category": "Dining | Groceries | ...",                  │
│    "action": "total | average | max | list | ...",         │
│    "goal_amount": 5000,                                     │
│    "goal_purpose": "car"                                    │
│  }                                                          │
│                                                             │
│  Fallback: regex parser (used if model fails or is slow)   │
└──────────────────────────┬──────────────────────────────────┘
                           │ structured intent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Context Resolution                                 │
│                                                             │
│  _apply_conversation_context()                              │
│  • Merges intent into ConversationState                     │
│  • Applies period filter to expenses + income DataFrames   │
│  • Applies category filter (expands parent → subcategories)│
│                                                             │
│  "what restaurant most?" → inherits period from prior turn │
└──────────────────────────┬──────────────────────────────────┘
                           │ filtered DataFrames
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Pandas Computation  (NO LLM involved)              │
│                                                             │
│  Dispatches to one of:                                      │
│                                                             │
│  _calculate_facts_with_pandas()  ← expense / income query  │
│    • totals, averages, top merchants, category breakdown    │
│    • full transaction list for the filtered period          │
│                                                             │
│  _calculate_budget_suggestion()  ← budget_request          │
│    • averages last 3–6 months by category                  │
│    • compares to income and 50/30/20 rule benchmarks        │
│                                                             │
│  _calculate_savings_plan()       ← savings_goal            │
│    • computes months-to-goal given avg income vs expenses   │
│    • stores / updates goals in ConversationState           │
│                                                             │
│  Output: rich plain-text data block (100% accurate figures)│
└──────────────────────────┬──────────────────────────────────┘
                           │ verified data block
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Finance Advisor Response                           │
│                                                             │
│  Model: financial_analysis_model  (temp = 0.7, max 1200 t) │
│                                                             │
│  System prompt contains:                                    │
│   • The user's question                                     │
│   • The verified pandas data block (numbers it MUST use)   │
│   • Conversation context summary                            │
│   • Style rules (direct, no filler, lead with answer)      │
│   • Role rules (never invent numbers, flag 50/30/20 gaps)  │
│                                                             │
│  Message list: system + last 8 turns + current user msg    │
│                                                             │
│  Normal response  → plain conversational text              │
│  Update request   → JSON { "action": "update_expense", … } │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Update request?       │
              │  _execute_action()     │
              │  Writes to CSV,        │
              │  returns confirmation  │
              └──────────┬─────────────┘
                         │ otherwise
                         ▼
                  Response text
                  returned to UI
```

---

## Why Two Models?

### The Hallucination Problem

If a single LLM were handed raw CSVs and asked "how much did I spend on dining in October?", it would read a subset of rows, do mental arithmetic, and often return a wrong total — especially for large datasets. The error is silent; the user has no way to know.

### The Solution: Pandas as Ground Truth

Python pandas computes all numbers. Neither model performs arithmetic. The finance model receives a pre-computed data block and is explicitly instructed:

> "Answer using ONLY the data shown above — never invent numbers. DO NOT multiply totals — they are already complete sums."

### Why Two Models Instead of One?

The intent parsing step runs at **temperature 0.0** — deterministic JSON extraction. The finance advisor runs at **temperature 0.7** — warm, conversational prose. These are opposing requirements. Using a single model would force a compromise on both. Splitting the roles also means:

- The intent model can be a smaller, faster model (lower latency)
- The finance model can be domain-tuned for financial advice
- Each can be swapped independently in `config/llm_models.json`

---

## Conversation State

`ConversationState` is a dataclass that persists across turns within a single chat session:

| Field | Set when | Used for |
|-------|----------|---------|
| `active_period` | User mentions a month/year | Follow-up questions inherit the same period |
| `active_months_window` | "last N months" | Rolling window filter |
| `active_category` | User mentions a category | Category-scoped follow-ups |
| `active_merchant` | User mentions a merchant | Merchant drill-down |
| `savings_goals` | User sets a goal | Recalculation on goal changes |
| `budget_targets` | User sets a budget per category | Budget tracking and advice |
| `monthly_savings_target` | User sets a savings target | Savings plan recalculation |

**Example:**
```
Turn 1: "how much did I spend on dining in October?"
         → active_period = "2025-10", active_category = "Dining"

Turn 2: "what restaurant was the most expensive?"
         → no period or category in message
         → state still has active_period = "2025-10", active_category = "Dining"
         → query correctly scoped to Dining in October
```

---

## Fallback Mode

If Ollama is unreachable, the primary model call fails, or the JSON response is malformed, `_regex_intent_fallback()` runs instead. It uses regular expressions to extract:
- Intent type (budget / savings / income / expense)
- Period (month name, "last month", "this year", "last N months")
- Category (synonym mapping, e.g. "restaurants" → `"Dining"`)
- Action (total / average / max / list)

The remaining steps (pandas computation and finance model) are unaffected by which intent parser ran.

---

## Configuration

Both models are set in `config/llm_models.json`:

```json
{
  "primary_model": "qwen3.5:9b",
  "secondary_model": "",
  "financial_analysis_model": "ALIENTELLIGENCE/financialadvisor"
}
```

Any Ollama model can be substituted. The container entrypoint auto-pulls any model listed here that is not yet present on the host.

---

## Debug Log

Every chatbot turn writes a debug file to `logs/llm_prompt_debug.txt` inside the container:

```
USER:        how much did i spend on dining last month?
INTENT:      { "type": "expense_query", "period": "2026-02", "category": "Dining", ... }
CONV STATE:  period=2026-02  category=Dining  merchant=None
PANDAS DATA:
  Period: 2026-02
  Transactions analyzed: 23
  ...
```

This is the fastest way to diagnose unexpected chatbot answers — it shows exactly what data the finance model received.

To read it from a running container:
```bash
docker exec automated-budgeting cat logs/llm_prompt_debug.txt
```
