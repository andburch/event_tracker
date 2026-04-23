"""
tools/check_groq_quota.py — Show remaining Groq API quota from response headers.

WARNING: This script only shows per-minute token (TPM) and daily request (RPD)
limits from Groq's response headers. Groq does NOT expose daily token (TPD)
usage in its API headers. To check daily token usage — which is the limit you
will actually hit during bulk scraping — use the LLM Usage dashboard at
/llm-usage, which computes a rolling 24h token window from the llm_calls DB
table. If the dashboard says "Over limit", trust it over this script.

Fires a minimal 1-token request per (key, model) and reads the rate limit
headers Groq returns on every response:

  x-ratelimit-remaining-requests  — Requests left today (RPD)
  x-ratelimit-remaining-tokens    — Tokens left this MINUTE (TPM) — NOT daily
  x-ratelimit-limit-requests      — Your daily request cap
  x-ratelimit-limit-tokens        — Your per-minute token cap (NOT daily)
  x-ratelimit-reset-requests      — Time until daily request limit resets
  x-ratelimit-reset-tokens        — Time until per-minute token limit resets

Checks all configured keys (GROQ_API_KEY + GROQ_API_KEY_2) by default.

Usage:
    python tools/check_groq_quota.py                    # Check all keys, all models
    python tools/check_groq_quota.py --model <name>     # Check specific model on all keys
    python tools/check_groq_quota.py --key 1            # Check only key 1
    python tools/check_groq_quota.py --key 2            # Check only key 2
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import config

def check_quota(label: str, api_key: str, model: str):
    """Check quota for a specific (key, model) pair."""
    if not api_key:
        print(f"  {label}/{model}: not configured")
        return

    resp = httpx.Client(transport=httpx.HTTPTransport(verify=False)).post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': 'hi'}],
            'max_tokens': 1,
        },
        timeout=15,
    )

    if resp.status_code == 429:
        status = 'RATE LIMITED (429)'
    elif resp.status_code != 200:
        status = f'HTTP {resp.status_code}: {resp.text[:100]}'
    else:
        status = 'OK'

    h = resp.headers
    rows = [
        ("Requests remaining today",   h.get('x-ratelimit-remaining-requests', 'n/a'),
                                       h.get('x-ratelimit-limit-requests', 'n/a')),
        ("Requests reset in",          h.get('x-ratelimit-reset-requests', 'n/a'), ''),
        ("Tokens remaining (per min)", h.get('x-ratelimit-remaining-tokens', 'n/a'),
                                       h.get('x-ratelimit-limit-tokens', 'n/a')),
        ("Tokens reset in",            h.get('x-ratelimit-reset-tokens', 'n/a'), ''),
    ]

    col_w = 30
    print(f"  {label} / {model}  [{status}]")
    for label_col, value, limit in rows:
        suffix = f"  (limit: {limit})" if limit else ''
        print(f"    {label_col:<{col_w}} {value}{suffix}")
    print()


def _all_keys() -> list[tuple[str, str]]:
    """Return list of (label, api_key) for all configured Groq keys."""
    keys = []
    if config.GROQ_API_KEY:
        keys.append(('groq_key_1', config.GROQ_API_KEY))
    if config.GROQ_API_KEY_2:
        keys.append(('groq_key_2', config.GROQ_API_KEY_2))
    return keys


if __name__ == '__main__':
    if not config.GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set in .env")
        sys.exit(1)

    # Parse flags
    args = sys.argv[1:]
    model_filter = None
    key_filter   = None

    if '--model' in args:
        idx = args.index('--model')
        if idx + 1 < len(args):
            model_filter = args[idx + 1]
        else:
            print("ERROR: --model requires a model name")
            sys.exit(1)

    if '--key' in args:
        idx = args.index('--key')
        if idx + 1 < len(args):
            key_filter = args[idx + 1]  # '1' or '2'
        else:
            print("ERROR: --key requires 1 or 2")
            sys.exit(1)

    keys   = _all_keys()
    models = list(dict.fromkeys(config.LLM_SCRAPING_MODELS + config.LLM_SCORING_MODELS))

    if model_filter:
        models = [model_filter]
    if key_filter:
        keys = [(l, k) for l, k in keys if l.endswith(key_filter)]
        if not keys:
            print(f"ERROR: groq_key_{key_filter} is not configured")
            sys.exit(1)

    print("=" * 70)
    print("GROQ API QUOTA CHECK")
    print("=" * 70)
    print()
    print("  NOTE: This shows per-minute tokens (TPM) and daily requests (RPD).")
    print("  Groq does NOT expose daily token (TPD) usage in API headers.")
    print("  For daily token budget status, check the /llm-usage dashboard.")
    print()

    for label, api_key in keys:
        for model in models:
            check_quota(label, api_key, model)
