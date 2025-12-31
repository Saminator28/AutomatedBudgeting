#!/usr/bin/env python3
"""Test the normalization function."""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def normalize_test(name):
    """Test normalization logic."""
    # Add space before caps in concatenated words
    if ' ' not in name and any(c.isupper() for c in name[1:]):
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return name

test_cases = [
    "THEHOMEDEPOT",
    "Thehomedepot",
    "CASHWISE",
    "Cashwise",
    "COWBOYJACKS",
]

for test in test_cases:
    result = normalize_test(test)
    print(f"{test:20s} → {result}")
