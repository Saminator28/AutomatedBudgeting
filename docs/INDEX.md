# Documentation Index

## Main Documentation

### [README.md](../README.md)
**Start here!** Complete setup guide, usage instructions, and examples.

- Installation instructions
- Quick start guide
- Usage examples
- Troubleshooting

---

## Detailed Guides

### [MODELS.md](MODELS.md)
**LLM model configuration guide**

- Required models (qwen2.5:14b)
- Recommended configurations
- Performance comparisons
- Model testing tools
- Troubleshooting

**Quick Reference:**
```bash
# Minimum (required)
ollama pull qwen2.5:14b

# Recommended (best accuracy)
ollama pull qwen2.5:14b
ollama pull dolphin-mistral
```

---

### [PARSER_UPDATES.md](PARSER_UPDATES.md)
**Recent changes and new features**

- Model configuration changes
- User correction learning system
- Post-processing normalization
- Performance expectations
- Migration guide

**Key Features:**
- 90-95% accuracy with multi-model ensemble
- Learns from your CSV edits automatically
- Cache system for consistency

---

### [TECHNICAL.md](../TECHNICAL.md)
**System architecture and internals**

- PDF parsing strategies
- Multi-LLM validation system
- Cross-referencing logic
- Category classification
- Advanced features

**For developers and contributors**

---

## Quick Links

| Task | Document |
|------|----------|
| Setup from scratch | [README.md](../README.md) |
| Install/configure models | [MODELS.md](MODELS.md) |
| Understand recent changes | [PARSER_UPDATES.md](PARSER_UPDATES.md) |
| Deep dive into architecture | [TECHNICAL.md](../TECHNICAL.md) |
| Report issues | [GitHub Issues](https://github.com/yourusername/AutomatedBudgeting/issues) |

---

## File Structure

```
AutomatedBudgeting/
├── README.md                    # Main documentation
├── TECHNICAL.md                 # Architecture details
├── docs/
│   ├── INDEX.md                 # This file
│   ├── MODELS.md                # LLM model guide
│   └── PARSER_UPDATES.md        # Recent changes
├── scripts/
│   ├── process_monthly.py       # Main processing script
│   ├── compare_models.py        # Test model accuracy
│   └── test_parser_init.py      # Verify configuration
└── config/
    ├── merchant_cache.json      # Learned merchant names
    ├── category_patterns.json   # Category rules
    └── ...
```

---

## Getting Help

1. **Check README**: Most common questions answered there
2. **Check MODELS.md**: For model-related issues
3. **Run tests**: `python scripts/test_parser_init.py`
4. **Check logs**: Parser prints detailed status messages
5. **Open issue**: If problem persists

---

## Contributing

See [TECHNICAL.md](../TECHNICAL.md) for architecture overview and contribution guidelines.
