#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Budget Advisor
Uses LLM to analyze spending patterns and suggest realistic budget goals.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import json

logger = logging.getLogger(__name__)

# ── Heuristic bucket map ─────────────────────────────────────────────────────
# Covers the ~80% common case; anything not in this map gets LLM classification.
_HEURISTIC_BUCKETS: Dict[str, str] = {
    # Needs
    'Rent/Mortgage': 'Need', 'Housing': 'Need',
    'Electric': 'Need', 'Natural Gas': 'Need', 'Water/Sewer': 'Need',
    'Internet/Cable': 'Need', 'Utilities': 'Need',
    'Groceries': 'Need', 'Healthcare': 'Need', 'Insurance': 'Need',
    'Gas/Fuel': 'Need', 'Auto Maintenance': 'Need', 'Auto Insurance': 'Need',
    'Transportation': 'Need', 'Phone Bill': 'Need',
    'Childcare': 'Need', 'Education': 'Need', 'Debt Payment': 'Need',
    # Wants
    'Dining': 'Want', 'Restaurants': 'Want', 'Fast Food': 'Want',
    'Entertainment': 'Want', 'Shopping': 'Want', 'Clothing': 'Want',
    'Alcohol/Bar': 'Want', 'Personal Care': 'Want', 'Hobbies': 'Want',
    'Gifts & Donations': 'Want', 'Subscriptions': 'Want',
    'Travel': 'Want', 'Vacation': 'Want', 'Pet Care': 'Want',
    'Home Improvement': 'Want', 'Electronics': 'Want',
    # Savings
    'Investment': 'Saving', 'Investment Transfer': 'Saving',
    'Investment Return': 'Saving', 'Savings': 'Saving',
    'Retirement': 'Saving',
}


