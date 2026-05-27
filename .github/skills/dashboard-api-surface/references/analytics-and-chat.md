# Analytics And Chat

## Main Backend Surface
- Route owner: [src/ui/backend/routes/analytics.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/analytics.py)
- Supporting analysis modules:
  - [src/ai_analysis/insights_generator.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/insights_generator.py)
  - [src/ai_analysis/forecaster.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/forecaster.py)
  - [src/ai_analysis/budget_advisor.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/budget_advisor.py)
  - [src/ai_analysis/outlier_detector.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/outlier_detector.py)
  - [src/ai_analysis/chatbot_assistant.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/chatbot_assistant.py)
  - [src/ai_analysis/model_loader.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/model_loader.py)
  - [src/ai_analysis/model_loader_hf.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/model_loader_hf.py)

## Analytics Route Families
- Monthly insights: `GET /api/insights/{month}`
- Forecasting: `GET /api/forecast`
- Trend view: `GET /api/trends`
- Budget suggestions: `GET /api/budget-suggestions`
- Budget goal months: `GET /api/budget/goals/months`
- Budget goal retrieval and save: `GET /api/budget/goals`, `POST /api/budget/goals`
- Category history and committed costs: `GET /api/budget/category-history`, `GET /api/budget/committed`
- Budget save, rollover, history, month comparison, and debrief:
  - `POST /api/budget/save`
  - `GET /api/budget/rollover/{month}`
  - `GET /api/budget/history`
  - `GET /api/budget/{month}`
  - `POST /api/budget/debrief/{month}`
  - `DELETE /api/budget/goals/{month}`
- Chatbot availability and answers:
  - `GET /api/chat/available`
  - `POST /api/chat`

## Data Dependencies
- Most analytics endpoints query expenses and income through [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py), which returns DB-backed DataFrames.
- Budget endpoints depend on the expanded budget tables defined in [src/database/models.py](/home/desktop/Documents/AutomatedBudgeting/src/database/models.py): `budget_goals`, `budget_settings`, `budget_history`, and `budget_goals_monthly`.
- Category rollups and investment detection depend on `config_categories` plus the keyword tables loaded into memory by [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py).

## Chatbot Pipeline
- Chat orchestrator: [src/ai_analysis/chatbot_assistant.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/chatbot_assistant.py)
- Model config source: [config/llm_models.json](/home/desktop/Documents/AutomatedBudgeting/config/llm_models.json)
- Primary model role: deterministic intent parsing plus some merchant and categorization tasks elsewhere in the repo.
- Financial analysis model role: conversational answer generation after Python and pandas compute the actual facts.
- Debug output: [logs/llm_prompt_debug.txt](/home/desktop/Documents/AutomatedBudgeting/logs/llm_prompt_debug.txt)

## Why The Chatbot Is Structured This Way
- Intent extraction is separated from answer generation to avoid hallucinated numbers.
- Pandas computes totals and comparisons between the two model steps.
- Conversation state is retained in Python, not delegated to the model alone.
- A regex fallback exists for intent parsing if Ollama or JSON parsing fails.

## Frontend Surface For Analytics
- Main owner: [src/ui/src/InsightsPanel.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/InsightsPanel.js)
- This component handles:
  - insights loading
  - forecast and trends
  - budget suggestion fetches
  - budget goal create/update/delete flows
  - budget history and category history views
  - committed-cost and rollover panels
  - chatbot availability checks and message submission

## Where To Patch Issues
- Wrong math or aggregation: [src/ui/backend/routes/analytics.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/routes/analytics.py), [src/ui/backend/deps.py](/home/desktop/Documents/AutomatedBudgeting/src/ui/backend/deps.py)
- Bad advice or narrative framing: [src/ai_analysis/chatbot_assistant.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/chatbot_assistant.py), [src/ai_analysis/insights_generator.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/insights_generator.py), [src/ai_analysis/budget_advisor.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/budget_advisor.py)
- Model availability or Ollama transport issue: [docker-entrypoint.sh](/home/desktop/Documents/AutomatedBudgeting/docker-entrypoint.sh), [src/ai_analysis/model_loader.py](/home/desktop/Documents/AutomatedBudgeting/src/ai_analysis/model_loader.py), [config/llm_models.json](/home/desktop/Documents/AutomatedBudgeting/config/llm_models.json)
- UI rendering or fetch flow issue: [src/ui/src/InsightsPanel.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/InsightsPanel.js), [src/ui/src/App.js](/home/desktop/Documents/AutomatedBudgeting/src/ui/src/App.js)
