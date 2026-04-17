"""routes/analytics.py — AI insights, forecasting, trends, budget, and chat endpoints."""

import json
import logging
import math
import os
from pathlib import Path

import requests
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.ui.backend.deps import (
    _PROJECT_ROOT,
    _query_df,
)

_OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')

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
def get_budget_suggestions(analysis_months: int = 3, savings_target: float = None, strategy: str = '50/30/20'):
    """Get AI-powered (or rule-based) budget suggestions based on recent spending."""
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor
        from src.ai_analysis.model_loader import FinGPTModelLoader
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt

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

        # Load any user-saved bucket overrides from budget_goals table
        bucket_overrides: dict = {}
        try:
            engine = _get_eng()
            with engine.connect() as conn:
                rows = conn.execute(_sqlt(
                    "SELECT category, bucket FROM budget_goals WHERE bucket IS NOT NULL AND bucket_override=1"
                )).fetchall()
                bucket_overrides = {r[0]: r[1] for r in rows}
                # Also load settings for savings target
                if savings_target is None:
                    settings_row = conn.execute(_sqlt(
                        "SELECT savings_target_amount, savings_target_pct, strategy FROM budget_settings WHERE id=1"
                    )).fetchone()
                    if settings_row:
                        if settings_row[0]:
                            savings_target = float(settings_row[0])
                        elif settings_row[1] and avg_monthly_income > 0:
                            savings_target = avg_monthly_income * float(settings_row[1]) / 100
                        if settings_row[2]:
                            strategy = settings_row[2]
        except Exception as _e:
            logging.warning(f"Could not load budget settings from DB: {_e}")

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

        suggestions = advisor.suggest_monthly_budgets(
            historical_df,
            months=analysis_months,
            avg_monthly_income=avg_monthly_income,
            strategy=strategy,
            savings_target=savings_target,
            bucket_overrides=bucket_overrides,
        )
        logging.info(f"💰 Generated budget suggestions (AI: {suggestions.get('ai_generated', False)}, income: ${avg_monthly_income:,.2f})")

        # Cache ai_cap and historical_avg back to budget_goals (upsert, don't overwrite user goals)
        try:
            engine = _get_eng()
            with engine.connect() as conn:
                for cat, b in suggestions.get('suggested_budgets', {}).items():
                    conn.execute(_sqlt("""
                        INSERT INTO budget_goals (category, ai_cap, historical_avg, bucket)
                        VALUES (:cat, :cap, :avg, :bucket)
                        ON CONFLICT(category) DO UPDATE SET
                            ai_cap         = excluded.ai_cap,
                            historical_avg = excluded.historical_avg,
                            bucket         = CASE WHEN bucket_override=1 THEN bucket ELSE excluded.bucket END
                    """), {
                        'cat':    cat,
                        'cap':    b.get('ai_cap'),
                        'avg':    b.get('historical_avg'),
                        'bucket': b.get('bucket'),
                    })
                # Also store avg income used
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(_sqlt("""
                    INSERT INTO budget_settings (id, avg_monthly_income_used, strategy, updated_at)
                    VALUES (1, :inc, :strat, :ts)
                    ON CONFLICT(id) DO UPDATE SET
                        avg_monthly_income_used = excluded.avg_monthly_income_used,
                        strategy = excluded.strategy,
                        updated_at = excluded.updated_at
                """), {'inc': avg_monthly_income, 'strat': strategy, 'ts': now})
                conn.commit()
        except Exception as _ce:
            logging.warning(f"Could not cache suggestions to DB: {_ce}")

        return suggestions

    except Exception as e:
        logging.exception("Failed to generate budget suggestions")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Budget comparison ─────────────────────────────────────────────────────────

@router.get("/api/budget/goals/months")
def get_budget_goal_months():
    """Return a list of distinct months that have saved per-month budget goals."""
    try:
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt
        engine = _get_eng()
        with engine.connect() as conn:
            rows = conn.execute(_sqlt(
                "SELECT DISTINCT month FROM budget_goals_monthly ORDER BY month DESC"
            )).fetchall()
        return {"months": [r[0] for r in rows]}
    except Exception as e:
        logging.exception("Failed to load budget goal months")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/budget/goals")