class BudgetAdvisor:
    """AI-powered budget goal advisor."""
    
    def __init__(self, model_loader=None, use_ai: bool = True):
        """
        Initialize budget advisor.
        
        Args:
            model_loader: FinGPTModelLoader instance for AI-generated advice
            use_ai: Whether to use AI or rule-based budget suggestions
        """
        self.model_loader = model_loader
        self.use_ai = use_ai and model_loader is not None and getattr(model_loader, 'available', False)
        self.model_name = getattr(model_loader, 'financial_model', None) if model_loader else None

    # ── Bucket classification ─────────────────────────────────────────────────

    def classify_bucket(self, category: str, cached_bucket: Optional[str] = None) -> str:
        """Return 'Need' | 'Want' | 'Saving' for a category.

        Uses heuristic map first; falls back to LLM for unknowns.
        The result is NOT cached here — callers should persist it to budget_goals.bucket.
        """
        if cached_bucket:
            return cached_bucket
        heuristic = _HEURISTIC_BUCKETS.get(category)
        if heuristic:
            return heuristic
        # LLM fallback for truly unknown categories
        if self.use_ai and self.model_loader:
            try:
                prompt = (
                    f"Is '{category}' a household necessity (Need), "
                    "a discretionary expense (Want), or a savings vehicle (Saving)? "
                    "Reply with exactly one word: Need, Want, or Saving."
                )
                resp = (self.model_loader.generate_insight(prompt, temperature=0.0, max_tokens=5) or '').strip()
                for word in ('Need', 'Want', 'Saving'):
                    if word.lower() in resp.lower():
                        return word
            except Exception:
                pass
        return 'Want'  # default unknown → discretionary

    # ── Trend slope ──────────────────────────────────────────────────────────

    @staticmethod
    def _trend_slope(monthly_amounts: List[float]) -> Tuple[float, str]:
        """Return (slope_pct_per_month, direction) for a list of monthly amounts."""
        if len(monthly_amounts) < 2:
            return (0.0, 'stable')
        x = np.arange(len(monthly_amounts), dtype=float)
        y = np.array(monthly_amounts, dtype=float)
        # Ignore months with zero spend — they skew the slope
        mask = y > 0
        if mask.sum() < 2:
            return (0.0, 'stable')
        coeffs = np.polyfit(x[mask], y[mask], 1)
        slope = float(coeffs[0])
        mean_y = float(y[mask].mean())
        slope_pct = (slope / mean_y * 100) if mean_y > 0 else 0.0
        if slope_pct > 5:
            direction = 'increasing'
        elif slope_pct < -5:
            direction = 'decreasing'
        else:
            direction = 'stable'
        return (round(slope_pct, 2), direction)

    # ── Fixed-cost detection ─────────────────────────────────────────────────

    @staticmethod
    def _fixedness_tier(
        monthly_amounts: List[float],
        bounds: Tuple[float, float] = (0.05, 0.20),
    ) -> str:
        """Return 'fixed', 'semi-fixed', or 'variable' based on CV of non-zero amounts.

        fixed      CV < 5%  — rent, annual subscriptions. Never reduce.
        semi-fixed CV 5-20% — electric (seasonal), phone. Forecast, don't cut.
        variable   CV > 20% — gas, groceries, entertainment. Subject to targets.
        """
        if len(monthly_amounts) < 2:
            return 'variable'
        nonzero = [v for v in monthly_amounts if v > 0]
        if len(nonzero) < 2:
            return 'variable'
        mean = float(np.mean(nonzero))
        if mean == 0:
            return 'variable'
        cv = float(np.std(nonzero)) / mean
        lo, hi = bounds
        if cv < lo:
            return 'fixed'
        elif cv < hi:
            return 'semi-fixed'
        else:
            return 'variable'

    @staticmethod
    def _is_fixed_cost(monthly_amounts: List[float], cv_threshold: float = 0.05) -> bool:
        """True if CV < 5% — truly fixed recurring costs like rent (backward compat)."""
        return BudgetAdvisor._fixedness_tier(monthly_amounts) == 'fixed'

    @staticmethod
    def _is_committed_spend(
        monthly_amounts: List[float],
        months: int,
        presence_threshold: float = 0.80,
        cv_threshold: float = 0.15,
    ) -> bool:
        """True if spend is present in >= 80% of months AND CV of non-zero values < 15%.

        Catches committed recurring wants (e.g., $250/mo charitable giving) that don't
        qualify as 'fixed' (CV too high) but are clearly a regular committed obligation.
        These should be forecast at their historical average — not reduced toward a
        discretionary income-% target.
        """
        if months < 1:
            return False
        nonzero = [v for v in monthly_amounts if v > 0]
        presence = len(nonzero) / months
        if presence < presence_threshold:
            return False
        if len(nonzero) < 2:
            # Present every month with only one data point — treat as committed
            return True
        mean = float(np.mean(nonzero))
        if mean == 0:
            return False
        cv = float(np.std(nonzero)) / mean
        return cv < cv_threshold

    # ── Smart Needs-pool allocation ──────────────────────────────────────────

    def _allocate_needs_pool(
        self,
        need_categories: Dict[str, Dict],
        needs_ceiling: float,
    ) -> Dict[str, float]:
        """Distribute the 50% Needs ceiling across Need-bucket categories.

        Fixed-cost categories are locked at their average first; the remainder
        is split proportionally among variable Need categories.
        """
        fixed: Dict[str, float] = {}
        variable: Dict[str, float] = {}
        for cat, info in need_categories.items():
            if info.get('is_fixed_cost'):
                fixed[cat] = info['historical_avg']
            else:
                variable[cat] = info['historical_avg']

        fixed_total = sum(fixed.values())
        remaining_pool = max(0.0, needs_ceiling - fixed_total)
        variable_total = sum(variable.values())

        result: Dict[str, float] = dict(fixed)
        if variable_total > 0 and remaining_pool > 0:
            for cat, avg in variable.items():
                proportion = avg / variable_total
                result[cat] = round(proportion * remaining_pool / 5) * 5  # round to $5
        elif variable:
            # Not enough pool — just use averages (can't do better)
            for cat, avg in variable.items():
                result[cat] = avg

        return result

    # ── Main entry point ─────────────────────────────────────────────────────

    def suggest_monthly_budgets(
        self,
        historical_df: pd.DataFrame,
        months: int = 3,
        avg_monthly_income: float = 0.0,
        strategy: str = '50/30/20',
        savings_target: Optional[float] = None,
        bucket_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Analyze spending history and suggest budget goals for each category.

        Returns the new extended shape:
          suggested_budgets[cat] = {
            suggested_amount, ai_cap, bucket, historical_avg,
            trend_slope, trend_direction, is_fixed_cost,
            reasoning, priority, change_from_average
          }
          Plus top-level: need_pct, want_pct, savings_pct,
          spendable_income, personalized_split_suggestion,
          fixed_cost_coaching_note.
        """
        bucket_overrides = bucket_overrides or {}

        # ── Per-category statistics ──────────────────────────────────────────
        cat_col = next(
            (c for c in historical_df.columns if c.lower() == 'category'),
            'category'
        )
        amt_col = next(
            (c for c in historical_df.columns if c.lower() == 'amount'),
            'Amount'
        )

        # Ensure month column
        if 'month' not in historical_df.columns:
            if 'Transaction Date' in historical_df.columns:
                historical_df = historical_df.copy()
                historical_df['month'] = pd.to_datetime(
                    historical_df['Transaction Date'], format='mixed', errors='coerce'
                ).dt.strftime('%Y-%m')
            else:
                historical_df = historical_df.copy()
                historical_df['month'] = ''

        category_stats: Dict[str, Dict] = {}
        for category in historical_df[cat_col].dropna().unique():
            cat_data = historical_df[historical_df[cat_col] == category]
            monthly = cat_data.groupby('month')[amt_col].sum()
            monthly_amounts = sorted(monthly.items(), key=lambda x: x[0])
            amounts_list = [float(v) for _, v in monthly_amounts]
            # Use full analysis-window average (sum / months), not months-present average
            # (monthly.mean()). This correctly amortizes sporadic spending — e.g. a single
            # $5,000 investment in one of three months should budget ~$1,667/month, not $5,000.
            avg = float(monthly.sum() / months) if (not monthly.empty and months > 0) else 0.0
            std = float(monthly.std()) if len(monthly) > 1 else 0.0
            slope_pct, direction = self._trend_slope(amounts_list)
            tier = self._fixedness_tier(amounts_list)
            is_fixed = (tier == 'fixed')
            is_committed = self._is_committed_spend(amounts_list, months)
            category_stats[category] = {
                'mean':           float(cat_data[amt_col].mean()),
                'monthly_avg':    avg,
                'std':            std,
                'min':            float(cat_data[amt_col].min()),
                'max':            float(cat_data[amt_col].max()),
                'count':          int(len(cat_data)),
                'total':          float(cat_data[amt_col].sum()),
                'months_present': int(len(monthly)),
                'trend_slope':    slope_pct,
                'trend_direction': direction,
                'is_fixed_cost':  is_fixed,
                'fixedness_tier': tier,
                'is_committed':   is_committed,
            }

        # ── Income-based pool calculations ───────────────────────────────────
        spendable_income = avg_monthly_income
        if savings_target is not None and avg_monthly_income > 0:
            spendable_income = max(0.0, avg_monthly_income - savings_target)
        elif avg_monthly_income > 0:
            spendable_income = avg_monthly_income * 0.80  # default: 20% savings

        _strategy_splits = {
            '50/30/20': (0.50, 0.30, 0.20),
            '60/20/20': (0.60, 0.20, 0.20),
            '70/20/10': (0.70, 0.20, 0.10),
        }
        _need_frac, _want_frac, _save_frac = _strategy_splits.get(strategy, (0.50, 0.30, 0.20))
        if avg_monthly_income > 0 and savings_target is None:
            savings_target = avg_monthly_income * _save_frac
            spendable_income = avg_monthly_income - savings_target
            savings_target_amt = savings_target
        needs_ceiling  = spendable_income * _need_frac
        wants_ceiling  = spendable_income * _want_frac
        savings_target_amt = avg_monthly_income - spendable_income if avg_monthly_income > 0 else 0.0

        # ── Classify categories into buckets ─────────────────────────────────
        buckets: Dict[str, str] = {}
        for cat in category_stats:
            override = bucket_overrides.get(cat)
            buckets[cat] = self.classify_bucket(cat, override)

        need_cats  = {c: category_stats[c] for c in category_stats if buckets.get(c) == 'Need'}
        want_cats  = {c: category_stats[c] for c in category_stats if buckets.get(c) == 'Want'}
        saving_cats = {c: category_stats[c] for c in category_stats if buckets.get(c) == 'Saving'}

        # ── Goal mode: predictive (forecast) vs aspirational (target) ─────────
        # predictive  → goal = forecast of expected spend; no income-% reduction
        # aspirational → goal = target to work toward; income % caps apply
        goal_modes: Dict[str, str] = {}
        for cat, stats in category_stats.items():
            tier = stats.get('fixedness_tier', 'variable')
            if tier in ('fixed', 'semi-fixed') or stats.get('is_committed', False):
                goal_modes[cat] = 'predictive'
            else:
                goal_modes[cat] = 'aspirational'

        # ── Smart Needs allocation ────────────────────────────────────────────
        needs_alloc: Dict[str, float] = {}
        if avg_monthly_income > 0 and need_cats:
            need_cat_infos = {}
            for cat, stats in need_cats.items():
                need_cat_infos[cat] = {
                    'historical_avg': stats['monthly_avg'],
                    'is_fixed_cost': stats['is_fixed_cost'],
                }
            needs_alloc = self._allocate_needs_pool(need_cat_infos, needs_ceiling)

        # ── Trend-aware goal adjustment ───────────────────────────────────────
        def _trend_adjusted_goal(stats: Dict, income_cap: Optional[float]) -> float:
            avg = stats['monthly_avg']
            slope_pct = stats['trend_slope']
            direction = stats['trend_direction']
            total_amounts = [
                v for _, v in
                sorted(
                    (historical_df[historical_df[cat_col] == stats.get('_cat', '')]
                     .groupby('month')[amt_col]
                     .sum()
                     .items()
                     if '_cat' in stats else {}),
                    key=lambda x: x[0]
                )
            ]
            latest = total_amounts[-1] if total_amounts else avg
            if direction == 'increasing' and slope_pct > 5:
                suggested = latest * 1.05   # acknowledge trend, mild ceiling
            elif direction == 'decreasing' and slope_pct < -5:
                suggested = avg * 0.95      # reward improvement
            else:
                suggested = avg
            if income_cap is not None:
                suggested = min(suggested, income_cap)
            return round(float(suggested), 2)

        # ── Build final suggestions ───────────────────────────────────────────
        if self.use_ai and self.model_loader:
            ai_budgets = self._generate_ai_budgets(
                category_stats, months, avg_monthly_income, goal_modes=goal_modes
            )
        else:
            ai_budgets = {}

        budgets: Dict[str, Dict] = {}
        for category, stats in category_stats.items():
            bucket = buckets.get(category, 'Want')
            avg = stats['monthly_avg']
            is_fixed = stats['is_fixed_cost']
            direction = stats['trend_direction']
            slope_pct = stats['trend_slope']
            goal_mode = goal_modes.get(category, 'aspirational')
            tier = stats.get('fixedness_tier', 'variable')
            is_committed = stats.get('is_committed', False)

            # AI cap = spendable-anchored ceiling.
            # Predictive categories (fixed/semi-fixed/committed) get no cap — they are
            # forecasts, not targets. Only aspirational categories get income-% guidance.
            if goal_mode == 'predictive':
                ai_cap = None  # don't clamp — it's a forecast
            elif spendable_income > 0:
                if bucket == 'Need':
                    ai_cap = needs_alloc.get(category)
                    if ai_cap is None:
                        target_pct = self.INCOME_TARGETS.get(category, 0.05)
                        ai_cap = spendable_income * target_pct
                elif bucket == 'Want':
                    target_pct = self.INCOME_TARGETS.get(category, 0.03)
                    ai_cap = spendable_income * target_pct  # per-category target, no blanket half-ceiling
                else:
                    ai_cap = None  # savings — user controls
            else:
                ai_cap = None

            # Suggest: AI output if available, else income-cap or trend-adjusted avg
            if ai_budgets and category in ai_budgets:
                suggested = float(ai_budgets[category]['suggested_amount'])
                reasoning = ai_budgets[category].get('reasoning', '')
                priority  = ai_budgets[category].get('priority', 'Important')
            else:
                # Trend-aware fallback
                if direction == 'increasing' and slope_pct > 5:
                    suggested = avg * 1.05
                    if goal_mode == 'predictive':
                        reasoning = f'Forecast: trending up {slope_pct:+.1f}%/mo'
                    else:
                        reasoning = f'Trending up {slope_pct:+.1f}%/mo — slight ceiling applied'
                elif direction == 'decreasing' and slope_pct < -5:
                    suggested = avg * 0.95
                    if goal_mode == 'predictive':
                        reasoning = f'Forecast: trending down {slope_pct:.1f}%/mo'
                    else:
                        reasoning = f'Trending down {slope_pct:.1f}%/mo — reward continued reduction'
                else:
                    suggested = avg

                # Only apply income cap for aspirational categories
                if goal_mode == 'aspirational' and ai_cap is not None and suggested > ai_cap:
                    suggested = ai_cap
                    reasoning = f'Capped at income-based {bucket} target'
                elif not reasoning:
                    if goal_mode == 'predictive':
                        if is_committed and not is_fixed:
                            reasoning = 'Committed recurring expense — forecast at historical average'
                        elif tier == 'semi-fixed':
                            reasoning = 'Semi-fixed cost (seasonal variation) — forecast, not a reduction target'
                        else:
                            reasoning = 'Fixed cost — forecast at historical average'
                    else:
                        reasoning = 'Based on 3-month average'

                priority = (
                    'Essential' if category in self.ESSENTIAL_CATEGORIES
                    else 'Discretionary' if category in self.DISCRETIONARY_CATEGORIES
                    else 'Important'
                )

            change_pct = ((suggested - avg) / avg * 100) if avg > 0 else 0.0

            budgets[category] = {
                'suggested_amount':    round(float(suggested), 2),
                'ai_cap':              round(float(ai_cap), 2) if ai_cap is not None else None,
                'historical_avg':      round(float(avg), 2),
                'bucket':              bucket,
                'bucket_override':     bool(bucket_overrides.get(category)),
                'trend_slope':         stats['trend_slope'],
                'trend_direction':     stats['trend_direction'],
                'is_fixed_cost':       is_fixed,
                'fixedness_tier':      tier,
                'is_committed':        is_committed,
                'goal_mode':           goal_mode,
                'reasoning':           reasoning,
                'priority':            priority,
                'change_from_average': round(float(change_pct), 1),
            }

        # ── Bucket health percentages ─────────────────────────────────────────
        total_avg = sum(s['monthly_avg'] for s in category_stats.values())
        need_total  = sum(category_stats[c]['monthly_avg'] for c in need_cats)
        want_total  = sum(category_stats[c]['monthly_avg'] for c in want_cats)
        saving_total = sum(category_stats[c]['monthly_avg'] for c in saving_cats)
        base = avg_monthly_income if avg_monthly_income > 0 else (total_avg or 1)
        need_pct   = round(need_total / base * 100, 1)
        want_pct   = round(want_total / base * 100, 1)
        savings_pct = round(saving_total / base * 100, 1)

        # ── Personalized split suggestion ─────────────────────────────────────
        split_suggestion: Optional[str] = None
        fixed_need_total = sum(
            s['monthly_avg'] for c, s in need_cats.items() if s['is_fixed_cost']
        )
        fixed_need_pct = fixed_need_total / base * 100 if base > 0 else 0
        if avg_monthly_income > 0:
            if fixed_need_pct > 50:
                split_suggestion = (
                    f"Your fixed housing/utilities costs are already {fixed_need_pct:.0f}% of income. "
                    f"A 60/20/20 split is more realistic for your income level."
                )
            elif want_pct < 15 and savings_pct >= 20:
                split_suggestion = (
                    f"You're already saving {savings_pct:.0f}% of income with low discretionary spending. "
                    f"You could relax the Wants budget slightly — perhaps a 50/30/20 split."
                )

        # ── Fixed-cost coaching note ──────────────────────────────────────────
        coaching_note: Optional[str] = None
        if avg_monthly_income > 0 and fixed_need_pct > 50:
            coaching_note = (
                f"Your fixed housing and utility costs account for {fixed_need_pct:.0f}% of income, "
                f"leaving only {100 - fixed_need_pct:.0f}% of income for groceries, gas, healthcare, "
                f"and all discretionary spending combined. "
                f"Consider temporarily reducing your savings target to relieve pressure."
            )

        return {
            'suggested_budgets':          budgets,
            'category_stats':             category_stats,
            'analysis_period':            months,
            'total_budget':               sum(b['suggested_amount'] for b in budgets.values()),
            'ai_generated':               self.use_ai,
            'model_name':                 self.model_name if self.use_ai else None,
            'avg_monthly_income':         avg_monthly_income,
            'spendable_income':           round(spendable_income, 2),
            'savings_target':             round(savings_target_amt, 2),
            'needs_ceiling':              round(needs_ceiling, 2),
            'wants_ceiling':              round(wants_ceiling, 2),
            'need_pct':                   need_pct,
            'want_pct':                   want_pct,
            'savings_pct':                savings_pct,
            'personalized_split':         split_suggestion,
            'fixed_cost_coaching':        coaching_note,
            'strategy':                   strategy,
        }
    
    def _generate_ai_budgets(
        self,
        category_stats: Dict,
        months: int,
        avg_monthly_income: float = 0.0,
        goal_modes: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """Use LLM to generate intelligent budget recommendations."""
        goal_modes = goal_modes or {}
        try:
            prompt = f"""As a financial advisor, analyze this {months}-month spending data and suggest realistic monthly budget goals.

SPENDING ANALYSIS:
"""
            total_avg = sum(stats.get('monthly_avg', stats['mean']) for stats in category_stats.values())

            for category, stats in sorted(category_stats.items(), key=lambda x: x[1].get('monthly_avg', x[1]['mean']), reverse=True):
                monthly_avg = stats.get('monthly_avg', stats['mean'])
                pct_of_total = (monthly_avg / total_avg * 100) if total_avg > 0 else 0
                pct_of_income = (monthly_avg / avg_monthly_income * 100) if avg_monthly_income > 0 else None
                mode = goal_modes.get(category, 'aspirational')
                tier = stats.get('fixedness_tier', 'variable')
                is_committed = stats.get('is_committed', False)

                prompt += f"\n{category} [mode={mode}, tier={tier}]:\n"
                prompt += f"  - Monthly Average: ${monthly_avg:,.2f} ({pct_of_total:.1f}% of total spending)"
                if pct_of_income is not None:
                    prompt += f" | {pct_of_income:.1f}% of income"
                prompt += "\n"
                prompt += f"  - Range: ${stats['min']:,.2f} - ${stats['max']:,.2f}\n"
                prompt += f"  - Trend: {stats.get('trend_direction', 'stable')} ({stats.get('trend_slope', 0):+.1f}%/mo)\n"
                if is_committed:
                    prompt += f"  - NOTE: Committed recurring expense (appears consistently at similar amounts)\n"

            prompt += f"\nTOTAL AVERAGE MONTHLY SPENDING: ${total_avg:,.2f}\n"
            if avg_monthly_income > 0:
                prompt += f"AVG GROSS MONTHLY INCOME: ${avg_monthly_income:,.2f}\n"
                prompt += f"CURRENT EXPENSE-TO-INCOME RATIO: {total_avg / avg_monthly_income * 100:.1f}%\n"

            prompt += """

GOAL MODES — READ CAREFULLY BEFORE SETTING ANY AMOUNTS:

PREDICTIVE categories [mode=predictive]: These are FIXED or COMMITTED recurring expenses.
  Your job is FORECASTING, not reducing. Set suggested_amount = the historical average.
  DO NOT apply income % targets. DO NOT suggest cuts. These include utilities, rent,
  insurance, AND any discretionary category that appears consistently every month at
  a similar amount (e.g., regular charitable giving, recurring subscriptions).
  Reasoning should say something like: "Forecast based on consistent historical spend."

ASPIRATIONAL categories [mode=aspirational]: These are discretionary/variable expenses
  where budget guidance is helpful. Apply income % targets as gentle guidance — but be
  realistic. If actual spending is close to the guideline, keep it there. Never suggest
  near-$0 for a category the person genuinely uses.

INCOME % GUIDELINES (for ASPIRATIONAL categories only):
- Housing / Rent / Mortgage: ≤ 30% of gross income
- Housing + Utilities combined: ≤ 35% of gross income
- Groceries + Dining combined: ≤ 15% of gross income
- Transportation (all): ≤ 15% of gross income
- Savings / Investments: ≥ 20% of gross income
- Entertainment + Shopping combined: ≤ 10% of gross income
- INCREASING trend categories: suggest 5% above latest month (acknowledge trend)
- DECREASING trend categories: suggest 5% below average (reward improvement)

Format your response as JSON:
{
  "CategoryName": {
    "suggested_amount": 450.00,
    "reasoning": "Forecast based on consistent $450/mo historical spend.",
    "priority": "Essential",
    "change_from_average": 0.0
  }
}

Provide ONLY valid JSON, no other text."""
            
            # Get AI response
            ai_response = self.model_loader.generate_insight(prompt, temperature=0.3, max_tokens=1500)
            
            if ai_response:
                # Try to parse JSON from response
                try:
                    json_start = ai_response.find('{')
                    json_end = ai_response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = ai_response[json_start:json_end]
                        budgets = json.loads(json_str)
                        cleaned_budgets = {}
                        for category, data in budgets.items():
                            if isinstance(data, dict) and 'suggested_amount' in data:
                                cleaned_budgets[category] = {
                                    'suggested_amount': float(data['suggested_amount']),
                                    'reasoning': data.get('reasoning', ''),
                                    'priority': data.get('priority', 'Important'),
                                    'change_from_average': float(data.get('change_from_average', 0))
                                }
                        if cleaned_budgets:
                            logger.info(f"Generated AI budgets for {len(cleaned_budgets)} categories")
                            return cleaned_budgets
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse AI budget JSON: {e}")
            
            logger.warning("AI budget generation failed, using rule-based fallback")
            return {}
            
        except Exception as e:
            logger.error(f"Error generating AI budgets: {e}")
            return {}
    
    # Income-based target percentages (gross monthly income).
    # Used only for ASPIRATIONAL categories — predictive categories bypass these targets.
    INCOME_TARGETS = {
        # Housing
        'Rent/Mortgage': 0.28,
        'Housing':       0.28,
        # Utilities — share of the 35% housing+utilities envelope
        'Utilities':     0.07,
        'Electric':      0.03,
        'Natural Gas':   0.02,
        'Water/Sewer':   0.02,
        'Internet/Cable': 0.02,
        'Phone Bill':    0.02,
        # Food
        'Groceries':     0.10,
        'Dining':        0.05,
        'Restaurants':   0.05,
        'Fast Food':     0.03,
        # Transport
        'Transportation': 0.10,
        'Gas/Fuel':       0.05,
        'Auto Maintenance': 0.03,
        'Auto Insurance': 0.04,
        # Health
        'Healthcare':    0.05,
        'Insurance':     0.05,
        # Savings / Investments
        'Savings':       0.20,
        'Investments':   0.20,
        # Committed wants — used only when category stays aspirational (not committed)
        'Gifts & Donations': 0.05,
        'Subscriptions': 0.02,
        'Pet Care':      0.03,
        # Discretionary
        'Entertainment': 0.05,
        'Alcohol/Bar':   0.02,
        'Shopping':      0.05,
        'Clothing':      0.03,
        'Hobbies':       0.03,
        'Travel':        0.05,
        'Personal Care': 0.03,
    }

    ESSENTIAL_CATEGORIES = {
        'Groceries', 'Utilities', 'Rent/Mortgage', 'Housing', 'Insurance',
        'Healthcare', 'Transportation', 'Gas/Fuel', 'Auto Maintenance',
        'Electric', 'Natural Gas', 'Water/Sewer', 'Internet/Cable', 'Auto Insurance',
    }
    DISCRETIONARY_CATEGORIES = {
        'Dining', 'Entertainment', 'Alcohol/Bar', 'Shopping',
        'Clothing', 'Hobbies', 'Travel', 'Personal Care',
    }

    def _generate_rule_based_budgets(self, category_stats: Dict, avg_monthly_income: float = 0.0) -> Dict:
        """Generate budgets using income-based targets when income is known, else statistical rules."""
        budgets = {}

        for category, stats in category_stats.items():
            monthly_avg = stats.get('monthly_avg', stats['mean'])

            # Try income-based target first
            target_pct = self.INCOME_TARGETS.get(category)
            if avg_monthly_income > 0 and target_pct is not None:
                suggested = avg_monthly_income * target_pct
                reasoning = f"Income-based target: {target_pct*100:.0f}% of gross monthly income"
                priority = 'Essential' if category in self.ESSENTIAL_CATEGORIES else \
                           'Discretionary' if category in self.DISCRETIONARY_CATEGORIES else 'Important'
            elif category in self.ESSENTIAL_CATEGORIES:
                suggested = stats['median'] * 1.10 if 'median' in stats else monthly_avg * 1.1
                priority = 'Essential'
                reasoning = 'Essential expense — based on median with 10% buffer'
            elif category in self.DISCRETIONARY_CATEGORIES:
                suggested = monthly_avg * 0.90
                priority = 'Discretionary'
                reasoning = 'Discretionary — target 10% reduction from average'
            else:
                suggested = stats.get('median', monthly_avg)
                priority = 'Important'
                reasoning = 'Based on median spending'

            change_pct = ((suggested - monthly_avg) / monthly_avg * 100) if monthly_avg > 0 else 0

            budgets[category] = {
                'suggested_amount': round(float(suggested), 2),
                'reasoning': reasoning,
                'priority': priority,
                'change_from_average': round(float(change_pct), 1)
            }

        return budgets

    def compare_to_budget(self, current_month_df: pd.DataFrame, budgets: Dict) -> Dict:
        """
        Compare actual spending to budget goals.
        
        Args:
            current_month_df: DataFrame with current month expenses
            budgets: Dictionary of budget goals per category
            
        Returns:
            Comparison analysis
        """
        actual_by_category = current_month_df.groupby('category')['Amount'].sum()
        
        comparison = {}
        total_actual = 0
        total_budget = 0
        
        for category, budget_info in budgets.items():
            budget_amount = budget_info['suggested_amount']
            actual_amount = float(actual_by_category.get(category, 0))
            
            variance = actual_amount - budget_amount
            variance_pct = (variance / budget_amount * 100) if budget_amount > 0 else 0
            
            total_actual += actual_amount
            total_budget += budget_amount
            
            comparison[category] = {
                'budget': budget_amount,
                'actual': actual_amount,
                'variance': variance,
                'variance_percent': variance_pct,
                'status': 'over' if variance > 0 else 'under' if variance < 0 else 'on_track',
                'priority': budget_info.get('priority', 'Important')
            }
        
        # Add categories with spending but no budget
        for category in actual_by_category.index:
            if category not in comparison:
                actual_amount = float(actual_by_category[category])
                total_actual += actual_amount
                
                comparison[category] = {
                    'budget': 0,
                    'actual': actual_amount,
                    'variance': actual_amount,
                    'variance_percent': 100,
                    'status': 'no_budget',
                    'priority': 'Unknown'
                }
        
        return {
            'categories': comparison,
            'total_budget': total_budget,
            'total_actual': total_actual,
            'total_variance': total_actual - total_budget,
            'total_variance_percent': ((total_actual - total_budget) / total_budget * 100) if total_budget > 0 else 0,
            'on_track': total_actual <= total_budget
        }

