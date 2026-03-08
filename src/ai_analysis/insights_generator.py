#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Financial Insights Generator
Generates natural language spending insights using financial analysis models via Ollama.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class InsightsGenerator:
    """Generate spending insights from transaction data."""
    
    def __init__(self, model_loader=None, use_ai: bool = True):
        """
        Initialize insights generator.
        
        Args:
            model_loader: FinGPTModelLoader instance for AI-generated insights
            use_ai: Whether to use AI or rule-based insights
        """
        self.model_loader = model_loader
        self.use_ai = use_ai and model_loader is not None and getattr(model_loader, 'available', False)
        self.model_name = getattr(model_loader, 'financial_model', None) if model_loader else None
        
    def generate_monthly_insights(self, month: str, expenses_df: pd.DataFrame, 
                                  prev_expenses_df: Optional[pd.DataFrame] = None) -> Dict:
        """
        Generate insights for a specific month.
        
        Args:
            month: Month in YYYY-MM format
            expenses_df: DataFrame with current month expenses
            prev_expenses_df: DataFrame with previous month for comparison
            
        Returns:
            Dictionary with insights, highlights, and recommendations
        """
        insights = {
            'month': month,
            'summary': '',
            'highlights': [],
            'category_changes': [],
            'anomalies': [],
            'recommendations': [],
            'ai_generated': self.use_ai,
            'model_name': self.model_name if self.use_ai else None
        }
        
        # Calculate basic statistics
        total_spending = expenses_df['Amount'].sum()
        category_totals = expenses_df.groupby('category')['Amount'].sum().sort_values(ascending=False)
        
        # Top spending categories
        top_categories = category_totals.head(3)
        insights['top_categories'] = [
            {'category': cat, 'amount': float(amt)} 
            for cat, amt in top_categories.items()
        ]
        
        # Compare with previous month if available
        if prev_expenses_df is not None and not prev_expenses_df.empty:
            prev_total = prev_expenses_df['Amount'].sum()
            change_pct = ((total_spending - prev_total) / prev_total * 100) if prev_total > 0 else 0
            
            insights['month_over_month'] = {
                'current': float(total_spending),
                'previous': float(prev_total),
                'change_percent': float(change_pct)
            }
            
            # Category-level changes
            prev_category_totals = prev_expenses_df.groupby('category')['Amount'].sum()
            
            for category in category_totals.index:
                current = category_totals[category]
                previous = prev_category_totals.get(category, 0)
                
                if previous > 0:
                    cat_change = ((current - previous) / previous * 100)
                    
                    # Flag significant changes (>25%)
                    if abs(cat_change) > 25:
                        insights['category_changes'].append({
                            'category': category,
                            'change_percent': float(cat_change),
                            'current': float(current),
                            'previous': float(previous)
                        })
        
        # Detect anomalies (transactions > 2 std dev from category mean)
        for category in expenses_df['category'].unique():
            cat_expenses = expenses_df[expenses_df['category'] == category]['Amount']
            if len(cat_expenses) > 3:  # Need enough data
                mean = cat_expenses.mean()
                std = cat_expenses.std()
                
                if std > 0:
                    outliers = cat_expenses[cat_expenses > mean + 2 * std]
                    for idx in outliers.index:
                        transaction = expenses_df.loc[idx]
                        insights['anomalies'].append({
                            'place': transaction['Place'],
                            'amount': float(transaction['Amount']),
                            'category': category,
                            'date': transaction['Transaction Date']
                        })
        
        # Generate text summary and recommendations
        if self.use_ai and self.model_loader:
            # Use AI for enhanced insights
            insights['summary'] = self._generate_ai_summary(insights, month, total_spending)
            insights['recommendations'] = self._generate_ai_recommendations(insights, category_totals)
        else:
            # Fallback to rule-based
            insights['summary'] = self._generate_summary(insights, month, total_spending)
            insights['recommendations'] = self._generate_recommendations(insights, category_totals)
        
        return insights
    
    def _generate_summary(self, insights: Dict, month: str, total: float) -> str:
        """Generate natural language summary of spending."""
        
        month_name = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
        lines = [f"# {month_name} Spending Analysis\n"]
        
        lines.append(f"**Total Spending:** ${total:,.2f}")
        
        # Month-over-month comparison
        if 'month_over_month' in insights:
            mom = insights['month_over_month']
            change = mom['change_percent']
            direction = "increased" if change > 0 else "decreased"
            lines.append(f"**Change from previous month:** {direction} by {abs(change):.1f}%")
        
        # Top categories
        lines.append("\n## Top Spending Categories")
        for item in insights['top_categories']:
            lines.append(f"- **{item['category']}:** ${item['amount']:,.2f}")
        
        # Significant changes
        if insights['category_changes']:
            lines.append("\n## Significant Changes")
            for change in sorted(insights['category_changes'], 
                               key=lambda x: abs(x['change_percent']), reverse=True)[:3]:
                direction = "increased" if change['change_percent'] > 0 else "decreased"
                lines.append(
                    f"- **{change['category']}** {direction} by {abs(change['change_percent']):.1f}% "
                    f"(${change['previous']:,.2f} → ${change['current']:,.2f})"
                )
        
        # Anomalies
        if insights['anomalies']:
            lines.append("\n## Unusual Transactions")
            for anomaly in insights['anomalies'][:5]:
                lines.append(
                    f"- {anomaly['place']}: ${anomaly['amount']:,.2f} "
                    f"({anomaly['category']}) on {anomaly['date']}"
                )
        
        return '\n'.join(lines)
    
    def _generate_recommendations(self, insights: Dict, category_totals: pd.Series) -> List[str]:
        """Generate spending recommendations."""
        recommendations = []
        
        # Check for high discretionary spending
        discretionary = ['Dining', 'Entertainment', 'Alcohol/Bar', 'Shopping']
        discretionary_total = sum(
            category_totals.get(cat, 0) for cat in discretionary
        )
        
        if discretionary_total > category_totals.sum() * 0.3:  # >30% of spending
            recommendations.append(
                f"Discretionary spending (dining, entertainment, shopping) represents "
                f"${discretionary_total:,.2f}. Consider setting a monthly budget for these categories."
            )
        
        # Check for large category increases
        for change in insights.get('category_changes', []):
            if change['change_percent'] > 50:
                recommendations.append(
                    f"{change['category']} spending increased significantly. "
                    f"Review if this aligns with your budget goals."
                )
        
        # Check for anomalies
        if len(insights.get('anomalies', [])) > 3:
            recommendations.append(
                f"Detected {len(insights['anomalies'])} unusual transactions. "
                "Review these for accuracy or consider if they represent one-time expenses."
            )
        
        return recommendations
    
    def _generate_ai_summary(self, insights: Dict, month: str, total: float) -> str:
        """Generate AI-powered natural language summary of spending."""
        try:
            month_name = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
            
            # Build context for AI
            context = {
                'month': month_name,
                'total': total,
                'top_categories': insights.get('top_categories', []),
                'change_percent': insights.get('month_over_month', {}).get('change_percent', 0),
                'category_changes': insights.get('category_changes', []),
                'anomalies': insights.get('anomalies', [])
            }
            
            # Use model loader to generate insight
            ai_summary = self.model_loader.analyze_spending(context)
            
            if ai_summary:
                return f"# {month_name} Spending Analysis\n\n{ai_summary}"
            else:
                # Fallback if AI fails
                logger.warning("AI summary generation failed, using rule-based fallback")
                return self._generate_summary(insights, month, total)
                
        except Exception as e:
            logger.error(f"Error generating AI summary: {e}")
            return self._generate_summary(insights, month, total)
    
    def _generate_ai_recommendations(self, insights: Dict, category_totals: pd.Series) -> List[str]:
        """Generate AI-powered spending recommendations."""
        try:
            # Prepare data for AI analysis
            prompt = f"""Analyze this spending data and provide 3-5 specific, actionable recommendations:

Total Spending: ${category_totals.sum():,.2f}

Category Breakdown:
"""
            for cat, amount in category_totals.head(5).items():
                pct = (amount / category_totals.sum() * 100)
                prompt += f"- {cat}: ${amount:,.2f} ({pct:.1f}%)\n"
            
            if insights.get('category_changes'):
                prompt += "\nSignificant Changes from Last Month:\n"
                for change in insights['category_changes'][:3]:
                    direction = "increased" if change['change_percent'] > 0 else "decreased"
                    prompt += f"- {change['category']} {direction} by {abs(change['change_percent']):.1f}%\n"
            
            if insights.get('anomalies'):
                prompt += f"\nUnusual Transactions: {len(insights['anomalies'])} detected\n"
            
            prompt += "\nProvide specific, actionable recommendations to improve financial health. Format as a numbered list."
            
            ai_recommendations = self.model_loader.generate_insight(prompt, temperature=0.4, max_tokens=600)
            
            if ai_recommendations:
                # Parse AI response into list
                lines = [line.strip() for line in ai_recommendations.split('\n') if line.strip()]
                # Filter to lines that look like recommendations
                recommendations = [line for line in lines if any(line.startswith(prefix) for prefix in ['1.', '2.', '3.', '4.', '5.', '-', '•']) or len(line) > 20]
                return recommendations if recommendations else [ai_recommendations]
            else:
                logger.warning("AI recommendations failed, using rule-based fallback")
                return self._generate_recommendations(insights, category_totals)
                
        except Exception as e:
            logger.error(f"Error generating AI recommendations: {e}")
            return self._generate_recommendations(insights, category_totals)
    
    def compare_months(self, months_data: List[Dict]) -> Dict:
        """
        Compare multiple months of data for trends.
        
        Args:
            months_data: List of monthly expense dictionaries
            
        Returns:
            Trend analysis and insights
        """
        trends = {
            'months': len(months_data),
            'total_trend': [],
            'category_trends': {},
            'insights': []
        }
        
        # Calculate monthly totals
        for month_data in months_data:
            df = month_data['data']
            total = df['Amount'].sum()
            trends['total_trend'].append({
                'month': month_data['month'],
                'total': float(total)
            })
        
        # Identify spending patterns
        if len(trends['total_trend']) >= 3:
            totals = [m['total'] for m in trends['total_trend']]
            avg = np.mean(totals)
            trend_direction = "increasing" if totals[-1] > totals[0] else "decreasing"
            
            trends['insights'].append(
                f"Average monthly spending: ${avg:,.2f}. "
                f"Overall trend is {trend_direction}."
            )
        
        return trends
