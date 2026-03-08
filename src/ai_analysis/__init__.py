"""
AI Analysis Module
Provides financial insights, forecasting, and sentiment analysis using FinGPT models.
"""

from .insights_generator import InsightsGenerator
from .forecaster import BudgetForecaster
from .outlier_detector import OutlierDetector

__all__ = ['InsightsGenerator', 'BudgetForecaster', 'OutlierDetector']