def get_budget_goals(month: str = None):
    """Return saved budget goals, preferring per-month goals when month is provided."""
    try:
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt
        engine = _get_eng()
        with engine.connect() as conn:
            # Always load the global template (bucket, ai_cap, historical_avg)
            global_rows = conn.execute(_sqlt(
                "SELECT category, goal_amount, ai_cap, historical_avg, bucket, bucket_override "
                "FROM budget_goals"
            )).fetchall()
            settings_row = conn.execute(_sqlt(
                "SELECT savings_target_amount, savings_target_pct, strategy, avg_monthly_income_used "
                "FROM budget_settings WHERE id=1"
            )).fetchone()

            # Load per-month goals if a month was supplied
            monthly_rows = []
            has_month_goals = False
            if month:
                try:
                    monthly_rows = conn.execute(_sqlt(
                        "SELECT category, goal_amount FROM budget_goals_monthly WHERE month=:m"
                    ), {'m': month}).fetchall()
                    has_month_goals = len(monthly_rows) > 0
                except Exception:
                    pass  # table may not exist yet on first run

            # Load the list of months that have saved goals
            saved_months = []
            try:
                saved_months = [r[0] for r in conn.execute(_sqlt(
                    "SELECT DISTINCT month FROM budget_goals_monthly ORDER BY month DESC"
                )).fetchall()]
            except Exception:
                pass

        # Build goal_details from global rows (bucket, ai_cap, historical_avg)
        goal_details = {
            r[0]: {
                'goal_amount':    r[1],
                'ai_cap':         r[2],
                'historical_avg': r[3],
                'bucket':         r[4],
                'bucket_override': bool(r[5]),
            }
            for r in global_rows
        }

        # Overlay per-month goal_amounts when available
        monthly_amounts = {r[0]: r[1] for r in monthly_rows if r[1] is not None}
        if monthly_amounts:
            for cat, amt in monthly_amounts.items():
                if cat in goal_details:
                    goal_details[cat]['goal_amount'] = amt
                else:
                    goal_details[cat] = {'goal_amount': amt, 'ai_cap': None,
                                         'historical_avg': None, 'bucket': None,
                                         'bucket_override': False}

        # goals = flat {category: amount} for backward compat
        goals = {cat: d['goal_amount'] for cat, d in goal_details.items()
                 if d['goal_amount'] is not None}

        settings_dict: dict = {}
        if settings_row:
            settings_dict = {
                'savings_target_amount':   settings_row[0],
                'savings_target_pct':      settings_row[1],
                'strategy':                settings_row[2] or '50/30/20',
                'avg_monthly_income_used': settings_row[3],
            }
        return {
            'goals':           goals,
            'goal_details':    goal_details,
            'settings':        settings_dict,
            'has_goals':       len(goals) > 0,
            'has_month_goals': has_month_goals,
            'saved_months':    saved_months,
        }
    except Exception as e:
        logging.exception("Failed to load budget goals")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/budget/goals")
