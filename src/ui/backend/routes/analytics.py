"""routes/analytics.py — AI insights, forecasting, trends, budget, and chat endpoints."""

import json
import logging
import math
import os
from pathlib import Path

import requests

_OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _PROJECT_ROOT,
    _query_df,
)

router = APIRouter()


def _strip_one_time(df) -> object:
    """Remove label='one-time' rows so forecasts/insights/budgets use only recurring spending."""
    lbl = next((c for c in df.columns if c.lower() == 'label'), None)
    if lbl is None:
        return df
    return df[df[lbl].astype(str).str.strip().str.lower() != 'one-time'].copy()


# ── Insights ──────────────────────────────────────────────────────────────────

@router.get("/api/insights/{month}")
def get_monthly_insights(month: str):
    """Get AI-generated (or rule-based) insights for a specific month."""
    try:
        from src.ai_analysis.insights_generator import InsightsGenerator
        from src.ai_analysis.model_loader import FinGPTModelLoader

        expenses_df = _query_df('expense', months=[month])
        if expenses_df.empty:
            return JSONResponse(status_code=404, content={"error": f"No data found for {month}"})
        expenses_df = _strip_one_time(expenses_df)

        year, month_num = map(int, month.split('-'))
        prev_month_num = month_num - 1 if month_num > 1 else 12
        prev_year = year if month_num > 1 else year - 1
        prev_month = f"{prev_year:04d}-{prev_month_num:02d}"
        prev_expenses_df = _query_df('expense', months=[prev_month])
        if prev_expenses_df.empty:
            prev_expenses_df = None
        else:
            prev_expenses_df = _strip_one_time(prev_expenses_df)

        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model: {e}")

        if model_loader and getattr(model_loader, 'available', False):
            generator = InsightsGenerator(model_loader=model_loader, use_ai=True)
            logging.info(f"✨ Generating AI insights using model: {generator.model_name}")
        else:
            logging.info("📊 Using rule-based insights (no financial model configured)")
            generator = InsightsGenerator(use_ai=False)

        insights = generator.generate_monthly_insights(month, expenses_df, prev_expenses_df)
        logging.info(f"📊 Generated insights for {month} (AI: {insights.get('ai_generated', False)})")
        return insights

    except Exception as e:
        logging.exception("Failed to generate insights")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Forecast ──────────────────────────────────────────────────────────────────

@router.get("/api/forecast")
def get_budget_forecast(months_ahead: int = 1, savings_goal: float = None,
                        filter_outliers: bool = True):
    """Get budget forecast based on historical expense data."""
    try:
        from src.ai_analysis.forecaster import BudgetForecaster
        from src.ai_analysis.model_loader import FinGPTModelLoader

        historical_df = _query_df('expense')
        if historical_df.empty:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})

        historical_df = _strip_one_time(historical_df)
        historical_df = historical_df.fillna('')
        n_months = historical_df['month'].nunique() if 'month' in historical_df.columns else 1

        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model for forecasting: {e}")

        if model_loader and getattr(model_loader, 'available', False):
            forecaster = BudgetForecaster(model_loader=model_loader, use_ai=True,
                                          filter_outliers=filter_outliers, outlier_threshold=1.5)
            logging.info(f"Using AI-powered forecasting with {model_loader.financial_model}")
        else:
            logging.info("Using statistical forecasting (no financial model configured)")
            forecaster = BudgetForecaster(use_ai=False, filter_outliers=filter_outliers,
                                          outlier_threshold=1.5)

        forecast = forecaster.forecast_total(historical_df, months_ahead)

        def _sanitise(obj):
            if isinstance(obj, float):
                return None if (math.isnan(obj) or math.isinf(obj)) else obj
            if isinstance(obj, dict):
                return {k: _sanitise(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitise(v) for v in obj]
            return obj
        forecast = _sanitise(forecast)

        if savings_goal is not None:
            historical_avg = historical_df['Amount'].sum() / n_months if n_months else 0
            recommendations = forecaster.create_budget_recommendations(forecast, historical_avg, savings_goal)
            forecast['recommendations'] = recommendations

        return forecast

    except Exception as e:
        logging.exception("Failed to generate forecast")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Trends ────────────────────────────────────────────────────────────────────

@router.get("/api/trends")
def get_spending_trends(months: int = 6):
    """Analyze spending trends over recent months."""
    try:
        from src.ai_analysis.forecaster import BudgetForecaster

        historical_df = _query_df('expense', recent_n=months)
        if historical_df.empty:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})

        historical_df = _strip_one_time(historical_df)
        forecaster = BudgetForecaster(use_ai=False)
        return forecaster.analyze_trends(historical_df, months)

    except Exception as e:
        logging.exception("Failed to analyze trends")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Budget suggestions ────────────────────────────────────────────────────────

