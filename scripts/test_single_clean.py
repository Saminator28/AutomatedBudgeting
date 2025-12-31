#!/usr/bin/env python3
"""Test merchant name cleaning on a single example."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bankai.parser.hybrid_parser import HybridPDFParser

# Initialize parser
print("Initializing parser...")
parser = HybridPDFParser()

# Test problematic names
test_cases = [
    ("THEHOMEDEPOT#3701 FARGO ND", "Home Depot"),
    ("CASHWISE #3045 WEST FARGO ND", "Cashwise"),
    ("COWBOYJACKS-APPLEV 952-5956372 MN", "Cowboy Jacks"),
    ("TST*THEPIGGYBBQOFWES WEST FARGO ND", "The Piggy BBQ"),
    ("WL*Steam Purchase 425-9522985 WA", "Steam"),
    ("WMSUPERCENTER #4352 FARGO ND", "Walmart"),
    ("BP#9267972HWY 13BP SAVAGE MN", "BP"),
    ("PIKEAND PINTGRILLINC ALEXANDRIA MN", "Pike And Pint Grill"),
]

print("\n" + "="*80)
print("Testing Merchant Name Cleaning")
print("="*80)

for raw, expected in test_cases:
    cleaned = parser._clean_merchant_name_with_context(raw, 50.0, "01/15/2025")
    match = "✓" if cleaned.lower().replace(" ", "") == expected.lower().replace(" ", "") else "✗"
    print(f"\n{match} Raw: {raw}")
    print(f"  Expected: {expected}")
    print(f"  Got:      {cleaned}")

print("\n" + "="*80)
