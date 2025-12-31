#!/usr/bin/env python3
"""
Model Comparison Tool

Test different Ollama models on merchant name cleaning to find the best one.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bankai.parser.hybrid_parser import HybridPDFParser
import time
import subprocess

# Test cases covering different challenges
TEST_CASES = [
    # Format: (raw_name, expected_output, description)
    ("TARGET #1234 FARGO ND", "Target", "Store with location"),
    ("WALMART SUPERCENTER #4352 FARGO", "Walmart", "Supercenter variant"),
    ("SQSP* INV165866692", "Squarespace", "Payment processor code"),
    ("CASH APP* JOHN DOE", "Cash App", "Personal name after"),
    ("BP#9267972HWY 13BP SAVAGE MN", "BP", "Gas station with codes"),
    ("COWBOYJACKS-APPLEV", "Cowboy Jacks", "Concatenated name"),
    ("WL*Steam Purchase", "Steam", "WorldLine processor"),
    ("THE HOME DEPOT #3701 WEST FARGO", "Home Depot", "THE prefix + location"),
    ("DECOR&MOREFROM RUE FARGO ND", "Decor & More", "Ampersand handling"),
    ("PIKEAND PINTGRILLINC ALEXANDRIA", "Pike And Pint Grill Inc", "Compressed business"),
    ("XX4297 RECUR PURCHASE YSI* MAPLE RIDGE VILLA", "Maple Ridge Villa", "Multiple prefixes"),
    ("TST* RESTAURANT NAME MOORHEAD MN", "Restaurant Name", "Toast prefix"),
    ("SQ* COFFEE SHOP", "Coffee Shop", "Square prefix"),
]

# Models to test (comment out unavailable ones)
MODELS_TO_TEST = [
    # Small/Medium models (good baseline)
    'qwen2.5:7b',           # Current default (4.4GB)
    'dolphin-mistral',      # Already installed (3.8GB)
    'llama3.2:3b',          # Fast, good at NER (2.0GB) - recommended
    'gemma2:9b',            # Great at structured tasks (5.4GB) - recommended
    'phi3:mini',            # Tiny but powerful (2.3GB) - recommended
    'llama3.1:8b',          # Latest Llama (4.7GB)
    'mistral:7b',           # Fast, concise (4.1GB)
    
    # Larger models (~14B+) - Better accuracy, slower
    'qwen2.5:14b',          # More capable Qwen (9.0GB) ⭐ RECOMMENDED
    'solar:10.7b',        # SOLAR model, excellent reasoning (6.1GB) ⭐ RECOMMENDED
    # 'mixtral:8x7b',       # Mixture of experts, very capable (26GB)
    # 'yi:34b',             # Strong reasoning, multilingual (19GB)
    # 'nous-hermes2:34b',   # Excellent instruction following (19GB)
    # 'command-r:35b',      # Cohere model, great at tasks (20GB)
]

def check_model_installed(model: str) -> bool:
    """Check if Ollama model is installed."""
    try:
        result = subprocess.run(
            ['ollama', 'list'], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        return model in result.stdout or model.split(':')[0] in result.stdout
    except:
        return False

def test_model(model_name: str):
    """Test a model on all test cases."""
    print(f"\n{'='*80}")
    print(f"Testing: {model_name}")
    print(f"{'='*80}")
    
    # Check if model is installed
    if not check_model_installed(model_name):
        print(f"⚠ Model not installed. Install with: ollama pull {model_name}")
        return None
    
    try:
        parser = HybridPDFParser(llm_model=model_name, use_multi_model=False)
        
        results = {
            'model': model_name,
            'correct': 0,
            'total': len(TEST_CASES),
            'times': [],
            'failures': []
        }
        
        for raw_name, expected, description in TEST_CASES:
            start = time.time()
            
            try:
                cleaned = parser._clean_merchant_name_with_context(raw_name, 50.0, "01/15/2025")
                elapsed = time.time() - start
                results['times'].append(elapsed)
                
                # Check if correct with lenient matching
                # Allow: case differences, extra words, missing spaces, "THE" prefix
                cleaned_norm = cleaned.lower().replace('the ', '').replace(' ', '').replace('&', '')
                expected_norm = expected.lower().replace('the ', '').replace(' ', '').replace('&', '')
                
                # Check if expected is contained in cleaned (allows extra text)
                is_correct = (expected_norm in cleaned_norm or 
                             cleaned_norm in expected_norm or
                             cleaned.lower() == expected.lower())
                
                if is_correct:
                    results['correct'] += 1
                    status = "✓"
                else:
                    status = "✗"
                    results['failures'].append({
                        'input': raw_name,
                        'expected': expected,
                        'got': cleaned,
                        'description': description
                    })
                
                print(f"{status} {description:30s} → {cleaned:20s} ({elapsed:.2f}s)")
                
            except Exception as e:
                print(f"✗ {description:30s} → ERROR: {str(e)[:40]}")
                results['failures'].append({
                    'input': raw_name,
                    'expected': expected,
                    'got': f"ERROR: {e}",
                    'description': description
                })
        
        # Calculate statistics
        accuracy = (results['correct'] / results['total']) * 100
        avg_time = sum(results['times']) / len(results['times']) if results['times'] else 0
        
        print(f"\n📊 Results:")
        print(f"   Accuracy: {results['correct']}/{results['total']} ({accuracy:.1f}%)")
        print(f"   Avg time: {avg_time:.2f}s per transaction")
        print(f"   Total time: {sum(results['times']):.2f}s")
        
        if results['failures']:
            print(f"\n❌ Failures ({len(results['failures'])}):")
            for failure in results['failures'][:3]:  # Show first 3
                print(f"   {failure['description']}")
                print(f"      Expected: {failure['expected']}")
                print(f"      Got:      {failure['got']}")
        
        return results
        
    except Exception as e:
        print(f"❌ Error testing {model_name}: {e}")
        return None

def main():
    """Run model comparison."""
    print("🔍 Model Comparison Tool")
    print("=" * 80)
    print(f"Testing {len(TEST_CASES)} merchant name cleaning scenarios")
    print(f"Models to test: {len(MODELS_TO_TEST)}")
    
    all_results = []
    
    for model in MODELS_TO_TEST:
        result = test_model(model)
        if result:
            all_results.append(result)
    
    if len(all_results) > 1:
        print("\n" + "=" * 80)
        print("📈 Comparison Summary")
        print("=" * 80)
        print(f"{'Model':<20s} {'Accuracy':>10s} {'Avg Time':>10s} {'Total Time':>12s}")
        print("-" * 80)
        
        for result in sorted(all_results, key=lambda x: x['correct'], reverse=True):
            accuracy = (result['correct'] / result['total']) * 100
            avg_time = sum(result['times']) / len(result['times']) if result['times'] else 0
            total_time = sum(result['times'])
            
            print(f"{result['model']:<20s} "
                  f"{accuracy:>9.1f}% "
                  f"{avg_time:>9.2f}s "
                  f"{total_time:>11.2f}s")
        
        # Recommendation
        best_accuracy = max(all_results, key=lambda x: x['correct'])
        best_speed = min(all_results, key=lambda x: sum(x['times']))
        
        print("\n🏆 Recommendations:")
        print(f"   Best accuracy: {best_accuracy['model']} "
              f"({(best_accuracy['correct']/best_accuracy['total'])*100:.1f}%)")
        print(f"   Fastest: {best_speed['model']} "
              f"({sum(best_speed['times']):.2f}s total)")
    
    print("\n" + "=" * 80)
    print("💡 To install a model: ollama pull <model-name>")
    print("   Example: ollama pull llama3.2:3b")
    print("\n   Recommended for merchant cleaning:")
    print("   • llama3.2:3b (2GB) - Best balance of speed + accuracy")
    print("   • phi3:mini (2.3GB) - Fastest, still accurate")
    print("   • gemma2:9b (5.4GB) - Most accurate, slower")

if __name__ == '__main__':
    main()
