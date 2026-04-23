"""
debug/utils.py -- Shared helpers for all debug/*.py scripts.

Not run directly -- imported only.

Provides:
  1. Bootstrap  -- path setup + .env loading
  2. Source     -- SITES lookup with clean error messages
  3. Artifacts  -- save/load files in /tmp/debug/{source}/
  4. Formatting -- banner(), step(), fmt_size(), fmt_time(), estimate_tokens()
  5. Validation -- JS placeholder detection, date-parse debugging
"""

import os, sys, re, time

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Artifacts go inside the project directory so they persist across Docker runs.
# The project root is mounted as .:/app in docker-compose, so this survives container restarts.
DEBUG_DIR    = os.path.join(PROJECT_ROOT, 'debug_artifacts')

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def bootstrap():
    """Load .env and make the project importable. Call once before any project imports."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))


# ── Source lookup ──────────────────────────────────────────────────────────────

def get_source(key: str) -> tuple:
    """
    Return the SITES tuple for key. Prints valid keys and exits on unknown key.

    Tuple layout: (name, url, use_selenium, wait, max_pages, note, color, pagination_config)
    """
    from sources import SITES
    if key not in SITES:
        print(f'Unknown source key: {key}')
        print(f'Valid keys: {", ".join(sorted(SITES))}')
        sys.exit(1)
    return SITES[key]


def list_sources():
    """Print all source keys with fetch mode and URL."""
    from sources import SITES
    print(f'\n{"KEY":<22} {"FETCH":<10} {"PAGES":<6} URL')
    print('─' * 80)
    for k, entry in SITES.items():
        name, url, use_sel, wait, max_pages, note, _color, _pag = entry
        sel = 'selenium' if use_sel else 'requests'
        flag = f'  [{note}]' if note else ''
        print(f'  {k:<20} {sel:<10} {max_pages:<6} {url[:55]}{flag}')


# ── Artifact I/O ───────────────────────────────────────────────────────────────
#
# Filename conventions:
#   page_1_raw.html              -- raw HTML (1-indexed pages)
#   page_1_cleaned.txt           -- text after clean_html()
#   page_1_chunk_1.txt           -- chunk N of cleaned text
#   page_1_chunk_1_prompt.txt    -- full prompt sent to LLM
#   page_1_chunk_1_response.json -- raw LLM response

def _ensure_debug_dir(source: str) -> str:
    path = os.path.join(DEBUG_DIR, source)
    os.makedirs(path, exist_ok=True)
    return path


def save_artifact(source: str, filename: str, content: str) -> str:
    """Write content to /tmp/debug/{source}/{filename} and return the full path."""
    dirpath = _ensure_debug_dir(source)
    filepath = os.path.join(dirpath, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


def load_artifact(source: str, filename: str) -> str:
    """
    Load /tmp/debug/{source}/{filename}.
    Exits with a clear error if the file doesn't exist.
    """
    filepath = os.path.join(DEBUG_DIR, source, filename)
    if not os.path.exists(filepath):
        print(f'Artifact not found: {filepath}')
        print(f'Run the earlier pipeline stage first to generate it.')
        sys.exit(1)
    with open(filepath) as f:
        return f.read()


def artifact_path(source: str, filename: str) -> str:
    return os.path.join(DEBUG_DIR, source, filename)


def artifact_exists(source: str, filename: str) -> bool:
    return os.path.exists(artifact_path(source, filename))


# ── Output formatting ──────────────────────────────────────────────────────────
#
# Consistent output across all debug scripts:
#
#   ============================================================
#     SECTION HEADER
#   ============================================================
#   [+] FETCH        185.4K chars (3.2s)       <- OK
#   [!] CLEAN        empty text                 <- FAIL
#   [~] LLM          0 events returned          <- WARN
#   [-] CHUNK        skipped (--from llm)       <- SKIP

ICONS = {'OK': '+', 'FAIL': '!', 'WARN': '~', 'SKIP': '-', 'INFO': ' '}


def banner(text: str):
    """Print a bold section separator."""
    print(f'\n{"=" * 60}')
    print(f'  {text}')
    print(f'{"=" * 60}')


def step(name: str, status: str, detail: str = ''):
    """Print a formatted step line. status: OK | FAIL | WARN | SKIP | INFO"""
    icon = ICONS.get(status, '?')
    print(f'  [{icon}] {name:<14} {detail}')


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~2.2 chars per token for English prose."""
    return int(len(text) / 2.2)


def fmt_size(chars: int) -> str:
    """Format a character count: 185420 -> '185.4K chars'"""
    if chars >= 1_000_000:
        return f'{chars / 1_000_000:.1f}M chars'
    if chars >= 1_000:
        return f'{chars / 1_000:.1f}K chars'
    return f'{chars} chars'


