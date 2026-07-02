"""
LLM utility functions for merchant name cleaning via Ollama REST API.

Uses /api/chat directly instead of the Python SDK so that model-specific
parameters (think: false for qwen3/deepseek-r1/qwq) are passed exactly as
documented and never silently ignored.

Compatible with any model served by Ollama.
Set OLLAMA_BASE_URL to override the default http://localhost:11434.
"""

import os
import re
import sys
import json
import time
import requests
from typing import Optional

OLLAMA_BASE_URL = (os.environ.get('OLLAMA_BASE_URL')
                   or os.environ.get('OLLAMA_HOST', 'http://localhost:11434'))

# Track which models we've already pulled this session so we only attempt once
_pulled_models: set = set()


# ---------------------------------------------------------------------------
# Model auto-pull
# ---------------------------------------------------------------------------

def ensure_model_pulled(model: str, base_url: str = None) -> bool:
    """
    Pull *model* from the Ollama registry if it isn't present locally.
    Streams download progress to stdout so it is visible in the GUI job log.
    Returns True if the pull succeeded, False otherwise.
    Only attempts once per model per process lifetime.
    """
    global _pulled_models
    if model in _pulled_models:
        return False  # already attempted this session
    _pulled_models.add(model)

    if base_url is None:
        base_url = OLLAMA_BASE_URL

    print(f"\n⬇️  Model '{model}' not found locally — pulling from Ollama registry...")
    print(f"   This may take several minutes depending on model size.")
    sys.stdout.flush()

    try:
        with requests.post(
            f'{base_url}/api/pull',
            json={'model': model, 'stream': True},
            stream=True,
            timeout=3600,
        ) as resp:
            resp.raise_for_status()
            last_status = ''
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except Exception:
                    continue
                status = data.get('status', '')
                total     = data.get('total', 0)
                completed = data.get('completed', 0)
                is_progress = total and completed
                if is_progress:
                    pct = int(100 * completed / total)
                    print(f"\r   {status}: {pct}%  ", end='', flush=True)
                elif status != last_status:
                    if last_status and total:
                        print()  # newline after progress bar
                    print(f"   {status}")
                    sys.stdout.flush()
                last_status = status
            print()  # final newline
        print(f"✅ Model '{model}' pulled successfully")
        sys.stdout.flush()
        return True
    except Exception as exc:
        print(f"\n❌ Failed to pull model '{model}': {exc}")
        sys.stdout.flush()
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ollama_chat(
    model: str,
    messages: list,
    options: dict = None,
    think: bool = False,
    timeout: int = 120,
) -> dict:
    """
    POST to Ollama /api/chat and return the parsed JSON response.

    `think` is a top-level key in the payload — NOT inside `options`.
    This is the correct Ollama API location; putting it in options is silently ignored.
    """
    payload = {
        'model':    model,
        'messages': messages,
        'stream':   False,
        'think':    think,
        'options':  options or {},
    }
    resp = requests.post(f'{OLLAMA_BASE_URL}/api/chat', json=payload, timeout=timeout)
    # Auto-pull if the model isn't present, then retry once
    if resp.status_code == 404 and 'not found' in resp.text.lower():
        pulled = ensure_model_pulled(model)
        if pulled:
            resp = requests.post(f'{OLLAMA_BASE_URL}/api/chat', json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _extract_content(response: dict) -> tuple:
    """Return (content, thinking) strings from a raw Ollama response dict."""
    msg      = response.get('message', {})
    content  = (msg.get('content')  or '').strip()
    thinking = (msg.get('thinking') or '').strip()
    return content, thinking


def _clean_md(raw: str) -> str:
    """Strip markdown bold/italic so **Answer:** becomes Answer:"""
    return raw.strip().strip('*').strip('_').strip()


# Words that begin reasoning sentences, never a real merchant name
_REASONING_STARTS = (
    'wait', 'okay', 'ok,', 'but ', 'but,', 'however', 'so,', 'so the',
    'the ', 'this ', 'let ', "let's", 'i ', 'in ', 'if ', 'also,',
    'note', 'now', 'since', 'actually', 'alternatively', 'maybe',
    'example:', 'transaction:', 'recur ', 'pos purchase',
)


def _extract_from_thinking(thinking: str, debug: bool = False) -> str:
    """
    Pull a 'Name | Confidence | Reasoning' answer out of the thinking field
    when the model wrote nothing to content.

    Pass 1  — line that starts with 'Answer:'
    Pass 1b — 'answer:' anywhere mid-line (e.g. 'So answer: "Name | 85 | ..."')
    Pass 2  — pipe-delimited line where field[0] looks like a merchant name
    Pass 3  — partial/cut-off pipe line (Name | Confidence, reasoning missing)
    """
    lines = thinking.split('\n')

    def _candidate_from_answer_tag(line: str):
        """Extract the text after 'answer:' in a line, stripping surrounding quotes/punctuation."""
        idx = line.lower().find('answer:')
        if idx == -1:
            return ''
        candidate = line[idx + 7:].strip()
        # Strip wrapping quotes and trailing sentence punctuation
        candidate = re.sub(r'^["\u201c\']+|["\u201d\'.,]+$', '', candidate).strip()
        return candidate if len(candidate) >= 2 else ''

    # Pass 1 — line starts with Answer:
    for line in reversed(lines):
        line = _clean_md(line)
        if line.lower().startswith('answer:'):
            candidate = _candidate_from_answer_tag(line)
            if candidate:
                if debug:
                    print(f"  [DEBUG] Extracted 'Answer:' from thinking: '{candidate[:100]}'")
                return candidate

    # Pass 1b — 'answer:' appears mid-line (e.g. 'So answer: "Name | 85 | ..."')
    for line in reversed(lines):
        line = _clean_md(line)
        if 'answer:' in line.lower() and '|' in line:
            candidate = _candidate_from_answer_tag(line)
            if candidate and '|' in candidate:
                if debug:
                    print(f"  [DEBUG] Extracted mid-line 'answer:' from thinking: '{candidate[:100]}'")
                return candidate

    # Pass 2 — complete Name | Confidence | Reasoning pipe line
    for line in reversed(lines):
        line = _clean_md(line)
        if '|' not in line:
            continue
        parts = line.split('|')
        if len(parts) < 2:
            continue
        name_part = parts[0].strip().strip('*').strip('_').strip()
        conf_part = parts[1].strip().strip('*').strip('_').strip().rstrip('%')  # strip % suffix
        # Skip reasoning sentences masquerading as a name field
        if any(name_part.lower().startswith(p) for p in _REASONING_STARTS):
            continue
        # Accept: short alphabetic name, numeric confidence
        if (2 <= len(name_part) <= 60
                and any(c.isalpha() for c in name_part)
                and (conf_part.isdigit() or (len(conf_part) >= 2 and conf_part[:2].isdigit()))):
            result = f"{name_part} | {conf_part}" + (f" | {parts[2].strip()}" if len(parts) > 2 else "")
            if debug:
                print(f"  [DEBUG] Extracted pipe line from thinking: '{result[:100]}'")
            return result

    # Pass 3 — partial/cut-off answer: grab last 'Name | ...' fragment even without full reasoning
    # This catches cases where num_predict cuts off mid-sentence after the name+confidence
    for line in reversed(lines):
        line = _clean_md(line)
        # Look for quoted partial answers like: '"Merchant Name | 85 |'
        quoted = re.search(r'["\u201c]([^"\u201d]{2,60}\s*\|\s*\d+)', line)
        if quoted:
            candidate = quoted.group(1).strip()
            if debug:
                print(f"  [DEBUG] Extracted quoted partial answer: '{candidate[:100]}'")
            return candidate

    if debug:
        tail = [l.strip() for l in lines if l.strip()][-5:]
        print(f"  [DEBUG] Thinking extraction failed. Last lines: {tail}")
    return ''


def _parse_answer(raw: str, debug: bool = False) -> Optional[str]:
    """
    Validate and normalise a raw LLM answer into 'Name | confidence | reasoning'.
    Returns None if unparseable.
    """
    result = raw.strip().strip('"').strip("'").strip()

    # Multiple lines — find the best one
    if '\n' in result:
        lines  = result.split('\n')
        chosen = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(skip in line.lower() for skip in
                   ['okay, i understand', 'here is', "here's", 'i will',
                    'format i will use', 'ready to process']):
                continue
            if line.lower().startswith('answer:'):
                chosen = line[7:].strip()
                break
            if '|' in line and len(line) < 200:
                parts = line.split('|')
                if len(parts) >= 2 and any(c.isalpha() for c in parts[0]):
                    chosen = line
                    break
        if chosen is None:
            for line in reversed(lines):
                if line.strip():
                    chosen = line.strip()
                    break
        result = chosen or result

    # Strip common preamble prefixes
    for prefix in ('transaction:', 'extracted:', 'company name:', 'business name:',
                   'company:', 'business:', 'name:', 'answer:'):
        if result.lower().startswith(prefix):
            result = result[len(prefix):].strip()
            break

    if not result:
        return None

    # Parse Name | Confidence | Reasoning
    if '|' in result:
        parts      = result.split('|')
        name       = parts[0].strip().strip('*').strip()
        confidence = parts[1].strip().rstrip('%') if len(parts) > 1 else 'unknown'  # strip % suffix
        # Reasoning may be multi-line (verbose models); collapse to single line
        reasoning  = ' '.join(parts[2].split()) if len(parts) > 2 else ''
        if not (2 <= len(name) <= 80):
            if debug:
                print(f"  [DEBUG] Name invalid length: '{name}'")
            return None
        result = f"{name} | {confidence} | {reasoning}"
    else:
        if len(result) > 80:
            if debug:
                print(f"  [DEBUG] Unstructured result too long")
            return None
        result = f"{result} | 50 | No confidence provided"

    # Title-case name, fix apostrophe capitalisation
    parts = result.split('|')
    name  = parts[0].strip().title()
    name  = re.sub(r"'S\b", "'s", name)
    name  = re.sub(r"'T\b", "'t", name)
    result = f"{name} | {parts[1].strip()}" + (f" | {parts[2].strip()}" if len(parts) > 2 else "")
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_merchant_name_llm(
    merchant:    str,
    model:       str,
    amount:      float = None,
    date:        str   = None,
    known_names: list  = None,
    max_retries: int   = 3,
    debug:       bool  = False,
) -> Optional[str]:
    """
    Extract a clean merchant name from raw transaction text using an Ollama model.

    Returns 'CleanName | confidence | reasoning', or None if all retries fail.
    """
    # Build optional known-merchants section to anchor the LLM on previous spellings
    known_section = ''
    if known_names:
        names_list = '\n'.join(f'  - {n}' for n in known_names)
        known_section = f"""

Known merchants from this account (use the EXACT spelling shown if the transaction matches):
{names_list}
"""

    prompt = f"""Given any transaction description, your task is to extract only the full company or business name from the text provided. Remove any additional information such as dates, locations (towns/cities/states), transaction reference numbers, and irrelevant details like 'RECUR PURCHASE'. Ensure that the extracted name is free of typos and correctly spelled.

IMPORTANT:
- Extract the MERCHANT where the purchase was made, NOT the bank/credit card that was used
- Use the business name exactly as it appears in the transaction. Do NOT infer parent companies or legal entities (e.g., "Service Portal" should stay "Service Portal", not "Parent Corporation").
- Fix concatenated words by adding spaces (e.g., "BUSINESSAND SERVICEGROUPINC" → "Business And Service Group Inc")
- Fix capitalization (e.g., "GENERIC MARKET" → "Generic Market")
- Expand common abbreviations to their full word (e.g., "Whse" → "Warehouse", "Cuis" → "Cuisine", "Mkt" → "Market", "Intl" → "International", "Assoc" → "Associates", "Mgmt" → "Management", "Svc" → "Services", "Dept" → "Department", "Corp" → "Corporation", "Bros" → "Brothers", "WM" or "Wm" at the start of a name → "Walmart", "Compa" → "Company")
- Remove payment processor prefixes (TST*, SQ*, WL*, etc.) but keep the actual merchant name
- Remove store/location numbers preceded by # (e.g. "#3370", "#1502") but KEEP numbers that are part of the business name (e.g. "411 Management", "76 Gas Station", "7-Eleven")
- ALWAYS provide a business name. NEVER return empty or "Answer:" alone.
- Give a confidence score from 1-100 using this scale:
    90-100: The name is clear and you are highly certain (e.g. national retailer, fuel station, airline)
    70-89:  Clear match with minor cleanup needed (removed prefix/location/number)
    50-69:  Educated guess — partial match or ambiguous abbreviation
    1-49:   Low confidence — OCR corruption, unknown abbreviation, or very uncertain
- Keep the reasoning under 20 words.
- Respond with ONLY this format and nothing else: Name | Confidence | Reasoning{known_section}
Example:
Transaction: "RECUR RETAILCENTER #3472 [Town Name/State] 12/25"
Answer: Retail Center | 85 | Removed recurrence tag, location, and store number

Transaction: "WAREHOUSECLUB #1119 CITY_A ST"
Answer: Warehouse Club | 95 | Expanded abbreviation, removed store number and location

Transaction: {merchant}
Answer:"""

    options = {'temperature': 0.0, 'num_predict': 2048, 'top_p': 0.9}

    for attempt in range(max_retries):
        try:
            if debug:
                print(f"  [DEBUG] Sending to LLM: '{merchant[:80]}{'...' if len(merchant) > 80 else ''}'")

            response = _ollama_chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                options=options,
                think=False,  # disable thinking for all models — we want content only
            )

            content, thinking = _extract_content(response)

            if debug and thinking:
                print(f"  [DEBUG] Has thinking field ({len(thinking)} chars)")

            # Fallback: pull answer from thinking field if content is empty
            if not content and thinking:
                if debug:
                    print(f"  [DEBUG] Response empty, extracting from thinking field ({len(thinking)} chars)")
                content = _extract_from_thinking(thinking, debug=debug)

            if not content:
                if debug:
                    print(f"  [DEBUG] Result rejected (empty)")
                continue

            parsed = _parse_answer(content, debug=debug)
            if parsed:
                if debug:
                    print(f"  [DEBUG] [{model}] returned: '{parsed[:150]}{'...' if len(parsed) > 150 else ''}'")
                return parsed
            if debug:
                print(f"  [DEBUG] Result rejected (failed validation)")

        except requests.Timeout:
            msg = f"Ollama request timed out (>{120}s)"
            if debug:   print(f"  [LLM Error] Attempt {attempt + 1}/{max_retries}: {msg}")
            elif attempt == 0: print(f"  [LLM Error] {msg}")
        except requests.ConnectionError as e:
            msg = f"Cannot reach Ollama at {OLLAMA_BASE_URL}"
            if debug:   print(f"  [LLM Error] Attempt {attempt + 1}/{max_retries}: {msg}: {e}")
            elif attempt == 0: print(f"  [LLM Error] {msg}")
        except requests.HTTPError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            if debug or attempt == 0: print(f"  [LLM Error] {msg}")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if debug:   print(f"  [LLM Error] Attempt {attempt + 1}/{max_retries}: {msg}")
            elif attempt == 0: print(f"  [LLM Error] {msg}")

        if attempt < max_retries - 1:
            wait = 2 ** (attempt + 1)
            if debug:
                print(f"  [Retry] Waiting {wait}s before retry...")
            time.sleep(wait)

    print(f"  [LLM Error] Max retries ({max_retries}) exceeded for: '{merchant[:60]}'")
    return None


