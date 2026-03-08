#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outlier Detection and Filtering
Identifies and optionally filters out one-time large purchases from forecasting.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


class OutlierDetector:
    """Detect and handle outlier transactions for better forecasting."""
    
    def __init__(self, method: str = 'iqr', threshold: float = 1.5):
        """
        Initialize outlier detector.
        
        Args:
            method: Detection method ('iqr', 'zscore', 'isolation_forest')
            threshold: Threshold multiplier (IQR: 1.5 = moderate, 3.0 = extreme)
        """
        self.method = method
        self.threshold = threshold
        
    def detect_outliers_iqr(self, values: pd.Series) -> pd.Index:
        """
        Detect outliers using Interquartile Range (IQR) method.
        More robust than standard deviation for skewed data.
        
        Args:
            values: Series of transaction amounts
            
        Returns:
            Index of outlier values
        """
        if len(values) < 4:
            return pd.Index([])
        
        Q1 = values.quantile(0.25)
        Q3 = values.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - self.threshold * IQR
        upper_bound = Q3 + self.threshold * IQR
        
        # Only flag high outliers (unusually large purchases)
        outliers = values[values > upper_bound]
        return outliers.index
    
    def detect_outliers_zscore(self, values: pd.Series, z_threshold: float = 3.0) -> pd.Index:
        """
        Detect outliers using Z-score method.
        
        Args:
            values: Series of transaction amounts
            z_threshold: Number of standard deviations (default: 3)
            
        Returns:
            Index of outlier values
        """
        if len(values) < 3:
            return pd.Index([])
        
        mean = values.mean()
        std = values.std()
        
        if std == 0:
            return pd.Index([])
        
        z_scores = np.abs((values - mean) / std)
        outliers = values[z_scores > z_threshold]
        return outliers.index
    
    def detect_by_category(self, df: pd.DataFrame, category_col: str = 'category',
                          amount_col: str = 'Amount') -> Dict[str, List[int]]:
        """
        Detect outliers per category.
        
        Args:
            df: DataFrame with transactions
            category_col: Name of category column
            amount_col: Name of amount column
            
        Returns:
            Dictionary mapping category -> list of outlier indices
        """
        outliers_by_category = {}
        
        for category in df[category_col].unique():
            cat_data = df[df[category_col] == category]
            values = cat_data[amount_col]
            
            if self.method == 'iqr':
                outlier_indices = self.detect_outliers_iqr(values)
            else:  # zscore
                outlier_indices = self.detect_outliers_zscore(values)
            
            if len(outlier_indices) > 0:
                outliers_by_category[category] = outlier_indices.tolist()
        
        return outliers_by_category
    
    def filter_outliers(self, df: pd.DataFrame, category_col: str = 'category',
                       amount_col: str = 'Amount') -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split DataFrame into regular transactions and outliers.
        
        Args:
            df: DataFrame with transactions
            category_col: Name of category column
            amount_col: Name of amount column
            
        Returns:
            Tuple of (regular_transactions_df, outliers_df)
        """
        outlier_indices = set()
        
        outliers_by_cat = self.detect_by_category(df, category_col, amount_col)
        for indices in outliers_by_cat.values():
            outlier_indices.update(indices)
        
        regular_df = df[~df.index.isin(outlier_indices)]
        outliers_df = df[df.index.isin(outlier_indices)]
        
        return regular_df, outliers_df
    
    def get_outlier_summary(self, df: pd.DataFrame, category_col: str = 'category',
                           amount_col: str = 'Amount', 
                           place_col: str = 'Place') -> List[Dict]:
        """
        Get summary of detected outliers.
        
        Args:
            df: DataFrame with transactions
            category_col: Name of category column
            amount_col: Name of amount column
            place_col: Name of place/merchant column
            
        Returns:
            List of outlier summaries
        """
        _, outliers_df = self.filter_outliers(df, category_col, amount_col)
        
        summaries = []
        for idx, row in outliers_df.iterrows():
            # Calculate how far from normal
            cat_data = df[df[category_col] == row[category_col]][amount_col]
            median = cat_data.median()
            
            summaries.append({
                'index': idx,
                'place': row.get(place_col, 'Unknown'),
                'amount': float(row[amount_col]),
                'category': row[category_col],
                'date': row.get('Transaction Date', ''),
                'vs_median': float(row[amount_col] / median) if median > 0 else 0,
                'deviation': f"{(row[amount_col] / median):.1f}x category median" if median > 0 else 'N/A'
            })
        
        return sorted(summaries, key=lambda x: x['amount'], reverse=True)


def classify_large_purchases(outliers: List[Dict], 
                             car_threshold: float = 5000,
                             house_threshold: float = 50000) -> Dict[str, List[Dict]]:
    """
    Classify outliers into likely purchase types.
    
    Args:
        outliers: List of outlier dictionaries
        car_threshold: Minimum amount to consider as car purchase
        house_threshold: Minimum amount to consider as house-related
        
    Returns:
        Dictionary categorizing outliers
    """
    classified = {
        'likely_vehicle': [],
        'likely_house': [],
        'large_one_time': [],
        'moderate_outlier': []
    }
    
    for outlier in outliers:
        amount = outlier['amount']
        category = outlier['category']
        
        # House-related
        if amount >= house_threshold or (amount >= 10000 and 'Rent' in category):
            classified['likely_house'].append(outlier)
        
        # Vehicle-related
        elif amount >= car_threshold and ('Auto' in category or 'Transportation' in category):
            classified['likely_vehicle'].append(outlier)
        
        # Other large one-time
        elif amount >= 1000:
            classified['large_one_time'].append(outlier)
        
        # Moderate
        else:
            classified['moderate_outlier'].append(outlier)
    
    return classified
