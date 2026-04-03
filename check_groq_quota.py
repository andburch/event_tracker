"""
check_groq_quota.py — Show remaining Groq API quota from response headers.

Fires a minimal 1-token request and reads the rate limit headers Groq
returns on every response:

  x-ratelimit-remaining-requests  — Requests left today (RPD)
  x-ratelimit-remaining-tokens    — Tokens left this minute (TPM)
  x-ratelimit-limit-requests      — Your daily request cap
  x-ratelimit-limit-tokens        — Your per-minute token cap
  x-ratelimit-reset-requests      — Time until daily request limit resets
  x-ratelimit-reset-tokens        — Time until per-minute token limit resets

Usage:
    python check_groq_quota.py                    # Check both scraping and scoring models
    python check_groq_quota.py --model <name>     # Check specific model
"""

import sys
import httpx
import config

def check_quota(model: str):
    """Check quota for a specific model."""
    if not config.GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set in .env")
        sys.exit(1)

    print(f"Checking quota for: {model}")

    # Use a raw httpx call so we can inspect response headers directly.
    # The Groq SDK wraps the response and doesn't expose headers easily.
    transport = httpx.HTTPTransport(verify=False)  # Corporate SSL bypass
    with httpx.Client(transport=transport) as client:
        resp = client.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {config.GROQ_API_KEY}',
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
        print("  STATUS: Rate limited (429) — you've hit a cap.\n")
    elif resp.status_code != 200:
        print(f"  STATUS: HTTP {resp.status_code}")
        print(f"  {resp.text[:300]}\n")
        return
    else:
        print("  STATUS: OK")

    # Print rate limit headers in a readable table
    h = resp.headers
    rows = [
        ("Requests remaining today",  h.get('x-ratelimit-remaining-requests', 'n/a'),
                                      h.get('x-ratelimit-limit-requests', 'n/a')),
        ("Requests reset in",         h.get('x-ratelimit-reset-requests', 'n/a'), ''),
        ("Tokens remaining (per min)", h.get('x-ratelimit-remaining-tokens', 'n/a'),
                                       h.get('x-ratelimit-limit-tokens', 'n/a')),
        ("Tokens reset in",           h.get('x-ratelimit-reset-tokens', 'n/a'), ''),
    ]

    col_w = 30
    for label, value, limit in rows:
        suffix = f"  (limit: {limit})" if limit else ''
        print(f"    {label:<{col_w}} {value}{suffix}")

    print()


if __name__ == '__main__':
    # Parse optional --model flag
    if '--model' in sys.argv:
        idx = sys.argv.index('--model')
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]
            check_quota(model)
        else:
            print("ERROR: --model requires a model name")
            sys.exit(1)
    else:
        # Check both models used by the application
        print("="*70)
        print("GROQ API QUOTA CHECK")
        print("="*70)
        print()
        
        check_quota(config.LLM_SCRAPING_MODEL)
        
        # Only check scoring model if it's different
        if config.LLM_SCORING_MODEL != config.LLM_SCRAPING_MODEL:
            check_quota(config.LLM_SCORING_MODEL)