def select_best_merchant_name(
    result1:          str,
    result2:          str,
    original_merchant: str,
    reasoning_model:  str,
    debug:            bool = False,
) -> str:
    """
    Pick the better of two 'Name | confidence | reasoning' results.
    Uses confidence scores first; breaks ties with a reasoning LLM call.
    """
    if not result1 and not result2:
        return None
    if not result1:
        return result2
    if not result2:
        return result1

    def parse(r):
        parts = r.split('|')
        if len(parts) >= 2:
            name = parts[0].strip()
            try:    conf = int(parts[1].strip())
            except: conf = 50
            reason = parts[2].strip() if len(parts) > 2 else ''
            return name, conf, reason
        return r.strip(), 50, ''

    name1, conf1, reason1 = parse(result1)
    name2, conf2, reason2 = parse(result2)

    if name1.lower() == name2.lower():
        return result1 if conf1 >= conf2 else result2

    if abs(conf1 - conf2) > 20:
        winner = result1 if conf1 > conf2 else result2
        w_name = name1  if conf1 > conf2 else name2
        w_conf = conf1  if conf1 > conf2 else conf2
        l_name = name2  if conf1 > conf2 else name1
        l_conf = conf2  if conf1 > conf2 else conf1
        if debug:
            print(f"  [Ensemble] Chose '{w_name}' (conf: {w_conf}) over '{l_name}' (conf: {l_conf})")
        return winner

    if debug:
        print(f"  [Ensemble] Reasoning between '{name1}' and '{name2}'")

    reasoning_prompt = f"""Two AI models cleaned this merchant name differently. Choose the BETTER result.

Original: {original_merchant}
Option A: {name1} (Confidence: {conf1}) — {reason1}
Option B: {name2} (Confidence: {conf2}) — {reason2}

Reply with only 'A' or 'B'."""

    try:
        response = _ollama_chat(
            model=reasoning_model,
            messages=[{'role': 'user', 'content': reasoning_prompt}],
            options={'temperature': 0.0, 'num_predict': 10},
            think=False,
        )
        content, _ = _extract_content(response)
        choice = content.upper()
        if 'A' in choice[:3]:
            if debug: print(f"  [Ensemble] Chose A: '{name1}'")
            return result1
        if 'B' in choice[:3]:
            if debug: print(f"  [Ensemble] Chose B: '{name2}'")
            return result2
    except Exception as e:
        if debug:
            print(f"  [Ensemble] Reasoning failed: {e}")

    return result1 if conf1 >= conf2 else result2