def fmt_time(seconds: float) -> str:
    """Format a duration: 83.5 -> '1m 23.5s'"""
    if seconds >= 60:
        m = int(seconds // 60)
        s = seconds % 60
        return f'{m}m {s:.1f}s'
    return f'{seconds:.1f}s'


def fmt_pct(a: int, b: int) -> str:
    if b == 0:
        return 'n/a'
    return f'{a * 100 // b}%'


# ── Selenium prereq check ──────────────────────────────────────────────────────

def check_selenium_available() -> bool:
    """
    Verify Chrome and chromedriver are installed before attempting Selenium fetches.
    Returns True if both found; prints install hint and returns False if missing.
    """
    import shutil
    chrome = (shutil.which('chromium-browser')
              or shutil.which('chromium')
              or shutil.which('google-chrome'))
    driver = shutil.which('chromedriver')
    ok = True
    if not chrome:
        step('PREREQ', 'FAIL', 'Chrome/Chromium not found — install: apt install chromium-browser')
        ok = False
    if not driver:
        step('PREREQ', 'FAIL', 'chromedriver not found — install: apt install chromium-chromedriver')
        ok = False
    return ok


# ── JS placeholder / empty text detection ─────────────────────────────────────
#
# The most common cause of "0 events" is Selenium not waiting long enough for
# JS to render. The page loads but shows a spinner instead of event data.
# We catch this before the LLM call to avoid burning API quota on empty pages.

_JS_PLACEHOLDERS = [
    'loading events',
    'loading...',
    'please wait',
    'javascript is required',
    'enable javascript',
    'calendar is loading',
    'fetching events',
    'events are loading',
]


def check_empty_or_placeholder(text: str) -> list[str]:
    """
    Check cleaned text for JS rendering issues.
    Returns list of warning strings; empty list = no problems.
    """
    warnings = []
    if not text or not text.strip():
        warnings.append('Cleaned text is EMPTY — Selenium may not have waited long enough. Try --wait 20.')
        return warnings
    stripped = text.strip()
    if len(stripped) < 100:
        warnings.append(f'Cleaned text is very short ({len(stripped)} chars) — page may not have loaded.')
    lower = stripped.lower()
    for pat in _JS_PLACEHOLDERS:
        if pat in lower:
            warnings.append(f'Found JS placeholder: "{pat}" — page content still rendering. Try --wait 20.')
    return warnings


# ── Date-parse debugging ───────────────────────────────────────────────────────
#
# Mirrors the exact logic in llm_scraper.parse_date() so debug scripts show
# which events would be silently dropped in production.

def parse_date_debug(date_str: str | None, time_str: str | None = None) -> tuple[bool, str]:
    """
    Try to parse a date string using the same logic as production.

    Returns (success: bool, result_str: str).
    success=False means the event would get the sentinel date (12:34) in production,
    which means it would either appear with wrong date or be filtered as past.
    """
    from datetime import datetime
    if not date_str:
        return False, 'missing date — sentinel time will be used'

    date_str = date_str.strip()

    # Primary: YYYY-MM-DD
    try:
        if time_str:
            time_str = time_str.split('-')[0].strip()
            time_str = re.sub(r'\s*p\.m\.', ' PM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'\s*a\.m\.', ' AM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'(\d)(am|pm)$', lambda m: m.group(1) + ' ' + m.group(2).upper(), time_str, flags=re.IGNORECASE)
            combined = f'{date_str} {time_str}'
            for fmt in ['%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %H:%M']:
                try:
                    dt = datetime.strptime(combined, fmt)
                    return True, dt.strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    continue
        dt = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12, minute=34)
        return True, dt.strftime('%Y-%m-%d 12:34 (no time)')
    except ValueError:
        pass

    # Legacy formats
    for fmt in ['%B %d, %Y', '%b %d, %Y', '%A, %B %d, %Y', '%A, %b %d, %Y', '%m/%d/%Y']:
        try:
            dt = datetime.strptime(date_str, fmt).replace(hour=12, minute=34)
            return True, dt.strftime(f'%Y-%m-%d (legacy fmt {fmt})')
        except ValueError:
            continue

    return False, f'UNPARSEABLE: "{date_str}" — event will use sentinel date in production'


# ── Interactive prompt ─────────────────────────────────────────────────────────

def ask(prompt: str, options: str = 'y/n') -> str:
    """Prompt user for input. Returns lowercased response."""
    try:
        resp = input(f'\n  >> {prompt} [{options}] ').strip().lower()
        return resp or 'y'
    except (EOFError, KeyboardInterrupt):
        print()
        return 'n'
