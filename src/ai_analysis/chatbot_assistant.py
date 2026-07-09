"""
AI Chatbot Assistant for Financial Analysis and Expense Management

This module provides an interactive chatbot that can:
- Answer questions about expenses and spending patterns
- Suggest budgets for upcoming months based on historical spending
- Set and track savings goals (e.g. "save for a car")
- Calculate how long to reach large purchase goals
- Mark expenses as one-time purchases / add notes
- Provide personalized financial insights via a dedicated finance model

Architecture: Two-Model Pipeline
  1. Intent Model  (primary_model in llm_models.json) – parses the user's
     natural-language question into a structured JSON intent so Pandas can
     compute the exact answer (zero hallucination).
  2. Finance Advisor (financial_analysis_model in llm_models.json) – receives
     the verified pandas data and the accumulated server-side conversation
     history and produces the user-facing response.  The same model also
     self-summarises older turns when the conversation grows past
     SESSION_SUMMARY_THRESHOLD so no separate memory model is required.
  3. Memory Layer (client-side) — the ChatbotAssistant instance is kept alive
     across HTTP requests (via the session store in deps.py) so
     ConversationState and the message list persist for the lifetime of a chat
     session.  Cross-session persistence lives in the chat_sessions DB table.

Anti-loop Measures
  - think=False on every Ollama call to suppress extended reasoning blocks.
  - stop sequences prevent the model from hallucinating turn prefixes.
  - _is_looping() + _truncate_loop() post-process any responses that still
    fall into a repetition pattern on slower hardware (Ryzen 5/7).
"""

import os
import json
import logging
import re
import requests
from requests.adapters import HTTPAdapter
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')

# Shared HTTP session so the three per-message Ollama calls (intent, advisor,
# optional summarizer) reuse a single TCP connection instead of paying a fresh
# handshake each time.  Ollama is stateless server-side; "reusing the agent"
# is really connection pooling + keep_alive, not a server-held session.
_HTTP = requests.Session()
_HTTP.mount('http://',  HTTPAdapter(pool_connections=4, pool_maxsize=8))
_HTTP.mount('https://', HTTPAdapter(pool_connections=4, pool_maxsize=8))

# Keep the model resident in memory for an hour after each call so the second
# message in a conversation doesn't pay a full model-reload penalty when the
# user pauses.  Ollama's default is 5 minutes, which is too short for a
# multi-turn chatbot session using a 31B model.
_KEEP_ALIVE = '1h'

logger = logging.getLogger(__name__)

MONTH_TO_NUM = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'may': '05', 'june': '06', 'july': '07', 'august': '08',
    'september': '09', 'october': '10', 'november': '11', 'december': '12'
}

# ---------------------------------------------------------------------------
# Session cache is owned by src.ui.backend.deps._chat_sessions.
# ChatbotAssistant instances live there so a single source of truth manages
# TTL pruning and eviction across the app.
# ---------------------------------------------------------------------------

# Number of assistant turns after which the finance model is asked to
# self-summarise older turns into a compact context block that gets injected
# into subsequent system prompts.
SESSION_SUMMARY_THRESHOLD = 20

# After a summary is generated, wait at least this many additional turns
# before regenerating it — avoids one summarisation call per message.
SESSION_SUMMARY_REFRESH_INTERVAL = 10


# ---------------------------------------------------------------------------
# Conversation State
# ---------------------------------------------------------------------------