def detect_institution_with_llm(
    header_text: str,
    model: str,
    debug: bool = False,
) -> Optional[str]:
    """
    Ask the LLM to identify the bank/issuer name from the first ~80 lines of a
    statement.  Returns a short institution name string, or None on failure.

    The header_text passed in is already the joined first-80-lines string, so the
    LLM only sees the most signal-dense part of the document.
    """
    # Trim to ~2 000 chars so prompt stays short and fast
    snippet = header_text[:2000].strip()
    if not snippet:
        return None

    prompt = (
        "You are reading the top of a bank or credit-card statement PDF.\n"
        "Identify the financial institution (bank or card issuer) that issued this statement.\n"
        "Use the short, common name only — for example:\n"
        "  'Citibank' not 'Citibank N.A.'\n"
        "  'Wells Fargo' not 'Wells Fargo Bank, N.A.'\n"
        "Reply with ONLY the institution name — no explanation, no punctuation, no extra words.\n"
        "If you cannot determine the institution, reply with exactly: Unknown\n\n"
        f"Statement header:\n{snippet}"
    )
    messages = [{'role': 'user', 'content': prompt}]
    try:
        response = _ollama_chat(
            model=model,
            messages=messages,
            options={'temperature': 0, 'num_predict': 32},
            think=False,
            timeout=30,
        )
        content, _ = _extract_content(response)
        name = content.strip().strip('"\'.').strip()
        if debug:
            print(f'  [LLM institution] raw response: {repr(name)}')
        # Reject non-answers
        if not name or name.lower() in {'unknown', 'unknown institution', 'n/a', 'none', ''}:
            return None
        # Reject if the model hallucinated a long sentence
        if len(name) > 80 or '\n' in name:
            return None
        return name
    except Exception as exc:
        if debug:
            print(f'  [LLM institution] error: {exc}')
        return None


