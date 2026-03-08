#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Budget Advisor
Uses LLM to analyze spending patterns and suggest realistic budget goals.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import logging
import json

logger = logging.getLogger(__name__)


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
    
    def suggest_monthly_budgets(self, historical_df: pd.DataFrame, months: int = 3, avg_monthly_income: float = 0.0) -> Dict:
        """
        Analyze spending history and suggest budget goals for each category.

        Args:
            historical_df: DataFrame with historical expense data (multiple months)
            months: Number of recent months to analyze
            avg_monthly_income: Average gross monthly income; used for income-based benchmarks

        Returns:
            Dictionary with suggested budgets and analysis
        """
        # Calculate statistics per category
        category_stats = {}
        
        for category in historical_df['category'].unique():
            cat_data = historical_df[historical_df['category'] == category]['Amount']
            
            if len(cat_data) > 0:
                category_stats[category] = {
                    'mean': float(cat_data.mean()),
                    'median': float(cat_data.median()),
                    'std': float(cat_data.std()) if len(cat_data) > 1 else 0,
                    'min': float(cat_data.min()),
                    'max': float(cat_data.max()),
                    'count': len(cat_data),
                    'total': float(cat_data.sum())
                }
        
        # Group by month and category for monthly averages
        if 'Transaction Date' in historical_df.columns:
            historical_df['month'] = pd.to_datetime(historical_df['Transaction Date'], format='%m/%d/%Y').dt.to_period('M')
            monthly_by_category = historical_df.groupby(['month', 'category'])['Amount'].sum().reset_index()
            
            # Calculate monthly averages per category
            for category in category_stats.keys():
                cat_monthly = monthly_by_category[monthly_by_category['category'] == category]['Amount']
                if len(cat_monthly) > 0:
                    category_stats[category]['monthly_avg'] = float(cat_monthly.mean())
                    category_stats[category]['months_present'] = len(cat_monthly)
        
        # Use AI to suggest budgets or fallback to rule-based
        if self.use_ai and self.model_loader:
            budgets = self._generate_ai_budgets(category_stats, months, avg_monthly_income)
        else:
            budgets = self._generate_rule_based_budgets(category_stats, avg_monthly_income)

        return {
            'suggested_budgets': budgets,
            'category_stats': category_stats,
            'analysis_period': months,
            'total_budget': sum(budget['suggested_amount'] for budget in budgets.values()),
            'ai_generated': self.use_ai,
            'model_name': self.model_name if self.use_ai else None,
            'avg_monthly_income': avg_monthly_income,
        }
    
    def _generate_ai_budgets(self, category_stats: Dict, months: int, avg_monthly_income: float = 0.0) -> Dict:
        """Use LLM to generate intelligent budget recommendations."""
        try:
            # Build comprehensive prompt
            prompt = f"""As a financial advisor, analyze this {months}-month spending data and suggest realistic monthly budget goals.

SPENDING ANALYSIS:
"""
            total_avg = sum(stats.get('monthly_avg', stats['mean']) for stats in category_stats.values())

            for category, stats in sorted(category_stats.items(), key=lambda x: x[1].get('monthly_avg', x[1]['mean']), reverse=True):
                monthly_avg = stats.get('monthly_avg', stats['mean'])
                pct_of_total = (monthly_avg / total_avg * 100) if total_avg > 0 else 0
                pct_of_income = (monthly_avg / avg_monthly_income * 100) if avg_monthly_income > 0 else None

                prompt += f"\n{category}:\n"
                prompt += f"  - Monthly Average: ${monthly_avg:,.2f} ({pct_of_total:.1f}% of total spending)"
                if pct_of_income is not None:
                    prompt += f" | {pct_of_income:.1f}% of income"
                prompt += "\n"
                prompt += f"  - Range: ${stats['min']:,.2f} - ${stats['max']:,.2f}\n"
                prompt += f"  - Standard Deviation: ${stats['std']:,.2f}\n"

            prompt += f"\nTOTAL AVERAGE MONTHLY SPENDING: ${total_avg:,.2f}\n"
            if avg_monthly_income > 0:
                prompt += f"AVG GROSS MONTHLY INCOME: ${avg_monthly_income:,.2f}\n"
                prompt += f"CURRENT EXPENSE-TO-INCOME RATIO: {total_avg / avg_monthly_income * 100:.1f}%\n"

            prompt += """

BUDGET RULES TO APPLY (use these as hard targets, not suggestions):
- Housing / Rent / Mortgage: target ≤ 30% of gross monthly income
- Housing + Utilities combined: target ≤ 35% of gross monthly income
- Groceries + Dining combined: target ≤ 15% of gross monthly income
- Transportation (all transport categories combined): target ≤ 15% of gross monthly income
- Savings / Investments: target ≥ 20% of gross monthly income
- All other necessities: apply 50/30/20 rule judgment
- Discretionary (dining out, entertainment, shopping): flag if over 30% of income total

For EACH category, provide:
1. suggested_amount: dollar figure anchored to income-% targets above, NOT just avg±10%
2. reasoning: one sentence citing the income-% target you applied
3. priority: Essential / Important / Discretionary
4. change_from_average: percentage change from the spending average (negative = reduction)

Format your response as JSON:
{
  "CategoryName": {
    "suggested_amount": 450.00,
    "reasoning": "Housing at 28% of income keeps you within the 30% guideline.",
    "priority": "Essential",
    "change_from_average": -5.5
  }
}

Provide ONLY valid JSON, no other text."""
            
            # Get AI response
            ai_response = self.model_loader.generate_insight(prompt, temperature=0.3, max_tokens=1500)
            
            if ai_response:
                # Try to parse JSON from response
                try:
                    # Extract JSON from response (might have extra text)
                    json_start = ai_response.find('{')
                    json_end = ai_response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = ai_response[json_start:json_end]
                        budgets = json.loads(json_str)
                        
                        # Validate and clean up
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
            
            # Fallback if AI parsing fails
            logger.warning("AI budget generation failed, using rule-based fallback")
            return self._generate_rule_based_budgets(category_stats)
            
        except Exception as e:
            logger.error(f"Error generating AI budgets: {e}")
            return self._generate_rule_based_budgets(category_stats)
    
    # Income-based target percentages (gross monthly income)
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
        # Food
        'Groceries':     0.10,
        'Dining':        0.05,
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
                # Essential without income: median + 10% buffer
                suggested = stats['median'] * 1.10
                priority = 'Essential'
                reasoning = 'Essential expense — based on median with 10% buffer'
            elif category in self.DISCRETIONARY_CATEGORIES:
                # Discretionary without income: 10% reduction
                suggested = monthly_avg * 0.90
                priority = 'Discretionary'
                reasoning = 'Discretionary — target 10% reduction from average'
            else:
                suggested = stats['median']
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