@router.get("/api/budget-suggestions")
def get_budget_suggestions(analysis_months: int = 3):
    """Get AI-powered (or rule-based) budget suggestions based on recent spending."""
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor
        from src.ai_analysis.model_loader import FinGPTModelLoader

        historical_df = _query_df('expense', recent_n=analysis_months)
        if historical_df.empty:
            return JSONResponse(status_code=404, content={"error": "No historical data found"})

        _lbl_col = next((c for c in historical_df.columns if c.lower() == 'label'), None)
        if _lbl_col:
            _one_time_mask = historical_df[_lbl_col].astype(str).str.strip().str.lower() == 'one-time'
            _n_one_time = int(_one_time_mask.sum())
            if _n_one_time > 0:
                logging.info(f"📊 Excluding {_n_one_time} one-time expense(s) from budget projection averages")
            historical_df = historical_df[~_one_time_mask]

        income_df = _query_df('income', recent_n=analysis_months)
        total_income = 0.0
        income_months_used: list = []
        _skipped_bonus_count = 0
        if not income_df.empty:
            _amt = next((c for c in income_df.columns if c.lower() == 'amount'), None)
            _lbl = next((c for c in income_df.columns if c.lower() == 'label'), None)
            _pl  = next((c for c in income_df.columns if c.lower() == 'place'), None)
            _mo  = next((c for c in income_df.columns if c == 'month'), None)
            if _amt and _mo:
                for month_str, grp in income_df.groupby(_mo):
                    month_total = 0.0
                    for _, irow in grp.iterrows():
                        try:
                            amount = float(irow[_amt])
                        except Exception:
                            continue
                        lbl = str(irow[_lbl]).strip().lower() if _lbl else 'recurring'
                        if lbl == 'bonus':
                            _skipped_bonus_count += 1
                            place = str(irow[_pl]).upper() if _pl else ''
                            logging.info(f"📊 Skipping bonus income ${amount:,.2f} ({place}) from avg baseline")
                            continue
                        month_total += amount
                    total_income += month_total
                    income_months_used.append(month_str)
        avg_monthly_income = (total_income / len(income_months_used)) if income_months_used else 0.0
        if _skipped_bonus_count:
            logging.info(f"📊 Excluded {_skipped_bonus_count} bonus income deposit(s) from avg baseline")
        logging.info(f"💵 Avg monthly recurring income: ${avg_monthly_income:,.2f} (from {len(income_months_used)} months)")

        model_loader = None
        try:
            model_loader = FinGPTModelLoader()
        except Exception as e:
            logging.warning(f"Could not load financial model for budget suggestions: {e}")

        if model_loader and getattr(model_loader, 'available', False):
            advisor = BudgetAdvisor(model_loader=model_loader, use_ai=True)
            logging.info(f"✨ Generating AI budget suggestions using {model_loader.financial_model}")
        else:
            logging.info("📊 Generating rule-based budget suggestions")
            advisor = BudgetAdvisor(use_ai=False)

        suggestions = advisor.suggest_monthly_budgets(historical_df, months=analysis_months, avg_monthly_income=avg_monthly_income)
        logging.info(f"💰 Generated budget suggestions (AI: {suggestions.get('ai_generated', False)}, income: ${avg_monthly_income:,.2f})")
        return suggestions

    except Exception as e:
        logging.exception("Failed to generate budget suggestions")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Budget comparison ─────────────────────────────────────────────────────────