def clean_merchant_with_ensemble(
    merchant:        str,
    primary_model:   str,
    secondary_model: Optional[str],
    amount:          float = None,
    date:            str   = None,
    known_names:     list  = None,
    debug:           bool  = False,
) -> str:
    """
    Clean a merchant name using one or two Ollama models.
    Returns just the clean name string.  Falls back to the raw original on total failure.
    """
    result_primary = clean_merchant_name_llm(
        merchant, primary_model, amount, date, known_names=known_names, max_retries=3, debug=debug
    )

    if not secondary_model or not result_primary:
        return result_primary.split('|')[0].strip() if result_primary else merchant

    result_secondary = clean_merchant_name_llm(
        merchant, secondary_model, amount, date, known_names=known_names, max_retries=3, debug=debug
    )

    if not result_secondary:
        return result_primary.split('|')[0].strip()

    best = select_best_merchant_name(
        result_primary, result_secondary, merchant, primary_model, debug=debug
    )
    return best.split('|')[0].strip() if best else merchant


def clean_merchant_batch(
    merchants:   list,
    model:       str,
    batch_size:  int  = 6,
    debug:       bool = False,
) -> dict:
    """
    Clean a list of raw merchant/transaction strings in batches of *batch_size*
    instead of one HTTP call per merchant.  On Ryzen 5/7 hardware a batch of 6
    completes in roughly the same wall-clock time as 1–2 individual calls.

    Returns a dict mapping each raw merchant string to its cleaned name (just the
    name, no confidence/reasoning suffix).  Merchants that the batch call cannot
    resolve fall back to ``clean_merchant_name_llm`` individually.

    Args:
        merchants:  list of raw transaction description strings
        model:      Ollama model name (primary_model)
        batch_size: items per LLM call; keep ≤ 8 for slower hardware
        debug:      print verbose output for troubleshooting

    Returns:
        dict of {raw_merchant: clean_name}
    """
    if not merchants:
        return {}

    results: dict = {}

    for chunk_start in range(0, len(merchants), batch_size):
        chunk = merchants[chunk_start: chunk_start + batch_size]

        merchant_lines = "\n".join(
            f"Transaction {i + 1}: {raw}" for i, raw in enumerate(chunk)
        )

        prompt = f"""Clean each transaction description below into a merchant name.
For each, reply on one line: "N. CleanName | Confidence | Reasoning"
Confidence is 1-100. Reasoning is under 15 words.
No extra text — one line per transaction.

Rules:
- Remove dates, locations, store numbers, payment processor prefixes (SQ*, TST*, WL*)
- Fix capitalization and expand common abbreviations (WM → Walmart, etc.)
- ALWAYS give a name — never leave a line blank.

{merchant_lines}

Your response:"""

        try:
            response = _ollama_chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.0,
                    'num_predict': 512,
                    'stop':        ['<|end|>', '<|im_end|>'],
                },
                think=False,
                timeout=120,
            )
            content, thinking = _extract_content(response)

            if not content and thinking:
                content = _extract_from_thinking(thinking, debug=debug)

            if debug:
                print(f"  [batch] raw response for chunk {chunk_start}: {content[:300]}")

            for line in (content or '').split('\n'):
                line = line.strip()
                # Match "N. Name | conf | reason" or "N) Name | conf | reason"
                m = re.match(r'^(\d+)[.)]\s*(.+)$', line)
                if not m:
                    continue
                idx = int(m.group(1)) - 1
                if idx < 0 or idx >= len(chunk):
                    continue
                raw_merchant = chunk[idx]
                parsed = _parse_answer(m.group(2).strip(), debug=debug)
                if parsed:
                    results[raw_merchant] = parsed.split('|')[0].strip()

        except Exception as exc:
            if debug:
                print(f"  [batch] chunk {chunk_start} failed: {exc}")

    # Fall back to individual calls for anything the batch missed
    for raw in merchants:
        if raw not in results:
            if debug:
                print(f"  [batch fallback] individual call for: {raw[:60]}")
            single = clean_merchant_name_llm(raw, model, debug=debug)
            if single:
                results[raw] = single.split('|')[0].strip()
            else:
                results[raw] = raw  # last resort: keep original

    return results
