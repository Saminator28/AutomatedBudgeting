#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinGPT Model Loader
Loads and manages financial analysis models using Ollama.
"""

import json
from pathlib import Path
from typing import Optional, Tuple
import logging

import requests

OLLAMA_HOST = 'http://localhost:11434'

logger = logging.getLogger(__name__)


class FinGPTModelLoader:
    """Load and manage financial analysis models via Ollama."""
    
    def __init__(self, llm_host: str = "http://localhost:11434"):
        """
        Initialize model loader.
        
        Args:
            llm_host: Ollama server URL
        """
        self.llm_host = llm_host
        
        # Load financial analysis model from config
        llm_config_path = Path(__file__).parent.parent.parent / 'config' / 'llm_models.json'
        if not llm_config_path.exists():
            logger.warning(f"LLM config not found: {llm_config_path}. AI insights disabled.")
            self.financial_model = None
            self.available = False
            return
        
        with open(llm_config_path, 'r') as f:
            llm_config = json.load(f)
        
        self.financial_model = llm_config.get('financial_analysis_model')
        if not self.financial_model or self.financial_model.strip() == '':
            logger.info("No financial_analysis_model specified in config. AI insights disabled, using rule-based fallback.")
            self.available = False
            return
        
        logger.info(f"Using financial analysis model: {self.financial_model}")
        
        self.available = self._check_model_availability()
    
    def _check_model_availability(self) -> bool:
        """Check if the financial analysis model is available in Ollama."""
        try:
            resp = requests.get(f'{OLLAMA_HOST}/api/tags', timeout=3)
            if resp.status_code == 200:
                names = [m['name'] for m in resp.json().get('models', [])]
                available = any(self.financial_model in n or n.startswith(self.financial_model + ':') for n in names)
                if available:
                    logger.info(f"Financial analysis model '{self.financial_model}' is available")
                else:
                    logger.warning(f"Financial analysis model '{self.financial_model}' not found in Ollama")
                return available
        except Exception as e:
            logger.warning(f"Could not check Ollama model availability: {e}")
        return False
        
    def generate_insight(self, prompt: str, temperature: float = 0.3, max_tokens: int = 500) -> Optional[str]:
        """
        Generate financial insights using the configured model.
        
        Args:
            prompt: The prompt to send to the model
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text or None if unavailable
        """
        if not self.available:
            logger.warning("Financial analysis model not available")
            return None

        try:
            resp = requests.post(
                f'{OLLAMA_HOST}/api/chat',
                json={
                    'model': self.financial_model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                    'think': False,
                    'options': {'temperature': temperature, 'num_predict': max_tokens},
                },
                timeout=120,
            )
            resp.raise_for_status()
            content = (resp.json().get('message', {}).get('content') or '').strip()
            logger.debug(f"Extracted content: {content[:100]}")
            return content or None

        except Exception as e:
            logger.error(f"Error generating insight: {e}", exc_info=True)
            return None
    
    def analyze_spending(self, spending_data: dict) -> Optional[str]:
        """
        Analyze spending patterns and generate insights.
        
        Args:
            spending_data: Dictionary with spending statistics
            
        Returns:
            Generated analysis or None
        """
        prompt = f"""As a financial advisor, analyze this spending data and provide insights:

Total: ${spending_data.get('total', 0):,.2f}
Top Categories: {spending_data.get('top_categories', [])}
Month-over-Month Change: {spending_data.get('change_percent', 0):.1f}%

Provide:
1. Key insights about spending patterns
2. Areas of concern or improvement opportunities
3. Specific recommendations

Keep it concise and actionable."""
        
        return self.generate_insight(prompt, temperature=0.3, max_tokens=500)
    
    def forecast_spending(self, historical_data: list) -> Optional[str]:
        """
        Forecast future spending based on historical data.
        
        Args:
            historical_data: List of monthly spending amounts
            
        Returns:
            Forecast and analysis or None
        """
        prompt = f"""As a financial forecaster, analyze this spending history and predict next month:

Historical Monthly Spending: {historical_data}

Provide:
1. Predicted spending for next month with reasoning
2. Trend analysis (increasing/decreasing/stable)
3. Confidence level in prediction

Be specific with numbers."""
        
        return self.generate_insight(prompt, temperature=0.2, max_tokens=400)