async def save_budget_goals_db(body: dict = Body(...)):
    """Save budget goals to the database.
    When a 'month' is provided the goal_amounts are saved per-month in
    budget_goals_monthly.  Bucket overrides and settings always write to the
    global tables (budget_goals / budget_settings).
    """
    try:
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt
        from datetime import datetime, timezone

        # Accept both {budgets: {...}, settings: {...}, bucket_overrides: {...}} and a flat {category: amount} map
        budgets          = body.get('budgets', body if not body.get('settings') else {})
        settings         = body.get('settings', {})
        bucket_overrides = body.get('bucket_overrides', {})
        month            = body.get('month')  # YYYY-MM, or None for global template
        now = datetime.now(timezone.utc).isoformat()

        engine = _get_eng()
        with engine.connect() as conn:
            if month:
                # Save per-month goal amounts to budget_goals_monthly
                for category, amount in budgets.items():
                    if amount is None:
                        continue
                    conn.execute(_sqlt("""
                        INSERT INTO budget_goals_monthly (month, category, goal_amount, updated_at)
                        VALUES (:m, :cat, :amt, :ts)
                        ON CONFLICT(month, category) DO UPDATE SET
                            goal_amount = excluded.goal_amount,
                            updated_at  = excluded.updated_at
                    """), {'m': month, 'cat': category, 'amt': float(amount), 'ts': now})
                # Also upsert global budget_goals row so bucket/ai_cap stay fresh
                for category, amount in budgets.items():
                    if amount is None:
                        continue
                    conn.execute(_sqlt("""
                        INSERT INTO budget_goals (category, goal_amount, updated_at)
                        VALUES (:cat, :amt, :ts)
                        ON CONFLICT(category) DO UPDATE SET
                            goal_amount = excluded.goal_amount,
                            updated_at  = excluded.updated_at
                    """), {'cat': category, 'amt': float(amount), 'ts': now})
            else:
                # No month specified — write to global template only
                for category, amount in budgets.items():
                    if amount is None:
                        continue
                    conn.execute(_sqlt("""
                        INSERT INTO budget_goals (category, goal_amount, updated_at)
                        VALUES (:cat, :amt, :ts)
                        ON CONFLICT(category) DO UPDATE SET
                            goal_amount = excluded.goal_amount,
                            updated_at  = excluded.updated_at
                    """), {'cat': category, 'amt': float(amount), 'ts': now})

            # Bucket overrides are always global (describe the category, not the month)
            for category, bucket in bucket_overrides.items():
                conn.execute(_sqlt("""
                    INSERT INTO budget_goals (category, bucket, bucket_override, updated_at)
                    VALUES (:cat, :bkt, 1, :ts)
                    ON CONFLICT(category) DO UPDATE SET
                        bucket          = excluded.bucket,
                        bucket_override = 1,
                        updated_at      = excluded.updated_at
                """), {'cat': category, 'bkt': bucket, 'ts': now})

            if settings:
                conn.execute(_sqlt("""
                    INSERT INTO budget_settings
                        (id, savings_target_amount, savings_target_pct, strategy, updated_at)
                    VALUES (1, :sta, :stp, :strat, :ts)
                    ON CONFLICT(id) DO UPDATE SET
                        savings_target_amount = COALESCE(excluded.savings_target_amount, savings_target_amount),
                        savings_target_pct    = COALESCE(excluded.savings_target_pct,    savings_target_pct),
                        strategy              = COALESCE(excluded.strategy,              strategy),
                        updated_at            = excluded.updated_at
                """), {
                    'sta':   settings.get('savings_target_amount'),
                    'stp':   settings.get('savings_target_pct'),
                    'strat': settings.get('strategy'),
                    'ts':    now,
                })

            conn.commit()

        month_label = f" for {month}" if month else " (global template)"
        logging.info(f"💾 Saved budget goals{month_label} — {len(budgets)} categories")
        return {"success": True, "message": f"Saved goals for {len(budgets)} categories"}
    except Exception as e:
        logging.exception("Failed to save budget goals to DB")
        return JSONResponse(status_code=500, content={"error": str(e)})


# Keep old endpoint as a thin alias so any existing clients don't break
@router.post("/api/budget/save")
async def save_budget_goals_legacy(budgets: dict = Body(...)):
    """Deprecated — use POST /api/budget/goals instead."""
    # Convert old {category: {suggested_amount: X, ...}} shape to flat {category: amount}
    flat: dict = {}
    for cat, val in budgets.items():
        if isinstance(val, dict):
            flat[cat] = val.get('suggested_amount', val.get('goal_amount'))
        elif isinstance(val, (int, float)):
            flat[cat] = val
    return await save_budget_goals_db({'budgets': flat})


