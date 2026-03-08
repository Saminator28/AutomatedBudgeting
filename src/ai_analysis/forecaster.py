#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Budget Forecaster
Predicts future spending using historical data and financial analysis models.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from .outlier_detector import OutlierDetector

logger = logging.getLogger(__name__)


class BudgetForecaster:
    """Forecast future spending based on historical patterns."""
    
    def __init__(self, model_loader=None, use_ai: bool = True, 
                 filter_outliers: bool = False, outlier_threshold: float = 1.5):
        """
        Initialize budget forecaster.
        
        Args:
            model_loader: FinGPTModelLoader instance for AI forecasting
            use_ai: Whether to use AI or statistical forecasting
            filter_outliers: Whether to exclude outliers from forecasting
            outlier_threshold: IQR multiplier for outlier detection (1.5 = moderate, 3.0 = extreme)
        """
        self.model_loader = model_loader
        self.use_ai = use_ai and model_loader is not None and getattr(model_loader, 'available', False)
        self.filter_outliers = filter_outliers
        self.outlier_detector = OutlierDetector(method='iqr', threshold=outlier_threshold) if filter_outliers else None
        
    def forecast_category(self, category: str, historical_data: pd.DataFrame,
                         months_ahead: int = 1) -> Dict:
        """
        Forecast spending for a specific category.
        
        Args:
            category: Category name to forecast
            historical_data: DataFrame with historical expenses
            months_ahead: Number of months to forecast
            
        Returns:
            Forecast with prediction, confidence interval, and insights
        """
        # Filter category data
        cat_data = historical_data[historical_data['category'] == category].copy()
        
        if cat_data.empty:
            return {
                'category': category,
                'forecast': 0,
                'confidence_low': 0,
                'confidence_high': 0,
                'method': 'no_data'
            }
        
        # Optionally filter outliers for more accurate forecasting
        if self.filter_outliers and self.outlier_detector:
            regular_data, outliers = self.outlier_detector.filter_outliers(
                cat_data, 'category', 'Amount'
            )
            
            # Use regular transactions for forecasting
            if not regular_data.empty:
                cat_data = regular_data
                logger.info(f"Filtered {len(outliers)} outliers from {category} for forecasting")
        
        # Parse dates and aggregate by month
        cat_data['_date'] = pd.to_datetime(cat_data['Transaction Date'], format='%m/%d/%Y')
        cat_data['_month'] = cat_data['_date'].dt.to_period('M')
        
        monthly_totals = cat_data.groupby('_month')['Amount'].sum()
        
        if len(monthly_totals) < 2:
            # Not enough data, use average
            avg = monthly_totals.mean() if not monthly_totals.empty else 0
            return {
                'category': category,
                'forecast': float(avg),
                'confidence_low': float(avg * 0.8),
                'confidence_high': float(avg * 1.2),
                'method': 'average',
                'data_points': len(monthly_totals)
            }
        
        # Use statistical forecasting
        return self._statistical_forecast(category, monthly_totals, months_ahead)
    
    def _statistical_forecast(self, category: str, monthly_series: pd.Series,
                             months_ahead: int) -> Dict:
        """Statistical forecasting using moving average and trend analysis."""
        
        values = monthly_series.values
        n = len(values)
        
        # Calculate trend
        x = np.arange(n)
        z = np.polyfit(x, values, 1)
        trend = z[0]  # Slope
        
        # Calculate seasonal pattern (if enough data)
        if n >= 12:
            # Identify month-of-year patterns
            months = [p.month for p in monthly_series.index]
            month_avgs = defaultdict(list)
            for month, value in zip(months, values):
                month_avgs[month].append(value)
            
            # Average for each month
            seasonal_factors = {
                month: np.mean(vals) / np.mean(values) 
                for month, vals in month_avgs.items()
            }
        else:
            seasonal_factors = {}
        
        # Forecast using weighted moving average + trend
        if n >= 3:
            # Weight recent months more heavily
            weights = np.exp(np.linspace(-1, 0, min(6, n)))
            weights = weights / weights.sum()
            recent_avg = np.average(values[-len(weights):], weights=weights)
        else:
            recent_avg = np.mean(values)
        
        # Base forecast
        forecast = recent_avg + trend * months_ahead
        
        # Apply seasonal adjustment if available
        next_month = monthly_series.index[-1] + months_ahead
        if hasattr(next_month, 'month') and next_month.month in seasonal_factors:
            forecast *= seasonal_factors[next_month.month]
        
        # Ensure forecast is non-negative (can't have negative expenses)
        forecast = max(0, forecast)
        
        # Calculate confidence interval based on historical volatility
        std = np.std(values)
        
        # Wider confidence for longer forecasts
        confidence_multiplier = 1 + (months_ahead - 1) * 0.2
        confidence_low = max(0, forecast - std * confidence_multiplier)
        confidence_high = max(forecast, forecast + std * confidence_multiplier)
        
        return {
            'category': category,
            'forecast': float(forecast),
            'confidence_low': float(confidence_low),
            'confidence_high': float(confidence_high),
            'trend': 'increasing' if trend > 0 else 'decreasing' if trend < 0 else 'stable',
            'trend_amount': float(trend),
            'volatility': float(std),
            'method': 'statistical',
            'data_points': n,
            'seasonal': bool(seasonal_factors)
        }
    
    def forecast_total(self, historical_data: pd.DataFrame, months_ahead: int = 1) -> Dict:
        """
        Forecast total spending across all categories.
        
        Args:
            historical_data: DataFrame with historical expenses
            months_ahead: Number of months to forecast
            
        Returns:
            Total forecast with category breakdowns
        """
        categories = historical_data['category'].unique()
        
        forecasts = {}
        total_forecast = 0
        total_low = 0
        total_high = 0
        
        for category in categories:
            cat_forecast = self.forecast_category(category, historical_data, months_ahead)
            forecasts[category] = cat_forecast
            
            total_forecast += cat_forecast['forecast']
            total_low += cat_forecast['confidence_low']
            total_high += cat_forecast['confidence_high']
        
        return {
            'total_forecast': float(total_forecast),
            'confidence_low': float(total_low),
            'confidence_high': float(total_high),
            'months_ahead': months_ahead,
            'categories': forecasts,
            'forecast_date': (datetime.now() + timedelta(days=30 * months_ahead)).strftime('%Y-%m')
        }
    
    def create_budget_recommendations(self, forecast: Dict, 
                                     historical_avg: float,
                                     savings_goal: Optional[float] = None) -> Dict:
        """
        Create budget recommendations based on forecasts.
        
        Args:
            forecast: Forecast dictionary from forecast_total()
            historical_avg: Historical average monthly spending
            savings_goal: Optional savings goal amount
            
        Returns:
            Budget recommendations and goals
        """
        recommendations = {
            'recommended_budget': {},
            'savings_potential': {},
            'adjustments': []
        }
        
        total_forecast = forecast['total_forecast']
        
        # Recommend budgets per category (use upper confidence bound for safety)
        for category, cat_forecast in forecast['categories'].items():
            # Use 75th percentile between forecast and high confidence
            recommended = cat_forecast['forecast'] * 1.1  # 10% buffer
            
            recommendations['recommended_budget'][category] = {
                'amount': float(recommended),
                'forecast': float(cat_forecast['forecast']),
                'confidence_range': [
                    float(cat_forecast['confidence_low']),
                    float(cat_forecast['confidence_high'])
                ]
            }
        
        # Calculate savings potential
        if savings_goal:
            required_spending = total_forecast - savings_goal
            
            if required_spending < total_forecast:
                # Need to cut spending
                cut_needed = total_forecast - required_spending
                cut_pct = (cut_needed / total_forecast * 100)
                
                recommendations['savings_potential'] = {
                    'goal': float(savings_goal),
                    'forecast_spending': float(total_forecast),
                    'required_spending': float(required_spending),
                    'cut_needed': float(cut_needed),
                    'cut_percentage': float(cut_pct)
                }
                
                # Suggest which categories to reduce
                discretionary = ['Dining', 'Entertainment', 'Alcohol/Bar', 'Shopping', 'Subscriptions']
                discretionary_forecast = sum(
                    forecast['categories'].get(cat, {}).get('forecast', 0)
                    for cat in discretionary
                )
                
                if discretionary_forecast > 0:
                    recommendations['adjustments'].append({
                        'type': 'reduce_discretionary',
                        'message': f"Consider reducing discretionary spending (dining, entertainment, shopping) by "
                                 f"${cut_needed:.2f} to meet savings goal of ${savings_goal:.2f}/month",
                        'categories': discretionary,
                        'current_forecast': float(discretionary_forecast),
                        'potential_savings': float(min(cut_needed, discretionary_forecast * 0.3))
                    })
        
        # Identify high-volatility categories that need closer monitoring
        for category, cat_forecast in forecast['categories'].items():
            if 'volatility' in cat_forecast:
                # High volatility if std dev > 30% of mean
                if cat_forecast['volatility'] > cat_forecast['forecast'] * 0.3:
                    recommendations['adjustments'].append({
                        'type': 'monitor_volatility',
                        'category': category,
                        'message': f"{category} shows high spending variability. Set alerts for unusual transactions.",
                        'volatility': float(cat_forecast['volatility'])
                    })
        
        return recommendations
    
    def analyze_trends(self, historical_data: pd.DataFrame, months: int = 6) -> Dict:
        """
        Analyze spending trends over time.
        
        Args:
            historical_data: DataFrame with historical expenses
            months: Number of recent months to analyze
            
        Returns:
            Trend analysis by category
        """
        # Parse dates
        data = historical_data.copy()
        data['_date'] = pd.to_datetime(data['Transaction Date'], format='%m/%d/%Y')
        data['_month'] = data['_date'].dt.to_period('M')
        
        # Filter to recent months
        recent_data = data[data['_month'] >= data['_month'].max() - months]
        
        trends = {}
        
        for category in recent_data['category'].unique():
            cat_data = recent_data[recent_data['category'] == category]
            monthly = cat_data.groupby('_month')['Amount'].sum()
            
            if len(monthly) >= 2:
                # Calculate trend
                x = np.arange(len(monthly))
                z = np.polyfit(x, monthly.values, 1)
                slope = z[0]
                
                # Percentage change: current month vs average of all prior months
                # (avoids wild swings caused by one unusually low/high old month)
                prior_avg = float(monthly.iloc[:-1].mean()) if len(monthly) > 1 else float(monthly.iloc[0])
                current_val = float(monthly.iloc[-1])
                pct_change = ((current_val - prior_avg) / prior_avg * 100) if prior_avg > 0 else 0

                trends[category] = {
                    'trend': 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'stable',
                    'slope': float(slope),
                    'percent_change': float(pct_change),
                    'current_month': current_val,
                    'previous_month': float(monthly.iloc[-2]) if len(monthly) >= 2 else 0,
                    'average': float(monthly.mean())
                }
        
        return trends
