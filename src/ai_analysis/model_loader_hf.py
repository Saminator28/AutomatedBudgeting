#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinGPT Model Loader (HuggingFace)
Loads and manages financial analysis models directly from HuggingFace.
Uses LoRA adapters without Ollama.
"""

import json
import torch
from pathlib import Path
from typing import Optional
import logging
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logger = logging.getLogger(__name__)


class FinGPTModelLoaderHF:
    """Load and manage financial analysis models via HuggingFace."""
    
    def __init__(self, use_4bit: bool = True, device: str = "auto"):
        """
        Initialize model loader with HuggingFace transformers.
        
        Args:
            use_4bit: Use 4-bit quantization to save memory (requires bitsandbytes)
            device: Device to use ('cuda', 'cpu', or 'auto')
        """
        self.device = device
        self.use_4bit = use_4bit
        self.model = None
        self.tokenizer = None
        self.available = False
        
        # FinGPT LoRA adapter model
        self.base_model_name = "meta-llama/Meta-Llama-3-8B-Instruct"
        self.lora_model_name = "FinGPT/fingpt-mt_llama3-8b_lora"
        
        logger.info(f"Initializing FinGPT with base: {self.base_model_name}")
        logger.info(f"Loading LoRA adapter: {self.lora_model_name}")
        
        try:
            self._load_model()
            self.available = True
            logger.info("✅ FinGPT model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load FinGPT model: {e}")
            self.available = False
    
    def _load_model(self):
        """Load base model and LoRA adapter."""
        # Load tokenizer
        logger.info("Loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_name,
            trust_remote_code=True
        )
        self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load base model with quantization if requested
        logger.info(f"Loading base model (4-bit={self.use_4bit})...")
        
        if self.use_4bit:
            from transformers import BitsAndBytesConfig
            
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16
            )
            
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                quantization_config=bnb_config,
                device_map=self.device,
                trust_remote_code=True
            )
        else:
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                device_map=self.device,
                torch_dtype=torch.float16,
                trust_remote_code=True
            )
        
        # Load LoRA adapter on top of base model
        logger.info("Loading LoRA adapter...")
        self.model = PeftModel.from_pretrained(
            base_model,
            self.lora_model_name,
            torch_dtype=torch.float16
        )
        
        # Set to evaluation mode
        self.model.eval()
        logger.info(f"Model loaded on device: {self.model.device}")
    
    def generate_insight(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        do_sample: bool = True
    ) -> Optional[str]:
        """
        Generate financial insights using FinGPT.
        
        Args:
            prompt: Input prompt for analysis
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter
            do_sample: Whether to use sampling (vs greedy decoding)
        
        Returns:
            Generated text or None if failed
        """
        if not self.available:
            logger.warning("Model not available")
            return None
        
        try:
            # Format prompt for instruction following
            formatted_prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>

You are a financial analyst. {prompt}

Provide concise, actionable insights.<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""
            
            # Tokenize
            inputs = self.tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=2048
            )
            
            # Move to model device
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
            
            # Generate
            logger.info(f"Generating response (max_tokens={max_new_tokens})...")
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=do_sample,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode response (skip input prompt)
            full_response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract only the assistant's response
            if "assistant<|end_header_id|>" in full_response:
                response = full_response.split("assistant<|end_header_id|>")[1].strip()
            else:
                response = full_response[len(formatted_prompt):].strip()
            
            logger.info(f"Generated {len(response)} characters")
            return response
            
        except Exception as e:
            logger.error(f"Error generating insight: {e}", exc_info=True)
            return None
    
    def analyze_spending(
        self,
        total_spending: float,
        category_breakdown: dict,
        num_transactions: int,
        month: str
    ) -> Optional[str]:
        """
        Analyze spending patterns with FinGPT.
        
        Args:
            total_spending: Total amount spent
            category_breakdown: Dict of {category: amount}
            num_transactions: Number of transactions
            month: Month being analyzed
        
        Returns:
            Analysis text or None if failed
        """
        # Format category breakdown
        categories_text = "\n".join([
            f"- {cat}: ${amt:,.2f}"
            for cat, amt in sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True)[:10]
        ])
        
        prompt = f"""Analyze this spending for {month}:

Total Spending: ${total_spending:,.2f}
Number of Transactions: {num_transactions}

Top Categories:
{categories_text}

Provide 3-4 key insights about spending patterns, potential concerns, and recommendations."""
        
        return self.generate_insight(prompt, max_new_tokens=400, temperature=0.7)
    
    def forecast_spending(
        self,
        historical_data: dict,
        forecast_month: str
    ) -> Optional[str]:
        """
        Forecast future spending based on historical data.
        
        Args:
            historical_data: Dict of {month: spending_amount}
            forecast_month: Month to forecast for
        
        Returns:
            Forecast analysis or None if failed
        """
        # Format historical data
        history_text = "\n".join([
            f"- {month}: ${amt:,.2f}"
            for month, amt in sorted(historical_data.items())
        ])
        
        prompt = f"""Based on this historical spending:

{history_text}

Forecast spending for {forecast_month} and provide:
1. Expected total spending amount
2. Key factors that might affect spending
3. Budget recommendations"""
        
        return self.generate_insight(prompt, max_new_tokens=400, temperature=0.7)
    
    def __del__(self):
        """Cleanup model from memory."""
        if self.model is not None:
            del self.model
        if self.tokenizer is not None:
            del self.tokenizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    # Test the model loader
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("Testing FinGPT Model Loader (HuggingFace)")
    print("=" * 70)
    
    # Initialize model
    print("\n1. Loading model...")
    loader = FinGPTModelLoaderHF(use_4bit=True)
    
    if loader.available:
        print("✅ Model loaded successfully")
        
        # Test spending analysis
        print("\n2. Testing spending analysis...")
        result = loader.analyze_spending(
            total_spending=18118.43,
            category_breakdown={
                "Shopping": 14165.00,
                "Rent/Mortgage": 1220.00,
                "Groceries": 850.50,
                "Dining": 425.30,
                "Transportation": 380.00
            },
            num_transactions=48,
            month="YYYY-MM"
        )
        
        if result:
            print("✅ Analysis generated:")
            print("-" * 70)
            print(result)
            print("-" * 70)
        else:
            print("❌ Analysis failed")
    else:
        print("❌ Model not available")
    
    print("\n" + "=" * 70)
