#!/usr/bin/env python3
"""
Preflight check: verify every model listed in config/llm_models.json is
installed in the host's local Ollama before the app is allowed to start.

Runs on the host machine as part of `make up`.  If any configured model is
missing, prints the exact `ollama pull <model>` command the user should run
and exits non-zero so `make up` aborts before touching Docker.

Exit codes:
    0  every configured model is installed (or the config lists none)
    1  one or more configured models are missing
    2  cannot reach the host Ollama at all (misconfiguration / not running)
    3  config file missing or unreadable
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'llm_models.json'
DEFAULT_OLLAMA_HOST = 'http://localhost:11434'
MODEL_KEYS = ('primary_model', 'secondary_model', 'financial_analysis_model')


def _load_configured_models() -> dict[str, str]:
    """Return {role: model_name} for every non-empty configured model."""
    try:
        with CONFIG_PATH.open('r', encoding='utf-8') as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        print(f"❌ Model config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(3)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ Could not read model config {CONFIG_PATH}: {exc}", file=sys.stderr)
        sys.exit(3)

    result: dict[str, str] = {}
    for key in MODEL_KEYS:
        value = str(cfg.get(key) or '').strip()
        if value:
            result[key] = value
    return result


def _fetch_installed_models(host: str) -> set[str]:
    """Return the set of installed Ollama model tags reported by /api/tags."""
    url = f"{host.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(
            f"❌ Cannot reach Ollama at {host} ({exc}).\n"
            f"   The app needs Ollama running on the host machine to serve AI models.\n"
            f"   Start Ollama, then rerun `make up`.\n"
            f"   • macOS / Windows: open the Ollama desktop app\n"
            f"   • Linux:           run `ollama serve` (or `systemctl start ollama`)",
            file=sys.stderr,
        )
        sys.exit(2)

    tags: set[str] = set()
    for entry in payload.get('models', []):
        name = entry.get('name') or entry.get('model')
        if not name:
            continue
        tags.add(name)
        # Ollama reports tagged names like "gemma4:31b"; also index the bare
        # base so a config value without a tag still matches an installed tag.
        if ':' in name:
            tags.add(name.split(':', 1)[0])
    return tags


def _is_installed(model: str, installed: set[str]) -> bool:
    """A configured model is installed if either the exact tag matches, or the
    bare base name matches (Ollama returns 'llama3:latest' but user may set
    'llama3' in config, and vice versa)."""
    if model in installed:
        return True
    if ':' not in model and f"{model}:latest" in installed:
        return True
    if ':' in model and model.split(':', 1)[0] in installed:
        return True
    return False


def main() -> int:
    configured = _load_configured_models()
    if not configured:
        print("ℹ️  No models configured in config/llm_models.json — skipping check.")
        return 0

    host = os.environ.get('OLLAMA_HOST') or DEFAULT_OLLAMA_HOST
    # Docker-only host aliases won't work from the host machine; strip them.
    if 'host.docker.internal' in host or 'gateway.docker.internal' in host:
        host = DEFAULT_OLLAMA_HOST

    installed = _fetch_installed_models(host)

    missing: list[tuple[str, str]] = []
    for role, model in configured.items():
        if _is_installed(model, installed):
            print(f"✅ {role}: {model}")
        else:
            print(f"❌ {role}: {model}  (not installed)")
            missing.append((role, model))

    if not missing:
        print("\n✨ All configured models are installed — proceeding.")
        return 0

    print(
        "\n⛔ Refusing to start the app: one or more configured Ollama models are missing.\n"
        "\n   Install the missing model(s) with:\n"
    )
    for _role, model in missing:
        print(f"       ollama pull {model}")
    print(
        "\n   Then rerun:  make up"
        "\n"
        "\n   To use a smaller model, edit config/llm_models.json before rerunning."
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