@router.get("/api/budget/{month}")
def get_budget_comparison(month: str):
    """Compare actual spending to saved budget goals for a specific month."""
    try:
        from src.ai_analysis.budget_advisor import BudgetAdvisor
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt

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

        # Read goals — prefer per-month goals, fall back to global template
        try:
            engine = _get_eng()
            with engine.connect() as conn:
                # Per-month goals (may not exist for older data or first run)
                monthly_goals = {}
                try:
                    mrows = conn.execute(_sqlt(
                        "SELECT category, goal_amount FROM budget_goals_monthly "
                        "WHERE month=:m AND goal_amount IS NOT NULL"
                    ), {'m': month}).fetchall()
                    monthly_goals = {r[0]: r[1] for r in mrows}
                except Exception:
                    pass  # table doesn't exist yet — fall through to global

                # Global template fallback
                global_goals = {}
                grows = conn.execute(_sqlt(
                    "SELECT category, goal_amount FROM budget_goals WHERE goal_amount IS NOT NULL"
                )).fetchall()
                global_goals = {r[0]: r[1] for r in grows}

            # Monthly goals take priority; global fills in any missing categories
            merged_goals = {**global_goals, **monthly_goals}
            budget_goals = {
                cat: {'suggested_amount': float(amt), 'priority': 'Important'}
                for cat, amt in merged_goals.items()
            }
        except Exception as db_err:
            logging.warning(f"Failed to read budget goals from DB: {db_err}")
            budget_goals = {}

        if not budget_goals:
            return JSONResponse(
                status_code=404,
                content={"error": "No budget goals found. Set your budget first."}
            )

        advisor = BudgetAdvisor(use_ai=False)
        comparison = advisor.compare_to_budget(expenses_df, budget_goals)
        comparison['one_time_total'] = one_time_total
        comparison['month'] = month

        # Attach budget_history rows for variance trend (last 3 months per category)
        try:
            with engine.connect() as conn:
                hist_rows = conn.execute(_sqlt("""
                    SELECT category, report_month, goal, actual, variance, variance_pct
                    FROM budget_history
                    WHERE report_month <= :m
                    ORDER BY report_month DESC
                    LIMIT 200
                """), {'m': month}).fetchall()
            history_by_cat: dict = {}
            for row in hist_rows:
                cat = row[0]
                if cat not in history_by_cat:
                    history_by_cat[cat] = []
                if len(history_by_cat[cat]) < 3:
                    history_by_cat[cat].append({
                        'month': row[1], 'goal': row[2], 'actual': row[3],
                        'variance': row[4], 'variance_pct': row[5]
                    })
            comparison['variance_trend'] = history_by_cat
        except Exception:
            comparison['variance_trend'] = {}

        return comparison

    except Exception as e:
        logging.exception("Failed to compare budget")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/budget/debrief/{month}")
