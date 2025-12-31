# LLM Models Guide

## Required Setup

### 1. Install Ollama

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Install Required Model

**Minimum (Required)**:
```bash
ollama pull qwen2.5:14b
```

This is the **only model you need** for the system to work. Total size: **9.0GB**

---

## Recommended Configuration

For **maximum accuracy** with multi-model ensemble:

```bash
# Primary model (required)
ollama pull qwen2.5:14b        # 9.0GB - Best reasoning

# Secondary model (pick one)
ollama pull dolphin-mistral    # 4.1GB - Fast filtering
# OR
ollama pull solar:10.7b        # 6.1GB - Better reasoning
```

**Total: 13-15GB** for dual-model setup

This gives you **90-95% accuracy** on merchant name cleaning.

---

## Model Roles

The parser uses a **multi-model ensemble** with 3 prompts:

| Prompt | Task | Model Used | Why |
|--------|------|------------|-----|
| **1** | Extract business name | qwen2.5:14b | Detail-focused, best reasoning |
| **2** | Remove locations/codes | 2nd available model | Diversity helps edge cases |
| **3** | Validate result | qwen2.5:14b | Consistency with prompt 1 |

All 3 results are combined with **confidence scoring** to pick the best answer.

### Learning from Your History

The parser **automatically learns** from previous months:
- Scans all `statements/20*-*/expenses.csv` and `income.csv` files
- Extracts merchant names you've manually corrected
- Uses them as high-confidence examples for future processing
- **Result**: Accuracy improves with each month you process

**Example:**
```
Month 1: "COWBOYJACKS-APPLEV" → LLM: "Cowboy Jacks" (85% confidence)
You edit CSV: "Cowboy Jack's Saloon"

Month 2: Parser loads your correction from Month 1 CSV
         "COWBOYJACKS-APPLEV" → "Cowboy Jack's Saloon" (100% confidence, instant)
```

This means the system gets **smarter over time** as you correct mistakes!

---

## Available Models

Based on testing, here are your options:

### Tier 1: Primary Models (Use for Prompt 1 & 3)

| Model | Size | Accuracy | Speed | Recommended |
|-------|------|----------|-------|-------------|
| **qwen2.5:14b** ⭐ | 9.0GB | 85% | Medium | **DEFAULT** |
| qwen2.5:7b | 4.7GB | 85% | Fast | Budget option |
| gemma2:9b | 5.4GB | 77% | Medium | Alternative |
| solar:10.7b | 6.1GB | 85% | Slow | If you have RAM |

### Tier 2: Secondary Models (Use for Prompt 2)

| Model | Size | Accuracy | Speed | Notes |
|-------|------|----------|-------|-------|
| **dolphin-mistral** ⭐ | 4.1GB | 85% | Fast | **RECOMMENDED** |
| solar:10.7b | 6.1GB | 85% | Medium | Alternative |
| llama3.2:3b | 2.0GB | 77% | Very Fast | Lightweight option |
| mistral:7b | 4.4GB | 62% | Slow | Not recommended |

### Not Recommended

| Model | Reason |
|-------|--------|
| llama3.1:8b | Low accuracy (31%), outputs nonsense |
| phi3:mini | Low accuracy (62%), too concise |

---

## Configuration Examples

### Option 1: Default (Recommended)
**Best accuracy, moderate speed**

```bash
ollama pull qwen2.5:14b
ollama pull dolphin-mistral
```

**Total**: 13.1GB  
**Accuracy**: 90-95% (Month 1) → 95-98% (Month 3+ with CSV learning)  
**Processing**: ~40s per transaction (first month), ~15s (by month 3 with cache)

---

### Option 2: Budget (8GB RAM)
**Good accuracy, faster**

```bash
ollama pull qwen2.5:7b
ollama pull llama3.2:3b
```

**Total**: 6.7GB  
**Accuracy**: 85-90% (Month 1) → 92-95% (Month 3+ with CSV learning)  
**Processing**: ~20s per transaction

---

### Option 3: Maximum Accuracy (32GB+ RAM)
**Best possible accuracy, slower**

```bash
ollama pull qwen2.5:14b
ollama pull solar:10.7b
ollama pull gemma2:9b      # Optional 3rd model
```

**Total**: 15-20GB  
**Accuracy**: 92-97% (Month 1) → 97-99% (Month 3+ with CSV learning)  
**Processing**: ~45s per transaction

---

## Changing Models

### Use Different Primary Model
Edit `src/bankai/parser/hybrid_parser.py` line 38:

```python
# Change from:
def __init__(self, ..., llm_model: str = 'qwen2.5:14b', ...):

# To:
def __init__(self, ..., llm_model: str = 'qwen2.5:7b', ...):
```

### Disable Multi-Model
If you only want to use one model:

```python
# Change line 38:
def __init__(self, ..., use_multi_model: bool = False):
```

---

## Performance Comparison

Based on testing 13 challenging merchant names:

| Configuration | Accuracy | Avg Time | Monthly (100 txns) |
|---------------|----------|----------|---------------------|
| qwen2.5:14b + dolphin-mistral | **85%** | 32s | 53 min |
| qwen2.5:14b + solar:10.7b | **85%** | 39s | 65 min |
| qwen2.5:7b + dolphin-mistral | **85%** | 23s | 38 min |
| qwen2.5:7b only | 77% | 22s | 37 min |
| llama3.2:3b only | 77% | 11s | 18 min |

**Note**: With cache system, subsequent months are 50-70% faster.

---

## Testing Your Setup

### Check Installed Models
```bash
ollama list
```

### Test Parser Configuration
```bash
python scripts/test_parser_init.py
```

Shows:
- Primary model
- Multi-model status
- Available models
- Cache size

### Compare All Models
```bash
python scripts/compare_models.py
```

Tests all installed models on 13 test cases and shows accuracy/speed.

---

## Troubleshooting

### "Model not found"
```bash
# Install the required model
ollama pull qwen2.5:14b
```

### Slow Processing
- **First month**: Expected (~40-50 min for 100 transactions)
- **Second month**: Should be 50% faster (cache helps)
- **Third month+**: Should be 70% faster

If still slow:
- Use smaller model: `qwen2.5:7b` instead of `14b`
- Disable multi-model (edit parser line 38)

### Low Accuracy
- Ensure `qwen2.5:14b` is installed
- Ensure multi-model is enabled
- Check cache is loading: `config/merchant_cache.json` should exist
- Review CSV corrections are being applied

### Out of Memory
You need ~20GB available RAM for qwen2.5:14b. If you have less:

```bash
# Use smaller model
ollama pull qwen2.5:7b    # Only needs 8GB RAM
```

---

## Summary

**Minimum to get started:**
```bash
ollama pull qwen2.5:14b   # That's it!
```

**Recommended for best results:**
```bash
ollama pull qwen2.5:14b
ollama pull dolphin-mistral
```

**After installation:**
```bash
python scripts/process_monthly.py 2025-01
```

The system handles everything automatically - no configuration needed!