@router.get("/api/budget/{month}")
def get_budget_comparison(month: str):
    """Compare actual spending to saved budget goals for a specific month."""
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor

        all_expenses_df = _query_df('expense', months=[month])
        if all_expenses_df.empty:
            return JSONResponse(status_code=404, content={"error": f"No data for month {month}"})

        # Split one-time out before budget comparison so actual spend reflects only recurring
        _lbl = next((c for c in all_expenses_df.columns if c.lower() == 'label'), None)
        if _lbl:
            _ot_mask = all_expenses_df[_lbl].astype(str).str.strip().str.lower() == 'one-time'
            one_time_total = round(float(all_expenses_df.loc[_ot_mask, 'Amount'].sum()), 2)
            expenses_df = all_expenses_df[~_ot_mask].copy()
        else:
            one_time_total = 0.0
            expenses_df = all_expenses_df

        budget_file = _PROJECT_ROOT / 'config' / 'budgets.json'
        if not budget_file.exists():
            return JSONResponse(status_code=404, content={"error": "No budget goals found. Generate suggestions first."})

        with open(budget_file, 'r') as f:
            budget_data = json.load(f)
            budget_goals = budget_data.get('budgets', {})

        if not budget_goals:
            return JSONResponse(status_code=404, content={"error": "No budget goals found."})

        advisor = BudgetAdvisor(use_ai=False)
        comparison = advisor.compare_to_budget(expenses_df, budget_goals)
        comparison['one_time_total'] = one_time_total
        comparison['month'] = month
        return comparison

    except Exception as e:
        logging.exception("Failed to compare budget")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/budget/save")
async def save_budget_goals(budgets: dict = Body(...)):
    """Save user's budget goals to config/budgets.json."""
    try:
        budget_file = _PROJECT_ROOT / 'config' / 'budgets.json'
        with open(budget_file, 'w') as f:
            json.dump({'budgets': budgets}, f, indent=2)
        logging.info(f"💾 Saved budget goals for {len(budgets)} categories")
        return {"success": True, "message": f"Saved budgets for {len(budgets)} categories"}
    except Exception as e:
        logging.exception("Failed to save budgets")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.get("/api/chat/available")
async def check_chat_availability():
    """Check if AI chatbot is available (Ollama + model configured)."""
    try:
        config_path = _PROJECT_ROOT / 'config' / 'llm_models.json'
        if not config_path.exists():
            return {"available": False, "model_name": None}

        with open(config_path) as f:
            config = json.load(f)

        model_name = config.get('financial_analysis_model', '')
        if not model_name:
            return {"available": False, "model_name": None}

        try:
            resp = requests.get(f'{_OLLAMA_HOST}/api/tags', timeout=3)
            model_names = [m['name'] for m in resp.json().get('models', [])]
            is_available = any(
                model_name in name or name.startswith(model_name + ':')
                for name in model_names
            )
            logging.info(f"💬 Chat availability check: {model_name} - {'Available' if is_available else 'Not found'}")
            return {"available": is_available, "model_name": model_name if is_available else None}
        except Exception as e:
            logging.warning(f"Could not check Ollama models: {e}")
            return {"available": False, "model_name": None}

    except Exception as e:
        logging.error(f"Chat availability check failed: {e}")
        return {"available": False, "model_name": None}


@router.post("/api/chat")
async def chat_with_assistant(request: dict = Body(...)):
    """Interactive AI chatbot for financial analysis and expense management."""
    try:
        from src.ai_analysis.chatbot_assistant import ChatbotAssistant

        month = request.get('month')
        message = request.get('message')
        conversation_history = request.get('conversation_history', [])

        if not message:
            return JSONResponse(status_code=400, content={"error": "Missing required field: message"})

        config_path = _PROJECT_ROOT / 'config' / 'llm_models.json'
        model_name = None

        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                model_name = config.get('financial_analysis_model', '')

        if model_name:
            try:
                resp = requests.get(f'{_OLLAMA_HOST}/api/tags', timeout=3)
                model_names = [m['name'] for m in resp.json().get('models', [])]
                is_available = any(
                    model_name in name or name.startswith(model_name + ':')
                    for name in model_names
                )
                if is_available:
                    logging.info(f"🤖 Chat using Ollama model: {model_name}")
                else:
                    logging.info("📊 Chat using rule-based fallback (model not found)")
                    model_name = None
            except Exception as e:
                logging.warning(f"Could not verify Ollama model: {e}")
                model_name = None
        else:
            logging.info("📊 Chat using rule-based fallback (no model configured)")

        chatbot = ChatbotAssistant(model_name=model_name)
        result = chatbot.process_message(month, message, conversation_history)

        expenses_count = len(result.get('expenses') or []) if result.get('expenses') is not None else 0
        logging.info(f"💬 Chat processed: {message[:50]}... → {expenses_count} expenses returned")

        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )

    except Exception as e:
        logging.exception("Failed to process chat message")
        return JSONResponse(status_code=500, content={"error": str(e)})