async def get_budget_debrief(month: str):
    """Generate (or return cached) AI coaching narrative for a processed month."""
    try:
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt
        from datetime import datetime, timezone

        engine = _get_eng()

        # Check cache first
        with engine.connect() as conn:
            rows = conn.execute(_sqlt(
                "SELECT category, goal, actual, variance, coaching_note "
                "FROM budget_history WHERE report_month=:m",
            ), {'m': month}).fetchall()

        if not rows:
            return JSONResponse(status_code=404, content={"error": f"No budget history for {month}"})

        # If any row has a coaching_note, return it (cached)
        for row in rows:
            if row[4]:
                return {"month": month, "coaching_note": row[4], "cached": True}

        # Build debrief prompt from the history rows
        total_goal = sum(r[1] or 0 for r in rows)
        total_actual = sum(r[2] or 0 for r in rows)
        surplus = total_goal - total_actual
        over_cats = [(r[0], r[2], r[1]) for r in rows if r[1] and r[2] and r[2] > r[1]]
        under_cats = [(r[0], r[2], r[1]) for r in rows if r[1] and r[2] and r[2] <= r[1] and r[2] > 0]
        savings_rate = None
        income_rows = _query_df('income', months=[month])
        if not income_rows.empty:
            amt_col = next((c for c in income_rows.columns if c.lower() == 'amount'), 'amount')
            total_income = float(income_rows[amt_col].sum())
            if total_income > 0:
                savings_rate = round((total_income - total_actual) / total_income * 100, 1)

        over_lines = '\n'.join(
            f"  {cat}: spent ${actual:.2f} vs ${goal:.2f} goal (+${actual-goal:.2f})"
            for cat, actual, goal in sorted(over_cats, key=lambda x: x[1]-x[2], reverse=True)[:5]
        )
        under_lines = '\n'.join(
            f"  {cat}: spent ${actual:.2f} vs ${goal:.2f} goal (-${goal-actual:.2f})"
            for cat, actual, goal in sorted(under_cats, key=lambda x: x[2]-x[1], reverse=True)[:5]
        )

        prompt = f"""Write a concise 3-5 sentence budget coaching note for {month}.

Budget summary:
  Total budget: ${total_goal:.2f}
  Total actual spend: ${total_actual:.2f}
  {'Surplus: $' + f'{surplus:.2f}' if surplus > 0 else 'Deficit: $' + f'{-surplus:.2f}'}
{f'  Savings rate: {savings_rate:.1f}%' if savings_rate is not None else ''}

Over-budget categories:
{over_lines or '  (none)'}

Under-budget categories:
{under_lines or '  (none)'}

Be specific, practical, and warm. Mention 1-2 categories by name. Keep it under 100 words."""

        note = None
        try:
            from src.ai_analysis.model_loader import FinGPTModelLoader
            model_loader = FinGPTModelLoader()
            if getattr(model_loader, 'available', False):
                note = model_loader.generate_insight(prompt, temperature=0.4, max_tokens=200)
        except Exception as _e:
            logging.warning(f"LLM debrief generation failed: {_e}")

        if not note:
            # Rule-based fallback
            if surplus > 0:
                note = (f"{month}: You came in ${surplus:.2f} under budget overall — great work! "
                        + (f"Biggest wins: {', '.join(c for c,_,_ in under_cats[:2])}. " if under_cats else '')
                        + (f"Watch {over_cats[0][0]} — it went ${over_cats[0][1]-over_cats[0][2]:.2f} over goal." if over_cats else ''))
            else:
                note = (f"{month}: You went ${-surplus:.2f} over budget this month. "
                        + (f"Main driver: {over_cats[0][0]} at ${over_cats[0][1]:.2f} vs ${over_cats[0][2]:.2f} goal. " if over_cats else '')
                        + "Review these categories and adjust goals if they reflect a new baseline.")

        # Cache the note in every history row for this month
        now_iso = datetime.now(timezone.utc).isoformat()
        with engine.connect() as conn:
            conn.execute(_sqlt(
                "UPDATE budget_history SET coaching_note=:note WHERE report_month=:m"
            ), {'note': note, 'm': month})
            conn.commit()

        return {"month": month, "coaching_note": note, "cached": False}

    except Exception as e:
        logging.exception("Failed to generate budget debrief")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/budget/history")
def get_budget_history(months: int = 6):
    """Return budget_history rows for the trend chart."""
    try:
        from src.database.session import get_engine as _get_eng
        from sqlalchemy import text as _sqlt

        engine = _get_eng()
        with engine.connect() as conn:
            rows = conn.execute(_sqlt("""
                SELECT report_month, category, goal, actual, variance, variance_pct, coaching_note
                FROM budget_history
                ORDER BY report_month DESC, category
                LIMIT :lim
            """), {'lim': months * 50}).fetchall()  # rough upper bound

        by_month: dict = {}
        for row in rows:
            m = row[0]
            if m not in by_month:
                by_month[m] = {'month': m, 'categories': {}, 'coaching_note': None}
            by_month[m]['categories'][row[1]] = {
                'goal': row[2], 'actual': row[3],
                'variance': row[4], 'variance_pct': row[5],
            }
            if row[6]:
                by_month[m]['coaching_note'] = row[6]

        sorted_months = sorted(by_month.values(), key=lambda x: x['month'], reverse=True)[:months]
        for m_data in sorted_months:
            cats = m_data['categories']
            m_data['total_goal']   = sum(v['goal']   or 0 for v in cats.values())
            m_data['total_actual'] = sum(v['actual'] or 0 for v in cats.values())
            total_goal = m_data['total_goal']
            total_actual = m_data['total_actual']
            m_data['attainment_pct'] = (
                round((1 - abs(total_actual - total_goal) / total_goal) * 100, 1)
                if total_goal > 0 else None
            )

        return sorted_months

    except Exception as e:
        logging.exception("Failed to fetch budget history")
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