@dataclass
class ConversationState:
    """
    Carries forward context that the user establishes during a conversation.
    
    Problem it solves: if the user says "how much dining in december?" and then
    "what restaurant most?" the second message has no time context on its own.
    This class remembers 'december' so the follow-up query is answered correctly.
    """

    # Last explicitly mentioned period (e.g. "YYYY-MM", "YYYY", "last_6_months")
    active_period: Optional[str] = None
    # Number of months for rolling windows (set when user says "last 6 months")
    active_months_window: Optional[int] = None
    # Last mentioned expense category (e.g. "Dining")
    active_category: Optional[str] = None
    # Last mentioned merchant
    active_merchant: Optional[str] = None
    # Active savings goals: list of {"purpose": str, "amount": float}
    savings_goals: List[Dict] = field(default_factory=list)
    # User-set monthly budget targets per category
    budget_targets: Dict[str, float] = field(default_factory=dict)
    # User's desired monthly savings amount
    monthly_savings_target: Optional[float] = None

    def update_from_intent(self, intent: Dict) -> None:
        """Merge a newly parsed intent into the running conversation state."""
        # Update period if the new intent specifies one
        new_period = intent.get("period")
        if new_period and new_period != "null":
            self.active_period = new_period
            # Reset rolling window when an explicit period is set
            if not str(new_period).startswith("last_"):
                self.active_months_window = None

        new_window = intent.get("months_window")
        if new_window:
            self.active_months_window = int(new_window)
            self.active_period = f"last_{new_window}_months"

        # Update category  
        new_cat = intent.get("category")
        if new_cat and new_cat not in ("null", None):
            self.active_category = new_cat

        # Update merchant
        new_merchant = intent.get("merchant")
        if new_merchant and new_merchant not in ("null", None):
            self.active_merchant = new_merchant

        # Savings goal
        if intent.get("goal_amount") and intent.get("goal_purpose"):
            goal = {
                "purpose": intent["goal_purpose"],
                "amount": float(intent["goal_amount"])
            }
            # Replace existing goal for same purpose
            self.savings_goals = [
                g for g in self.savings_goals
                if g["purpose"].lower() != goal["purpose"].lower()
            ]
            self.savings_goals.append(goal)

        # Monthly savings target
        if intent.get("monthly_savings_target"):
            self.monthly_savings_target = float(intent["monthly_savings_target"])

        # Budget adjustment
        if intent.get("budget_category") and intent.get("budget_amount"):
            self.budget_targets[intent["budget_category"]] = float(intent["budget_amount"])

    def summary(self) -> str:
        """Return a human-readable summary of the current context."""
        parts = []
        if self.active_period:
            parts.append(f"Period: {self.active_period}")
        if self.active_category:
            parts.append(f"Category: {self.active_category}")
        if self.active_merchant:
            parts.append(f"Merchant: {self.active_merchant}")
        if self.savings_goals:
            goals_str = ", ".join(
                f"{g['purpose']} (${g['amount']:,.0f})" for g in self.savings_goals
            )
            parts.append(f"Goals: {goals_str}")
        if self.monthly_savings_target:
            parts.append(f"Monthly savings target: ${self.monthly_savings_target:,.0f}")
        return "; ".join(parts) if parts else "No active context"

    def to_dict(self) -> Dict:
        """Serialise state to a plain dict suitable for JSON storage."""
        return {
            "active_period":          self.active_period,
            "active_months_window":   self.active_months_window,
            "active_category":        self.active_category,
            "active_merchant":        self.active_merchant,
            "savings_goals":          self.savings_goals,
            "budget_targets":         self.budget_targets,
            "monthly_savings_target": self.monthly_savings_target,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ConversationState":
        """Reconstruct a ConversationState from a previously serialised dict."""
        state = cls()
        state.active_period          = data.get("active_period")
        state.active_months_window   = data.get("active_months_window")
        state.active_category        = data.get("active_category")
        state.active_merchant        = data.get("active_merchant")
        state.savings_goals          = data.get("savings_goals") or []
        state.budget_targets         = data.get("budget_targets") or {}
        state.monthly_savings_target = data.get("monthly_savings_target")
        return state


# ---------------------------------------------------------------------------
# Session DB helpers
# ---------------------------------------------------------------------------

def _get_db_engine():
    """Return the shared SQLAlchemy engine, or None if unavailable."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from src.database.session import get_engine
        return get_engine()
    except Exception as exc:
        logger.warning(f"Session DB unavailable: {exc}")
        return None


def load_session(session_id: str) -> Optional[Dict]:
    """
    Load a chat session row from the DB.
    Returns a dict with keys: session_id, title, created_at, updated_at,
    messages (list), conv_state (dict), summary (str|None).
    Returns None if the session does not exist.
    """
    engine = _get_db_engine()
    if engine is None:
        return None
    try:
        from sqlalchemy import text as _t
        with engine.connect() as conn:
            row = conn.execute(
                _t("SELECT session_id, title, created_at, updated_at, messages, conv_state, summary "
                   "FROM chat_sessions WHERE session_id=:sid"),
                {"sid": session_id},
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row[0],
            "title":      row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "messages":   json.loads(row[4] or "[]"),
            "conv_state": json.loads(row[5] or "{}"),
            "summary":    row[6],
        }
    except Exception as exc:
        logger.warning(f"Could not load session {session_id}: {exc}")
        return None


def save_session(
    session_id: str,
    title: str,
    messages: List[Dict],
    conv_state: Dict,
    summary: Optional[str] = None,
    created_at: Optional[str] = None,
) -> bool:
    """
    Upsert a chat session row in the DB.
    Returns True on success, False on failure.
    """
    engine = _get_db_engine()
    if engine is None:
        return False
    now = datetime.utcnow().isoformat()
    try:
        from sqlalchemy import text as _t
        with engine.connect() as conn:
            conn.execute(_t("""
                INSERT INTO chat_sessions
                    (session_id, title, created_at, updated_at, messages, conv_state, summary)
                VALUES (:sid, :title, :cat, :uat, :msgs, :cs, :sum)
                ON CONFLICT(session_id) DO UPDATE SET
                    title      = excluded.title,
                    updated_at = excluded.updated_at,
                    messages   = excluded.messages,
                    conv_state = excluded.conv_state,
                    summary    = excluded.summary
            """), {
                "sid":   session_id,
                "title": title,
                "cat":   created_at or now,
                "uat":   now,
                "msgs":  json.dumps(messages),
                "cs":    json.dumps(conv_state),
                "sum":   summary,
            })
            conn.commit()
        return True
    except Exception as exc:
        logger.warning(f"Could not save session {session_id}: {exc}")
        return False


def list_sessions() -> List[Dict]:
    """
    Return a list of all chat sessions ordered newest-first.
    Each item contains: session_id, title, created_at, updated_at, message_count.
    """
    engine = _get_db_engine()
    if engine is None:
        return []
    try:
        from sqlalchemy import text as _t
        with engine.connect() as conn:
            rows = conn.execute(_t(
                "SELECT session_id, title, created_at, updated_at, messages "
                "FROM chat_sessions ORDER BY updated_at DESC"
            )).fetchall()
        result = []
        for row in rows:
            msgs = json.loads(row[4] or "[]")
            result.append({
                "session_id":    row[0],
                "title":         row[1],
                "created_at":    row[2],
                "updated_at":    row[3],
                "message_count": len(msgs),
            })
        return result
    except Exception as exc:
        logger.warning(f"Could not list sessions: {exc}")
        return []


def delete_session(session_id: str) -> bool:
    """Delete a chat session from the DB and evict it from the in-memory cache."""
    # Evict from the live in-memory cache owned by deps.py (lazy import to
    # avoid a circular dependency at module load).
    try:
        from src.ui.backend.deps import evict_chat_session
        evict_chat_session(session_id)
    except Exception:
        pass
    engine = _get_db_engine()
    if engine is None:
        return False
    try:
        from sqlalchemy import text as _t
        with engine.connect() as conn:
            conn.execute(_t("DELETE FROM chat_sessions WHERE session_id=:sid"),
                         {"sid": session_id})
            conn.commit()
        return True
    except Exception as exc:
        logger.warning(f"Could not delete session {session_id}: {exc}")
        return False


class ChatbotAssistant:
    """AI-powered financial chatbot with expense management capabilities"""
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the chatbot assistant.

        model_name: the finance-advisor model passed in from the UI / config.
        The intent-parsing model is loaded from config/llm_models.json
        (primary_model field) so the two models can differ.

        _messages accumulates user/assistant turns across process_message() calls
        when this instance is kept alive in the session store (deps.get_or_create_chat_session).
        """
        # Finance advisor model (conversational responses + budgeting advice)
        self.model_name = model_name
        self.ai_available = bool(model_name)

        # Per-conversation state (period, category, goals …)
        self.conv_state = ConversationState()

        # Accumulated message history — grows across turns when the instance persists.
        # Each entry: {"role": "user"|"assistant", "content": str}
        self._messages: List[Dict] = []

        # Rolling summary of older turns produced by the memory model.  Refreshed
        # once the conversation grows past SESSION_SUMMARY_THRESHOLD and then
        # every SESSION_SUMMARY_REFRESH_INTERVAL turns after that.
        self._session_summary: Optional[str] = None
        self._last_summary_at_turn: int = 0

        # Load secondary model names from config
        self._load_model_config()

        if self.ai_available:
            logger.info(
                f"✨ ChatbotAssistant | intent={self.intent_model} | "
                f"advisor={self.finance_model} (also self-summarises long sessions)"
            )
        else:
            logger.info("📊 Initialized ChatbotAssistant in rule-based mode")

    def _load_model_config(self) -> None:
        """Load model names from config/llm_models.json.

        Two-model chatbot pipeline: ``primary_model`` for intent parsing and
        ``financial_analysis_model`` for answers + self-summarization.  No
        third memory model — the finance model handles both jobs.
        """
        try:
            config_path = Path("config/llm_models.json")
            if config_path.exists():
                with open(config_path) as f:
                    cfg = json.load(f)
                self.intent_model  = cfg.get("primary_model", self.model_name)
                # Finance model: prefer explicit key, fall back to what was passed in
                self.finance_model = cfg.get("financial_analysis_model") or self.model_name
            else:
                self.intent_model  = self.model_name
                self.finance_model = self.model_name
        except Exception as e:
            logger.warning(f"Could not load llm_models.json: {e}")
            self.intent_model  = self.model_name
            self.finance_model = self.model_name
    
    def process_message(
        self,
        month: Optional[str],
        message: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message and generate a response.

        When this instance is kept alive in the session store, ``_messages``
        accumulates across calls so the model sees genuine multi-turn context.

        For backward-compatibility, ``conversation_history`` is still accepted
        and used to seed ``_messages`` on the very first call to a new instance
        (e.g. when a client does not yet send a session_id but already carries
        history from a previous connection).

        Args:
            month: Optional specific month filter (YYYY-MM), if None loads all months
            message: User's message
            conversation_history: Legacy client-side history; only used to seed
                                  _messages if this instance has no history yet.

        Returns:
            Dict with response, actions_taken, updated_expenses, session_id hint, etc.
        """
        if conversation_history is None:
            conversation_history = []

        # Seed _messages from legacy client history on the very first call only.
        # Only user/assistant turns with string content are accepted so a
        # malicious client cannot inject system instructions via this seed.
        if not self._messages and conversation_history:
            self._messages = [
                {"role": m["role"], "content": m["content"]}
                for m in conversation_history
                if isinstance(m, dict)
                and m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)
            ]

        # Append current user turn to the instance message store
        self._messages.append({"role": "user", "content": message})

        # Load expense data - all months or specific month
        if month:
            expenses_df  = self._load_expenses(month)
            month_context = month
        else:
            expenses_df  = self._load_all_expenses()
            month_context = "all available months"

        if expenses_df is None or expenses_df.empty:
            error_msg = (
                "I don't have any expense data available yet. "
                "Please process monthly statements first."
            )
            self._messages.append({"role": "assistant", "content": error_msg})
            return {
                "response": error_msg,
                "actions_taken": [],
                "conversation_history": list(self._messages),
            }

        # Prepare expense summary for context
        expense_context = self._prepare_expense_context(expenses_df)
        
        # Build the legacy system-prompt messages for the fallback path
        system_prompt = self._build_system_prompt(month_context, expense_context)
        legacy_messages = [{"role": "system", "content": system_prompt}]
        for msg in self._messages[-6:]:
            legacy_messages.append(msg)
        
        # Get AI response
        if self.ai_available:
            try:
                response_data = self._generate_ai_response(message, expenses_df, month_context)
            except Exception as e:
                logger.error(f"❌ AI response generation failed: {e}")
                response_data = self._generate_fallback_response(message, expenses_df, month_context)
        else:
            response_data = self._generate_fallback_response(message, expenses_df, month_context)
        
        # Append assistant response to instance history
        self._messages.append({"role": "assistant", "content": response_data["response"]})

        # Refresh the rolling summary once the conversation grows beyond the
        # threshold, then again every SESSION_SUMMARY_REFRESH_INTERVAL turns.
        self._maybe_refresh_summary()

        return {
            **response_data,
            "conversation_history": list(self._messages),
        }

    def _maybe_refresh_summary(self) -> None:
        """Regenerate ``self._session_summary`` when the conversation is long
        enough and enough new turns have accumulated since the last refresh.

        Uses the finance model itself for the summary — no separate memory
        model is required.  No-op until the session crosses
        ``SESSION_SUMMARY_THRESHOLD`` turns; the advisor sees the last 10
        messages directly until then.
        """
        turn_count = len(self._messages)
        if turn_count < SESSION_SUMMARY_THRESHOLD:
            return
        if turn_count - self._last_summary_at_turn < SESSION_SUMMARY_REFRESH_INTERVAL:
            return
        # Summarise everything except the trailing 4 turns (2 exchanges) so the
        # advisor still sees the most recent verbatim context alongside the summary.
        older = self._messages[:-4] if turn_count > 4 else self._messages[:]
        new_summary = self._summarize_session(older, existing_summary=self._session_summary)
        if new_summary:
            self._session_summary = new_summary
            self._last_summary_at_turn = turn_count
    
    def _load_expenses(self, month: str) -> Optional[pd.DataFrame]:
        """Load expense data for a specific month from DB."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from src.database.session import get_engine
            from sqlalchemy import text as _text
            eng = get_engine()
            with eng.connect() as conn:
                rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, category "
                    "FROM transactions WHERE tx_type='expense' "
                    "AND INSTR(tx_date, '/') > 0 "
                    "AND ("
                    "SUBSTR(tx_date, LENGTH(tx_date)-3, 4) || '-' || "
                    "printf('%02d', CAST(SUBSTR(tx_date, 1, INSTR(tx_date,'/')-1) AS INTEGER))"
                    ")=:m "
                    "ORDER BY tx_date"
                ), {'m': month}).fetchall()
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=['Transaction Date', 'Place', 'Amount', 'category'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
            return df
        except Exception as e:
            logger.error(f"Error loading expenses for {month}: {e}")
            return None
    
    def _load_all_expenses(self) -> Optional[pd.DataFrame]:
        """Load expense data from all available months from DB."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from src.database.session import get_engine
            from sqlalchemy import text as _text
            eng = get_engine()
            with eng.connect() as conn:
                rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, category, report_month "
                    "FROM transactions WHERE tx_type='expense' ORDER BY report_month, tx_date"
                )).fetchall()
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=['Transaction Date', 'Place', 'Amount', 'category', 'month'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
            logger.info(f"📊 Loaded {len(df)} expenses from DB")
            return df
        except Exception as e:
            logger.error(f"Error loading all expenses: {e}")
            return None
    
    def _load_all_income(self) -> Optional[pd.DataFrame]:
        """Load income data from all available months from DB."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from src.database.session import get_engine
            from sqlalchemy import text as _text
            eng = get_engine()
            with eng.connect() as conn:
                rows = conn.execute(_text(
                    "SELECT tx_date, place, amount, category, report_month "
                    "FROM transactions WHERE tx_type='income' ORDER BY report_month, tx_date"
                )).fetchall()
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=['Transaction Date', 'Place', 'Amount', 'category', 'month'])
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
            logger.info(f"💰 Loaded {len(df)} income transactions from DB")
            return df
        except Exception as e:
            logger.error(f"Error loading all income: {e}")
            return None
    
    def _prepare_expense_context(self, df: pd.DataFrame) -> str:
        """Prepare a summary of expenses for the AI"""
        # Standardize amount column (might be 'Amount' or 'amount')
        amount_col = 'Amount' if 'Amount' in df.columns else 'amount'
        merchant_col = 'Place' if 'Place' in df.columns else 'merchant'
        date_col = 'Transaction Date' if 'Transaction Date' in df.columns else 'date'
        category_col = 'category' if 'category' in df.columns else 'Category'
        
        total_expenses = df[amount_col].sum()
        num_transactions = len(df)
        
        # Category breakdown
        if category_col in df.columns:
            category_summary = df.groupby(category_col)[amount_col].agg(['sum', 'count']).round(2)
            category_text = "\n".join([
                f"  - {cat}: ${row['sum']:.2f} ({int(row['count'])} transactions)"
                for cat, row in category_summary.iterrows()
            ])
        else:
            category_text = "  (No category information available)"
        
        # Largest expenses
        top_expenses = df.nlargest(5, amount_col)[[date_col, merchant_col, amount_col]]
        if category_col in df.columns:
            top_expenses = df.nlargest(5, amount_col)[[date_col, merchant_col, amount_col, category_col]]
        
        top_expenses_text = "\n".join([
            f"  - {row[date_col]}: {row[merchant_col]} - ${row[amount_col]:.2f}" + 
            (f" ({row[category_col]})" if category_col in row.index else "")
            for _, row in top_expenses.iterrows()
        ])
        
        return f"""
**Expense Summary:**
- Total Expenses: ${total_expenses:.2f}
- Number of Transactions: {num_transactions}

**By Category:**
{category_text}

**Top 5 Largest Expenses:**
{top_expenses_text}
"""
    
    def _build_system_prompt(self, month: str, expense_context: str) -> str:
        """Build the system prompt for the AI"""
        return f"""You are a helpful financial assistant chatbot analyzing expenses for {month}.

{expense_context}

**Your Capabilities:**
- Answer questions about expenses naturally and conversationally
- When asked about "largest" or "biggest", sort and show the top items
- When asked "where", mention the merchant/place name
- When asked about specific categories, filter and analyze that category
- When users want to mark something as one-time or add notes, acknowledge and confirm

**For normal questions, respond conversationally with details.**

**Only respond in JSON format when the user wants to UPDATE or MARK something:**

UPDATE format (when user says "mark this as one-time" or "add note"):
```json
{{
  "action": "update_expense",
  "expense_index": <row_number>,
  "updates": {{
    "one_time_purchase": true/false,
    "user_notes": "note text"
  }},
  "message": "Marked [merchant] expense as a one-time purchase."
}}
```

For everything else, answer naturally with specific details from the data."""
    
    # ── Anti-loop utilities ───────────────────────────────────────────────────

    @staticmethod
    def _is_looping(text: str) -> bool:
        """Return True if *text* shows a repetition loop.

        A loop is defined as any sentence (> 20 chars) appearing 3 or more times.
        This catches the common failure mode on mid-range hardware where the model
        gets stuck repeating the same phrase endlessly.
        """
        if len(text) < 200:
            return False
        sentences = re.split(r'[.!?\n]', text)
        seen: Dict[str, int] = {}
        for s in sentences:
            key = s.strip()[:60].lower()
            if len(key) < 20:
                continue
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= 3:
                return True
        return False

    @staticmethod
    def _truncate_loop(text: str) -> str:
        """Truncate *text* at the point where repetition first starts."""
        parts = re.split(r'([.!?\n])', text)
        seen: Dict[str, int] = {}
        result: list = []
        i = 0
        while i < len(parts):
            chunk = parts[i] + (parts[i + 1] if i + 1 < len(parts) else '')
            key   = chunk.strip()[:60].lower()
            if len(key) >= 20:
                seen[key] = seen.get(key, 0) + 1
                if seen[key] >= 2:
                    break
            result.append(chunk)
            i += 2
        return ''.join(result).rstrip() or text[:500]

    def _generate_ai_response(
        self,
        user_message: str,
        expenses_df: pd.DataFrame,
        month: str,
    ) -> Dict[str, Any]:
        """
        Three-model pipeline:
          1. Intent Model  → parse user message + accumulated conv_state → JSON intent
          2. Pandas        → execute intent against real data (zero hallucination)
          3. Memory/Finance Model → compose conversational answer using self._messages

        conv_state is maintained across calls by the persistent instance; no need
        to rebuild it from history on each request.
        """
        try:
            # Prior turns (everything before the current user message)
            prior_history = self._messages[:-1]

            # ── 1. Parse intent with the reasoning model ────────────────────
            intent = self._parse_intent(user_message, prior_history)
            logger.info(f"🧠 Parsed intent: {intent}")

            # ── 2. Update running conversation state ────────────────────────
            self.conv_state.update_from_intent(intent)

            # ── 3. Load & filter data using resolved context ─────────────────
            all_expenses = expenses_df  # already loaded by caller
            all_income   = self._load_all_income()

            filtered_expenses, filtered_income = self._apply_conversation_context(
                all_expenses, all_income, intent_type=intent.get("type", "expense_query")
            )

            # ── 4. Build pandas data block based on intent type ──────────────
            intent_type = intent.get("type", "expense_query")

            if intent_type == "budget_request":
                pandas_data = self._calculate_budget_suggestion(all_expenses, all_income)
            elif intent_type == "savings_goal":
                pandas_data = self._calculate_savings_plan(
                    all_expenses, all_income,
                    goal_amount=intent.get("goal_amount"),
                    goal_purpose=intent.get("goal_purpose")
                )
            elif intent_type == "goal_adjustment":
                pandas_data = self._calculate_savings_plan(
                    all_expenses, all_income,
                    goal_amount=None,
                    goal_purpose=None
                )
            else:
                pandas_data = self._calculate_facts_with_pandas(
                    filtered_expenses, user_message, filtered_income
                )

            # ── 5. DEBUG log ─────────────────────────────────────────────────
            debug_file = Path("logs/llm_prompt_debug.txt")
            debug_file.parent.mkdir(exist_ok=True)
            with open(debug_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write("LLM PROMPT DEBUG\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"USER: {user_message}\n")
                f.write(f"INTENT: {json.dumps(intent, indent=2)}\n")
                f.write(f"CONV STATE: {self.conv_state.summary()}\n\n")
                f.write(f"SESSION TURNS: {len(self._messages)}\n")
                f.write("PANDAS DATA:\n")
                f.write(pandas_data)
                f.write(f"\n\nTransactions analyzed: {len(filtered_expenses)}\n")

            # ── 6. Call memory/finance advisor model ─────────────────────────
            response_text = self._call_finance_advisor(
                user_message, pandas_data, intent, month
            )

            # Handle update requests (mark expense / add note)
            if '"action"' in response_text and '"update_expense"' in response_text:
                try:
                    js = response_text[response_text.find('{'):response_text.rfind('}')+1]
                    action_data = json.loads(js)
                    return self._execute_action(action_data, filtered_expenses, month)
                except json.JSONDecodeError:
                    pass

            return {
                "response":      response_text.strip(),
                "expenses":      [],
                "actions_taken": [],
                "ai_generated":  True,
                "model_name":    self.finance_model,
            }

        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise

    # ── Intent Parsing ────────────────────────────────────────────────────────

    def _parse_intent(self, user_message: str, conversation_history: List[Dict]) -> Dict:
        """
        Use the intent model (primary_model from config/llm_models.json) to parse
        the user's message into a structured JSON intent.  Falls back to a regex-based
        parser if the model is unavailable or the JSON is malformed.
        """
        if not self.intent_model:
            return self._regex_intent_fallback(user_message)

        # Build a concise conversation snippet so the model understands context
        history_snippet = ""
        for msg in conversation_history[-4:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_snippet += f"{role}: {msg['content'][:200]}\n"

        # Resolve temporal references deterministically so the model doesn't have to guess
        _now = datetime.now()
        _last_month_dt = (_now.replace(day=1) - timedelta(days=1))
        _today_str      = _now.strftime('%B %d, %Y')
        _this_month_str = _now.strftime('%Y-%m')
        _last_month_str = _last_month_dt.strftime('%Y-%m')
        _this_year      = _now.year
        _last_year      = _now.year - 1

        # Determine the latest month that actually has data so "last month" resolves correctly
        _latest_data_month = _last_month_str
        _available_months_str = ""
        try:
            from src.database.session import get_engine as _get_eng
            from sqlalchemy import text as _sqlt
            with _get_eng().connect() as _c:
                _rows = _c.execute(_sqlt(
                    "SELECT DISTINCT report_month FROM transactions ORDER BY report_month"
                )).fetchall()
            _available = [r[0] for r in _rows if r[0]]
            if _available:
                _latest_data_month = _available[-1]
                _available_months_str = ", ".join(_available)
        except Exception:
            pass

        # Load actual category list from DB so the prompt stays in sync with user customizations
        _cat_list: list = []
        try:
            from src.database.session import get_engine as _get_cat_engine
            from sqlalchemy import text as _cat_text
            with _get_cat_engine().connect() as _cc:
                _cat_list = [r[0] for r in _cc.execute(_cat_text(
                    'SELECT name FROM config_categories ORDER BY sort_order, name'
                )).fetchall()]
        except Exception:
            pass
        _cat_enum = ' | '.join(_cat_list) if _cat_list else (
            'Dining | Shopping | Groceries | Entertainment | Alcohol/Bar | Utilities | '
            'Transportation | Subscriptions | Gifts & Donations | Other'
        )

        prompt = f"""You are an intent parser for a personal finance chatbot.
Extract the user's intent from the message below and output ONLY valid JSON.

Today's date: {_today_str}
Months with data: {_available_months_str or 'unknown'}
Latest month with data: {_latest_data_month}
Temporal reference guide:
  "last month" or "previous month" = {_latest_data_month}  (use the latest month with data, not calendar last month)
  "this month" or "current month"  = {_this_month_str}
  "this year"                      = {_this_year}
  "last year"                      = {_last_year}

Conversation so far:
{history_snippet}
Current message: {user_message}

Output a single JSON object with these fields (use null for unknown):
{{
  "type": "expense_query | income_query | budget_request | savings_goal | goal_adjustment | general_advice",
  "period": "<YYYY-MM for a specific month | YYYY for a full year | null>",
  "months_window": <integer if user says 'last N months', else null>,
  "category": "<{_cat_enum} | null>",
  "merchant": "<specific merchant name or null>",
  "action": "<total | average | max | min | list | count | null>",
  "goal_amount": <number or null>,
  "goal_purpose": "<car | house | vacation | custom description or null>",
  "monthly_savings_target": <number or null>,
  "budget_category": "<category name or null>",
  "budget_amount": <number or null>
}}

Rules:
- "budget_request" = user wants a suggested budget for next month
- "savings_goal"   = user wants to know how to save for something big
- "goal_adjustment"= user is changing an existing goal or savings target
- "general_advice" = open-ended financial advice question
- Always resolve relative time words ("last month", "this month", etc.) using the
  temporal reference guide above — never leave period as null for those phrases.
- If the question is a follow-up with no explicit period (e.g. "what restaurant most?"),
  set period to null so the caller uses the conversation state.
- Output ONLY the JSON — no explanation, no markdown, no thinking tags."""

        try:
            _resp = _HTTP.post(
                f'{_OLLAMA_HOST}/api/chat',
                json={
                    'model': self.intent_model,
                    'messages': [{"role": "user", "content": prompt}],
                    'stream': False,
                    'think': False,
                    'keep_alive': _KEEP_ALIVE,
                    'options': {
                        "temperature": 0.0,
                        "num_predict": 400,
                        "stop": ["\n\n", "```", "<|end|>", "<|im_end|>"],
                    },
                },
                timeout=60,
            )
            _resp.raise_for_status()
            raw = (_resp.json().get('message', {}).get('content') or '').strip()
            # Strip any residual thinking tags
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
            # Extract the JSON object
            js_start = raw.find('{')
            js_end   = raw.rfind('}') + 1
            if js_start >= 0 and js_end > js_start:
                intent = json.loads(raw[js_start:js_end])
                return intent
        except Exception as e:
            logger.warning(f"Intent model failed: {e}")

        return self._regex_intent_fallback(user_message)

    def _regex_intent_fallback(self, user_message: str) -> Dict:
        """Cheap regex-based intent extraction used when the model is unavailable."""
        msg = user_message.lower()
        intent: Dict[str, Any] = {
            "type": "expense_query",
            "period": None,
            "months_window": None,
            "category": None,
            "merchant": None,
            "action": "total",
            "goal_amount": None,
            "goal_purpose": None,
            "monthly_savings_target": None,
            "budget_category": None,
            "budget_amount": None,
        }

        # Intent type
        if any(w in msg for w in ["budget", "next month", "plan", "allocate"]):
            intent["type"] = "budget_request"
        elif any(w in msg for w in ["save for", "saving for", "how long", "afford"]):
            intent["type"] = "savings_goal"
        elif any(w in msg for w in ["how much should i save", "monthly savings"]):
            intent["type"] = "goal_adjustment"
        elif any(w in msg for w in ["income", "made", "earned", "salary", "paycheck"]):
            intent["type"] = "income_query"
        elif any(w in msg for w in ["advice", "financial health", "doing well", "am i on track"]):
            intent["type"] = "general_advice"

        # Period
        _now_fb = datetime.now()
        _last_month_fb = (_now_fb.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        _this_month_fb = _now_fb.strftime('%Y-%m')

        if any(p in msg for p in ['last month', 'previous month']):
            intent["period"] = _last_month_fb
        elif any(p in msg for p in ['this month', 'current month']):
            intent["period"] = _this_month_fb
        else:
            m = re.search(
                r'(january|february|march|april|may|june|july|august|september|october|november|december)'
                r'(?:\s+(\d{4}))?', msg
            )
            if m:
                yr = m.group(2) or str(_now_fb.year)
                intent["period"] = f"{yr}-{MONTH_TO_NUM[m.group(1)]}"
            elif "last year" in msg or "previous year" in msg:
                intent["period"] = str(_now_fb.year - 1)
            elif "this year" in msg:
                intent["period"] = str(_now_fb.year)

        win = re.search(r'(?:last|past|previous)\s+(\d+)\s+months?', msg)
        if win:
            intent["months_window"] = int(win.group(1))

        # Category synonyms — map to the actual category/subcategory names used in the data
        synonyms = {
            "dining": "Dining", "restaurant": "Dining", "eating out": "Dining",
            "food": "Dining", "fast food": "Dining",
            "shopping": "Shopping", "amazon": "Shopping",
            "groceries": "Groceries", "grocery": "Groceries",
            "entertainment": "Entertainment",
            "alcohol": "Alcohol/Bar", "bar": "Alcohol/Bar", "liquor": "Alcohol/Bar",
            "beer": "Alcohol/Bar", "wine": "Alcohol/Bar", "drinking": "Alcohol/Bar",
            "electricity": "Electric", "electric bill": "Electric", "electric": "Electric",
            "internet": "Internet/Cable", "cable": "Internet/Cable", "wifi": "Internet/Cable",
            "natural gas": "Natural Gas", "heating": "Natural Gas",
            "water": "Water/Sewer", "sewer": "Water/Sewer",
            "utilities": "Utilities",
            "health": "Health", "medical": "Health", "doctor": "Health",
            "gas station": "Gas/Fuel", "fuel": "Gas/Fuel", "gasoline": "Gas/Fuel",
            "auto maintenance": "Auto Maintenance", "car repair": "Auto Maintenance",
            "transport": "Transportation", "uber": "Transportation", "parking": "Transportation",
            "subscriptions": "Subscriptions", "netflix": "Subscriptions", "spotify": "Subscriptions",
            "donation": "Gifts & Charity", "charity": "Gifts & Charity",
            "investment": "Investment",
        }
        for kw, cat in synonyms.items():
            if kw in msg:
                intent["category"] = cat
                break

        # Action
        if any(w in msg for w in ["most", "highest", "largest", "biggest", "top"]):
            intent["action"] = "max"
        elif any(w in msg for w in ["average", "avg", "mean"]):
            intent["action"] = "average"
        elif any(w in msg for w in ["list", "show", "what"]):
            intent["action"] = "list"
        elif any(w in msg for w in ["how many", "count", "times"]):
            intent["action"] = "count"

        # Goal amount
        amt_m = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(?:thousand|k)?', msg)
        if amt_m and intent["type"] in ("savings_goal", "goal_adjustment"):
            raw_amt = amt_m.group(1).replace(',', '')
            multiplier = 1000 if 'thousand' in msg or 'k' in msg else 1
            intent["goal_amount"] = float(raw_amt) * multiplier

        for purpose in ["car", "house", "home", "vacation", "trip", "emergency fund", "college"]:
            if purpose in msg:
                intent["goal_purpose"] = purpose
                break

        return intent

    # ── Conversation Context Application ─────────────────────────────────────

    def _apply_conversation_context(
        self,
        expenses_df: Optional[pd.DataFrame],
        income_df: Optional[pd.DataFrame],
        intent_type: str = "expense_query"
    ) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
        """
        Filter dataframes using the current conversation state (period, category, etc.)
        so follow-up questions automatically use the same scope as the previous message.
        """
        if expenses_df is None or expenses_df.empty:
            return pd.DataFrame(), None

        state = self.conv_state

        # --- Period filter ---
        filtered_exp = expenses_df.copy()
        filtered_inc = income_df.copy() if income_df is not None and not income_df.empty else None

        if state.active_period:
            period = state.active_period
            if 'month' in filtered_exp.columns:
                if re.match(r'\d{4}-\d{2}$', period):
                    # Exact month: YYYY-MM
                    candidate = filtered_exp[filtered_exp['month'] == period]
                    if candidate.empty and not filtered_exp.empty:
                        # Requested month has no data — fall back to latest available month
                        latest = sorted(filtered_exp['month'].unique())[-1]
                        logger.warning(
                            f"No data for requested period {period}, falling back to latest: {latest}"
                        )
                        self.conv_state.active_period = latest
                        period = latest
                        candidate = filtered_exp[filtered_exp['month'] == period]
                    filtered_exp = candidate
                    if filtered_inc is not None and 'month' in filtered_inc.columns:
                        filtered_inc = filtered_inc[filtered_inc['month'] == period]
                elif re.match(r'\d{4}$', period):
                    # Full year: YYYY
                    filtered_exp = filtered_exp[filtered_exp['month'].str.startswith(period)]
                    if filtered_inc is not None and 'month' in filtered_inc.columns:
                        filtered_inc = filtered_inc[filtered_inc['month'].str.startswith(period)]
                elif period.startswith("last_") and period.endswith("_months"):
                    window = int(period.split('_')[1])
                    now = datetime.now()
                    total = now.year * 12 + now.month - window
                    sy, sm = total // 12, total % 12
                    if sm == 0:
                        sm = 12; sy -= 1
                    start = f"{sy}-{sm:02d}"
                    filtered_exp = filtered_exp[filtered_exp['month'] >= start]
                    if filtered_inc is not None and 'month' in filtered_inc.columns:
                        filtered_inc = filtered_inc[filtered_inc['month'] >= start]

        # --- Category filter ---
        # Only apply for targeted expense/income queries, not budget or general advice
        # which need the full dataset across all categories.
        _targeted = intent_type in ("expense_query", "income_query")
        if _targeted and state.active_category and 'category' in filtered_exp.columns:
            cat_lower = state.active_category.lower()

            # Expand parent categories to include subcategories from DB
            # (e.g. "Utilities" → ["Electric", "Natural Gas", "Water/Sewer", "Internet/Cable"])
            try:
                from src.database.session import get_engine as _get_sub_engine
                from sqlalchemy import text as _sub_text
                with _get_sub_engine().connect() as _sc:
                    _sub_rows = _sc.execute(_sub_text(
                        'SELECT name, parent FROM config_categories WHERE parent IS NOT NULL'
                    )).fetchall()
                _subcategories = {}
                for _sname, _sparent in _sub_rows:
                    _subcategories.setdefault(_sparent, []).append(_sname)
            except Exception:
                _subcategories = {}

            candidate_cats: set = {cat_lower}
            for parent, subs in _subcategories.items():
                if parent.lower() == cat_lower:
                    candidate_cats.update(s.lower() for s in subs)

            def _cat_matches(c: str) -> bool:
                cl = c.lower()
                return any(cand in cl or cl in cand for cand in candidate_cats)

            cat_mask = filtered_exp['category'].astype(str).apply(_cat_matches)
            if cat_mask.any():
                filtered_exp = filtered_exp[cat_mask]

        return filtered_exp, filtered_inc

    # ── Budget Suggestion ─────────────────────────────────────────────────────

    def _calculate_budget_suggestion(
        self,
        expenses_df: pd.DataFrame,
        income_df: Optional[pd.DataFrame]
    ) -> str:
        """
        Calculate a suggested budget for next month based on the last 3–6 months
        of actual spending.  Returns a rich text block for the finance model.
        """
        if expenses_df is None or expenses_df.empty:
            return "No expense history available to generate a budget suggestion."

        amount_col   = 'Amount'   if 'Amount'   in expenses_df.columns else 'amount'
        category_col = 'category' if 'category' in expenses_df.columns else 'Category'

        lines = []

        # Use up to 6 most-recent months
        if 'month' in expenses_df.columns:
            recent_months = sorted(expenses_df['month'].unique())[-6:]
            df = expenses_df[expenses_df['month'].isin(recent_months)]
            n_months = len(recent_months)
            lines.append(f"**Budget Analysis — Based on last {n_months} months "
                         f"({recent_months[0]} → {recent_months[-1]})**\n")
        else:
            df = expenses_df
            n_months = 1

        # Compute average income
        avg_income = None
        if income_df is not None and not income_df.empty:
            income_amount_col = 'Amount' if 'Amount' in income_df.columns else 'amount'
            if 'month' in income_df.columns:
                recent_income = income_df[income_df['month'].isin(
                    sorted(income_df['month'].unique())[-6:]
                )]
                avg_income = recent_income[income_amount_col].sum() / max(
                    len(recent_income['month'].unique()), 1
                )
            else:
                avg_income = income_df[income_amount_col].sum()

        if category_col in df.columns:
            cat_avg = (
                df.groupby(category_col)[amount_col]
                .sum()
                .div(n_months)
                .sort_values(ascending=False)
                .round(2)
            )
            total_avg = cat_avg.sum()
            lines.append("**Average Monthly Spending by Category:**")
            lines.append(f"(% of spend = share of total expenses; % of income = share of avg monthly income ${avg_income:,.2f})" if avg_income else "(% of spend = share of total expenses)")
            lines.append("")
            for cat, avg in cat_avg.items():
                pct_of_spend = (avg / total_avg * 100) if total_avg > 0 else 0
                if avg_income and avg_income > 0:
                    pct_of_income = avg / avg_income * 100
                    lines.append(f"  {cat}: ${avg:,.2f}/mo  ({pct_of_spend:.1f}% of spend | {pct_of_income:.1f}% of income)")
                else:
                    lines.append(f"  {cat}: ${avg:,.2f}/mo  ({pct_of_spend:.1f}% of spend)")

            lines.append(f"\n**Total Avg Monthly Expenses: ${total_avg:,.2f}**")
            if avg_income:
                lines.append(f"**Avg Monthly Income: ${avg_income:,.2f}**")
                lines.append(f"**Avg Monthly Surplus/Deficit: ${avg_income - total_avg:,.2f}**")
                lines.append(f"**Expense-to-Income Ratio: {total_avg / avg_income * 100:.1f}%**")

        # User-set targets (from conversation state)
        if self.conv_state.budget_targets:
            lines.append("\n**Your Custom Budget Targets:**")
            for cat, amt in self.conv_state.budget_targets.items():
                lines.append(f"  {cat}: ${amt:,.2f}/mo")

        return "\n".join(lines)

    # ── Savings Goal Calculator ───────────────────────────────────────────────

    def _calculate_savings_plan(
        self,
        expenses_df: pd.DataFrame,
        income_df: Optional[pd.DataFrame],
        goal_amount: Optional[float] = None,
        goal_purpose: Optional[str] = None,
    ) -> str:
        """
        Calculate how long it will take to reach a savings goal based on the
        user's actual income vs. spending pattern.
        """
        lines = []

        # Determine average monthly income
        avg_income = 0.0
        if income_df is not None and not income_df.empty:
            inc_col = 'Amount' if 'Amount' in income_df.columns else 'amount'
            if 'month' in income_df.columns:
                months_with_income = income_df['month'].nunique()
                avg_income = income_df[inc_col].sum() / max(months_with_income, 1)
            else:
                avg_income = income_df[inc_col].sum()

        # Determine average monthly expenses
        avg_expenses = 0.0
        if expenses_df is not None and not expenses_df.empty:
            exp_col = 'Amount' if 'Amount' in expenses_df.columns else 'amount'
            if 'month' in expenses_df.columns:
                recent = sorted(expenses_df['month'].unique())[-6:]
                df_recent = expenses_df[expenses_df['month'].isin(recent)]
                avg_expenses = df_recent[exp_col].sum() / max(len(recent), 1)
            else:
                avg_expenses = expenses_df[exp_col].sum()

        monthly_surplus = max(avg_income - avg_expenses, 0)

        lines.append(f"**Your Financial Snapshot (6-month average):**")
        lines.append(f"  Average monthly income:   ${avg_income:,.2f}")
        lines.append(f"  Average monthly expenses: ${avg_expenses:,.2f}")
        lines.append(f"  Average monthly surplus:  ${monthly_surplus:,.2f}")

        # User's desired monthly savings target (from conversation)
        target_savings = self.conv_state.monthly_savings_target or monthly_surplus

        # Goals to calculate for
        goals = []
        if goal_amount and goal_purpose:
            goals.append({"purpose": goal_purpose, "amount": goal_amount})
        goals.extend(self.conv_state.savings_goals)

        if goals:
            lines.append(f"\n**Savings Goal Projections (saving ${target_savings:,.2f}/month):**")
            for g in goals:
                purpose = g["purpose"]
                amount  = g["amount"]
                if target_savings > 0:
                    months_needed = amount / target_savings
                    years  = int(months_needed // 12)
                    months = int(months_needed % 12)
                    time_str  = ""
                    if years:
                        time_str += f"{years} year{'s' if years != 1 else ''}"
                    if months:
                        time_str += (" and " if time_str else "") + f"{months} month{'s' if months != 1 else ''}"
                    lines.append(
                        f"  🎯 {purpose.title()} (${amount:,.0f}): "
                        f"~{time_str} at your current surplus rate"
                    )
                    # What if they saved more?
                    for extra in [100, 200, 500]:
                        boosted_months = amount / (target_savings + extra)
                        by, bm = int(boosted_months // 12), int(boosted_months % 12)
                        bt = ""
                        if by: bt += f"{by}y"
                        if bm: bt += f" {bm}m"
                        lines.append(
                            f"     → Save ${target_savings+extra:,.0f}/mo: ~{bt.strip()}"
                        )
                else:
                    lines.append(
                        f"  ⚠️ {purpose.title()}: No surplus to save — expenses exceed income."
                    )
        else:
            lines.append(
                "\n**No specific goal set yet.** Tell me what you're saving for "
                "(e.g. 'I want to save for a car worth $25,000') and I'll calculate a plan."
            )

        # Expense categories most reducible
        if expenses_df is not None and not expenses_df.empty:
            exp_col = 'Amount' if 'Amount' in expenses_df.columns else 'amount'
            cat_col = 'category' if 'category' in expenses_df.columns else 'Category'
            if cat_col in expenses_df.columns and 'month' in expenses_df.columns:
                recent = sorted(expenses_df['month'].unique())[-3:]
                df_rec = expenses_df[expenses_df['month'].isin(recent)]
                cat_avg = (
                    df_rec.groupby(cat_col)[exp_col].sum()
                    .div(len(recent))
                    .sort_values(ascending=False)
                )
                discretionary = {
                    c: amt for c, amt in cat_avg.items()
                    if c in ["Dining", "Entertainment", "Shopping", "Subscriptions"]
                }
                if discretionary:
                    lines.append("\n**Top Discretionary Spending (potential savings):**")
                    for cat, amt in list(discretionary.items())[:4]:
                        lines.append(f"  {cat}: ${amt:.2f}/mo average")

        return "\n".join(lines)

    # ── Finance Advisor Call ──────────────────────────────────────────────────

    def _summarize_session(
        self,
        conversation_history: List[Dict],
        existing_summary: Optional[str] = None,
    ) -> Optional[str]:
        """
        Ask the finance model to condense older turns into a compact summary
        paragraph.  Returns the summary string, or None on failure.

        Uses the same ``financial_analysis_model`` that produces user-facing
        answers — running summarisation on the same model avoids requiring a
        second model install and keeps the summary in the advisor's own voice.

        The summary is stored in the chat_sessions.summary column so the
        finance advisor can receive it as a context block instead of the
        full message log when the session is very long.
        """
        if not self.finance_model:
            return None

        # Build the conversation text to summarise
        lines = []
        if existing_summary:
            lines.append(f"[Previous summary]: {existing_summary}\n")
        for msg in conversation_history:
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue
            prefix = "User" if role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg['content'][:400]}")

        conv_text = "\n".join(lines)
        if not conv_text.strip():
            return None

        prompt = (
            "You are a memory manager for a personal-finance chatbot.  "
            "Summarise the following conversation into a single compact paragraph "
            "that captures: the financial questions asked, the key data points "
            "discussed, any goals or budgets mentioned, and the time periods "
            "referenced.  The summary will be injected into future prompts so the "
            "assistant does not lose context.  Be concise — 3–5 sentences maximum.\n\n"
            f"Conversation:\n{conv_text}\n\nSummary:"
        )
        try:
            resp = _HTTP.post(
                f'{_OLLAMA_HOST}/api/chat',
                json={
                    "model":   self.finance_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":  False,
                    "think":   False,
                    "keep_alive": _KEEP_ALIVE,
                    "options": {"temperature": 0.3, "num_predict": 300},
                },
                timeout=60,
            )
            resp.raise_for_status()
            summary = (resp.json().get("message", {}).get("content") or "").strip()
            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
            if summary:
                logger.info(f"🧠 Finance model self-summarised session ({len(summary)} chars)")
            return summary or None
        except Exception as exc:
            logger.warning(f"Session summarisation failed: {exc}")
            return None

    def _call_finance_advisor(
        self,
        user_message: str,
        pandas_data: str,
        intent: Dict,
        month: str,
    ) -> str:
        """
        Call the finance advisor model with verified pandas data and the
        accumulated server-side conversation history (self._messages).

        The finance-tuned model (``financial_analysis_model``) writes every
        user-facing answer.  Long conversations are compressed by the same
        model via ``_summarize_session`` — no separate memory model.

        Anti-loop measures:
          - think=False suppresses extended reasoning blocks
          - stop sequences prevent turn-prefix hallucination
          - num_predict capped at 800 (suitable for Ryzen 5/7)
          - _is_looping / _truncate_loop post-process any repeated output
        """
        active_model = self.finance_model

        # Build session summary section if the rolling memory summary is populated.
        summary_section = ""
        if self._session_summary:
            summary_section = f"\n**Session Summary:**\n{self._session_summary}\n"

        system_prompt = f"""You are a concise, professional personal finance advisor.

The user has asked: {user_message}

Here is the VERIFIED financial data (calculated by Python pandas — 100% accurate):

{pandas_data}

**Conversation Context:**
{self.conv_state.summary()}
{summary_section}
**Communication Style:**
- Be direct and professional — lead with the answer, not the explanation
- Keep responses SHORT (2–4 sentences for simple questions)
- Do NOT narrate calculations step by step
- Do NOT restate the question or use filler phrases like "Great question!"
- Stop after giving the answer — do not loop or repeat

**Your Role:**
- Answer using ONLY the data shown above — never invent numbers
- DO NOT multiply totals — they are already complete sums for the stated period
- For budget suggestions: compare against 50/30/20 rule, flag what's off, give a target
- For discretionary spending: be direct if over benchmark — state the number and a target
- For savings/investment: flag clearly if under 20% of income
- For savings goals: give a clear timeline and one concrete suggestion
- If the user sets a goal or adjusts a budget, confirm and recalculate concisely

**For UPDATE requests only**, respond in JSON:
```json
{{
  "action": "update_expense",
  "expense_index": <row_number>,
  "updates": {{"one_time_purchase": true/false, "user_notes": "text"}},
  "message": "Confirmation message"
}}
```
For all other requests, answer in plain conversational text. Stop once the answer is complete."""

        # Build message list from instance history (includes current user message at end)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in self._messages[-10:]:    # cap at 10 messages = 5 turns of context
            messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            _resp = _HTTP.post(
                f'{_OLLAMA_HOST}/api/chat',
                json={
                    'model':    active_model,
                    'messages': messages,
                    'stream':   False,
                    'think':    False,
                    'keep_alive': _KEEP_ALIVE,
                    'options':  {
                        "temperature": 0.7,
                        "num_predict": 800,     # conservative for Ryzen 5/7
                        "stop": [               # prevent turn-prefix hallucination
                            "\nUser:", "\nHuman:", "User:", "Human:",
                            "<|end|>", "<|im_end|>",
                        ],
                    },
                },
                timeout=120,
            )
            _resp.raise_for_status()
            raw = (_resp.json().get('message', {}).get('content') or '').strip()
            # Strip residual thinking tags (some models emit them despite think=False)
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            # Anti-loop: truncate if the model is repeating itself
            if self._is_looping(raw):
                logger.warning("⚠️ Finance advisor response loop detected — truncating")
                raw = self._truncate_loop(raw)

            logger.info(f"💬 Finance Advisor [{active_model}]: {raw[:200]}…")
            return raw
        except Exception as e:
            logger.error(f"Finance advisor model failed: {e}")
            raise

    def _calculate_facts_with_pandas(self, expenses_df: pd.DataFrame, user_message: str, income_df: Optional[pd.DataFrame] = None) -> str:
        """Provide simple summary stats and ALL transaction details - let LLM do the analysis"""
        if expenses_df.empty:
            # Build a helpful message listing what months are available
            try:
                from src.database.session import get_engine as _get_eng2
                from sqlalchemy import text as _sqlt2
                with _get_eng2().connect() as _c2:
                    _avail = [r[0] for r in _c2.execute(_sqlt2(
                        "SELECT DISTINCT report_month FROM transactions "
                        "WHERE tx_type='expense' ORDER BY report_month"
                    )).fetchall() if r[0]]
                if _avail:
                    return (f"No expense data for the requested period. "
                            f"Available months: {', '.join(_avail)}. "
                            f"Try asking about {_avail[-1]} instead.")
            except Exception:
                pass
            return "No expense data available for the requested period. Please process statements first."
        
        # Determine column names
        amount_col = 'Amount' if 'Amount' in expenses_df.columns else 'amount'
        merchant_col = 'Place' if 'Place' in expenses_df.columns else 'merchant'
        date_col = 'Transaction Date' if 'Transaction Date' in expenses_df.columns else 'date'
        category_col = 'category' if 'category' in expenses_df.columns else 'Category'
        
        facts = []

        
        # Period information
        if 'month' in expenses_df.columns:
            months = sorted(expenses_df['month'].unique())
            num_months = len(months)
            
            if num_months == 1:
                facts.append(f"**Period:** {months[0]}")
            else:
                facts.append(f"**Period:** {months[0]} to {months[-1]} ({num_months} months)")
        
        # INCOME INFORMATION (if available)
        if income_df is not None and not income_df.empty:
            total_income = income_df[amount_col].sum()
            num_income_transactions = len(income_df)
            facts.append(f"\n**💰 INCOME:**")
            facts.append(f"**Total Income:** ${total_income:,.2f}")
            facts.append(f"**Income Transactions:** {num_income_transactions}")
            
            # Show all income transactions
            if num_income_transactions <= 100:
                facts.append(f"\n**ALL INCOME TRANSACTIONS:**")
                sorted_income = income_df.sort_values(by=date_col, ascending=False)
                for _, row in sorted_income.iterrows():
                    source = row[merchant_col]
                    amount = row[amount_col]
                    date = row[date_col]
                    month_tag = f" [{row['month']}]" if 'month' in row.index else ''
                    facts.append(f"  • {date}{month_tag}: {source} - ${amount:.2f}")
            
            # Calculate net (income - expenses)
            total_expenses = expenses_df[amount_col].sum()
            net_savings = total_income - total_expenses
            facts.append(f"\n**📊 NET SAVINGS:** ${net_savings:,.2f} (Income - Expenses)")
        
        # Basic expense summary
        total_amount = expenses_df[amount_col].sum()
        num_transactions = len(expenses_df)
        facts.append(f"\n**💸 EXPENSES:**")
        facts.append(f"**Total Expenses:** ${total_amount:,.2f}")
        facts.append(f"**Total Transactions:** {num_transactions}")
        
        # Category summary (helpful overview)
        if category_col in expenses_df.columns:
            category_totals = expenses_df.groupby(category_col)[amount_col].sum().sort_values(ascending=False)
            facts.append(f"\n**Category Summary:**")
            for cat, total in category_totals.items():
                count = len(expenses_df[expenses_df[category_col] == cat])
                facts.append(f"  - {cat}: ${total:,.2f} ({count} transactions)")
        
        # ALL TRANSACTIONS - Complete details for LLM to analyze
        if num_transactions <= 300:  # Increased limit
            facts.append(f"\n**ALL TRANSACTION DETAILS:**")
            facts.append("(You can filter, group, calculate averages, find specific merchants, etc. from this data)")
            
            # Sort by date descending
            sorted_df = expenses_df.sort_values(by=date_col, ascending=False)
            
            for _, row in sorted_df.iterrows():
                merchant = row[merchant_col]
                amount = row[amount_col]
                date = row[date_col]
                category = row.get(category_col, 'Uncategorized')
                month_tag = f" [{row['month']}]" if 'month' in row.index else ''
                facts.append(f"  • {date}{month_tag}: {merchant} - ${amount:.2f} ({category})")
        else:
            # Too many transactions - but check if they're asking about a specific merchant
            facts.append(f"\n**Note:** {num_transactions} transactions total (too many to list all)")
            
            # Search for merchant mentions in the question
            unique_merchants = expenses_df[merchant_col].unique()
            merchant_found = False
            
            for merchant in unique_merchants:
                merchant_lower = str(merchant).lower()
                message_lower = user_message.lower()
                
                # Check if merchant name appears in question (match significant words)
                merchant_words = [w for w in merchant_lower.split() if len(w) >= 4]
                
                if merchant_words and any(word in message_lower for word in merchant_words):
                    # Found a merchant mentioned in the question
                    merchant_transactions = expenses_df[expenses_df[merchant_col] == merchant]
                    
                    if not merchant_transactions.empty:
                        merchant_total = merchant_transactions[amount_col].sum()
                        facts.append(f"\n**{merchant} Transactions Found:**")
                        facts.append(f"  - Total spent: ${merchant_total:,.2f}")
                        facts.append(f"  - Number of transactions: {len(merchant_transactions)}")
                        facts.append(f"  - Individual transactions:")
                        
                        for _, row in merchant_transactions.iterrows():
                            date = row[date_col]
                            amount = row[amount_col]
                            category = row.get(category_col, 'Uncategorized')
                            month_tag = f" [{row['month']}]" if 'month' in row.index else ''
                            facts.append(f"    • {date}{month_tag}: ${amount:.2f} ({category})")
                        
                        merchant_found = True
                        break
            
            if not merchant_found:
                facts.append("  → Try asking about a specific month, category, or merchant to see details")
        
        return "\n".join(facts)
    
    def _filter_by_month_mention(self, expenses_df: pd.DataFrame, user_message: str) -> pd.DataFrame:
        """Filter expenses if user mentions a specific month or time range"""
        import re
        from datetime import datetime, timedelta
        
        # Check for relative time references first
        current_date = datetime.now()
        month_name = None
        year = None
        
        # Check for "last year" / "this year" (calendar year)
        if 'last year' in user_message.lower() or 'previous year' in user_message.lower():
            year_filter = str(current_date.year - 1)
            logger.info(f"🔍 Detected 'last year': filtering to {year_filter}")
            
            if 'month' in expenses_df.columns:
                # Filter to all months in that year (YYYY-01 through YYYY-12)
                filtered_df = expenses_df[expenses_df['month'].str.startswith(year_filter)].copy()
                logger.info(f"🔍 Found {len(filtered_df)} expenses for year {year_filter}")
                return filtered_df
        
        elif 'this year' in user_message.lower() or 'current year' in user_message.lower():
            year_filter = str(current_date.year)
            logger.info(f"🔍 Detected 'this year': filtering to {year_filter}")
            
            if 'month' in expenses_df.columns:
                filtered_df = expenses_df[expenses_df['month'].str.startswith(year_filter)].copy()
                logger.info(f"🔍 Found {len(filtered_df)} expenses for year {year_filter}")
                return filtered_df
        
        # Check for "past/last X months/years"
        range_pattern = r'(?:past|last|previous)\s+(\d+)\s+(month|year)s?'
        range_match = re.search(range_pattern, user_message.lower())
        
        if range_match:
            num_periods = int(range_match.group(1))
            period_type = range_match.group(2)
            
            logger.info(f"🔍 Detected time range: {num_periods} {period_type}s")
            
            # Calculate the start month/year
            current_year = current_date.year
            current_month = current_date.month
            
            if period_type == 'month':
                # Calculate months back
                total_months = current_year * 12 + current_month - num_periods
                start_year = total_months // 12
                start_month = total_months % 12
                if start_month == 0:
                    start_month = 12
                    start_year -= 1
            else:  # year
                start_year = current_year - num_periods
                start_month = current_month
            
            start_period = f"{start_year}-{start_month:02d}"
            
            # Filter by month column (format: YYYY-MM)
            if 'month' in expenses_df.columns:
                filtered_df = expenses_df[expenses_df['month'] >= start_period].copy()
                
                logger.info(f"🔍 Filtered to {len(filtered_df)} expenses from {start_period} onwards")
                return filtered_df
        
        if any(phrase in user_message for phrase in ['last month', 'previous month']):
            # Use the latest month that actually has data rather than calendar last month
            if 'month' in expenses_df.columns and not expenses_df.empty:
                latest_available = sorted(expenses_df['month'].unique())[-1]
                try:
                    latest_dt = datetime.strptime(latest_available, '%Y-%m')
                    month_name = latest_dt.strftime('%B').lower()
                    year = str(latest_dt.year)
                except Exception:
                    first_of_current_month = current_date.replace(day=1)
                    last_month_date = first_of_current_month - timedelta(days=1)
                    month_name = last_month_date.strftime('%B').lower()
                    year = str(last_month_date.year)
            else:
                first_of_current_month = current_date.replace(day=1)
                last_month_date = first_of_current_month - timedelta(days=1)
                month_name = last_month_date.strftime('%B').lower()
                year = str(last_month_date.year)
            logger.info(f"🔍 Detected 'last month': using latest available {month_name} {year}")
        
        elif any(phrase in user_message for phrase in ['this month', 'current month']):
            month_name = current_date.strftime('%B').lower()
            year = str(current_date.year)
            logger.info(f"🔍 Detected 'this month': {month_name} {year}")
        
        else:
            # Try to match explicit month with year first
            month_pattern_with_year = r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})'
            month_match = re.search(month_pattern_with_year, user_message)
            
            if month_match:
                month_name = month_match.group(1)
                year = month_match.group(2)
            else:
                # Try to match month only (without year)
                month_pattern_only = r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b'
                month_match = re.search(month_pattern_only, user_message)
                if month_match:
                    month_name = month_match.group(1)
                    year = str(current_date.year)
                    logger.info(f"🔍 Detected month without year: {month_name}, defaulting to {year}")
                else:
                    # No month mentioned, return all data
                    return expenses_df
        
        # Convert month name to number
        month_num = MONTH_TO_NUM[month_name]
        month_filter = f"{year}-{month_num}"
        logger.info(f"🔍 Filtering to month: {month_filter}")
        
        # Filter by month if we have the 'month' column
        if 'month' in expenses_df.columns:
            filtered_df = expenses_df[expenses_df['month'] == month_filter]
            logger.info(f"🔍 Found {len(filtered_df)} expenses for {month_filter}")
            
            # If filtering resulted in no data, return empty DataFrame
            # The pandas facts calculator will handle this appropriately
            if filtered_df.empty:
                logger.info(f"⚠️ No data found for {month_filter}, returning empty DataFrame")
            
            return filtered_df
        
        return expenses_df
    
    def _execute_action(
        self, 
        action_data: Dict, 
        expenses_df: pd.DataFrame,
        month: str
    ) -> Dict[str, Any]:
        """Execute an action requested by the AI"""
        action = action_data.get("action")
        actions_taken = []
        
        if action == "update_expense":
            return {
                "response": action_data.get("message", "Noted."),
                "actions_taken": actions_taken,
                "ai_generated": True,
                "model_name": self.model_name
            }
        
        elif action == "query_expenses":
            # Query and filter expenses
            filtered_df = expenses_df.copy()
            
            # Determine column names
            amount_col = 'Amount' if 'Amount' in filtered_df.columns else 'amount'
            merchant_col = 'Place' if 'Place' in filtered_df.columns else 'merchant'
            date_col = 'Transaction Date' if 'Transaction Date' in filtered_df.columns else 'date'
            category_col = 'category' if 'category' in filtered_df.columns else 'Category'
            
            if "category" in action_data and category_col in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[category_col] == action_data["category"]]
            if "min_amount" in action_data:
                filtered_df = filtered_df[filtered_df[amount_col] >= action_data["min_amount"]]
            if "max_amount" in action_data:
                filtered_df = filtered_df[filtered_df[amount_col] <= action_data["max_amount"]]
            if "merchant_contains" in action_data:
                filtered_df = filtered_df[
                    filtered_df[merchant_col].str.contains(action_data["merchant_contains"], case=False, na=False)
                ]
            
            # Format expense list
            expense_list = []
            for idx, row in filtered_df.iterrows():
                expense_list.append({
                    "index": idx,
                    "date": row[date_col],
                    "merchant": row[merchant_col],
                    "amount": float(row[amount_col]),
                    "category": row.get(category_col, 'Uncategorized'),
                })
            
            return {
                "response": action_data.get("message", f"Found {len(expense_list)} expenses."),
                "expenses": expense_list,
                "actions_taken": actions_taken,
                "ai_generated": True,
                "model_name": self.model_name
            }
        
        # Unknown action
        return {
            "response": action_data.get("message", "I'm not sure how to help with that."),
            "actions_taken": actions_taken,
            "ai_generated": True,
            "model_name": self.model_name
        }
    
    def _generate_fallback_response(
        self, 
        message: str, 
        expenses_df: pd.DataFrame,
        month: str
    ) -> Dict[str, Any]:
        """Generate a simple rule-based response when AI is unavailable"""
        message_lower = message.lower()
        
        # Determine column names
        amount_col = 'Amount' if 'Amount' in expenses_df.columns else 'amount'
        merchant_col = 'Place' if 'Place' in expenses_df.columns else 'merchant'
        date_col = 'Transaction Date' if 'Transaction Date' in expenses_df.columns else 'date'
        category_col = 'category' if 'category' in expenses_df.columns else 'Category'
        
        # Check for "largest" or "biggest" queries
        if any(word in message_lower for word in ['largest', 'biggest', 'most expensive', 'top']):
            # Show top 5 expenses
            top_expenses = expenses_df.nlargest(5, amount_col)
            expense_list = []
            for idx, row in top_expenses.iterrows():
                expense_list.append({
                    "index": idx,
                    "date": row[date_col],
                    "merchant": row[merchant_col],
                    "amount": float(row[amount_col]),
                    "category": row.get(category_col, 'Uncategorized'),
                })
            
            top_expense = expense_list[0]
            return {
                "response": f"Your largest expense in {month} was ${top_expense['amount']:.2f} at {top_expense['merchant']} on {top_expense['date']}. Here are your top 5 expenses:",
                "expenses": expense_list,
                "actions_taken": [],
                "ai_generated": False
            }
        
        # Simple keyword matching for categories
        if any(word in message_lower for word in ['shopping', 'shop']):
            category = 'Shopping'
        elif any(word in message_lower for word in ['dining', 'restaurant', 'food']):
            category = 'Dining'
        elif any(word in message_lower for word in ['groceries', 'grocery']):
            category = 'Groceries'
        elif any(word in message_lower for word in ['entertainment', 'movie', 'game']):
            category = 'Entertainment'
        else:
            category = None
        
        if category and category_col in expenses_df.columns:
            filtered_df = expenses_df[expenses_df[category_col] == category]
            
            if filtered_df.empty:
                return {
                    "response": f"No {category} expenses found for {month}.",
                    "actions_taken": [],
                    "ai_generated": False
                }
            
            # Build expense list
            expense_list = []
            for idx, row in filtered_df.iterrows():
                expense_list.append({
                    "index": idx,
                    "date": row[date_col],
                    "merchant": row[merchant_col],
                    "amount": float(row[amount_col]),
                    "category": row.get(category_col, 'Uncategorized'),
                    "one_time_purchase": bool(row.get('one_time_purchase', False)),
                    "notes": row.get('user_notes', '')
                })
            
            # If asking about largest in category, show top items
            if any(word in message_lower for word in ['largest', 'biggest', 'most']):
                top_in_category = filtered_df.nlargest(5, amount_col)
                expense_list = []
                for idx, row in top_in_category.iterrows():
                    expense_list.append({
                        "index": idx,
                        "date": row[date_col],
                        "merchant": row[merchant_col],
                        "amount": float(row[amount_col]),
                        "category": row.get(category_col, 'Uncategorized'),
                        "one_time_purchase": bool(row.get('one_time_purchase', False)),
                        "notes": row.get('user_notes', '')
                    })
                
                largest = top_in_category.iloc[0]
                return {
                    "response": f"Your largest {category} expense was ${largest[amount_col]:.2f} at {largest[merchant_col]} on {largest[date_col]}. Here are the top {len(expense_list)}:",
                    "expenses": expense_list,
                    "actions_taken": [],
                    "ai_generated": False
                }
            
            # Regular category listing
            total = filtered_df[amount_col].sum()
            return {
                "response": f"Here are your {category} expenses for {month}. Total: ${total:.2f}",
                "expenses": expense_list,
                "actions_taken": [],
                "ai_generated": False
            }
        
        # Generic response
        total_expenses = expenses_df[amount_col].sum()
        num_transactions = len(expenses_df)
        return {
            "response": f"For {month}, you have {num_transactions} transactions totaling ${total_expenses:.2f}. Try asking about specific categories like 'shopping', 'dining', or 'groceries', or ask about your 'largest expenses'.",
            "actions_taken": [],
            "ai_generated": False
        }
