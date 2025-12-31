#!/usr/bin/env python3
"""Test LLM directly to see if it's working."""

import requests

test_name = "THEHOMEDEPOT#3701 FARGO ND"

prompt = f"""Extract clean business name from transaction.

REMOVE ALL:
- City/state names (Fargo, ND, etc.)
- Store numbers (#3701)

Transaction: {test_name}
Name:"""

print(f"Testing LLM with: {test_name}")
print("=" * 60)

try:
    response = requests.post(
        'http://localhost:11434/api/generate',
        json={
            'model': 'qwen2.5:14b',
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': 0.0,
                'num_predict': 35,
            }
        },
        timeout=10
    )
    
    if response.status_code == 200:
        result = response.json().get('response', '').strip()
        print(f"✓ LLM Response: {result}")
    else:
        print(f"✗ HTTP Error: {response.status_code}")
except Exception as e:
    print(f"✗ Error: {e}")

print("=" * 60)
