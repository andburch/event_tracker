"""
llm_scrape_core.py -- Shared core for LLM-based event extraction

Contains all fetch, clean, chunk, and LLM-call logic used by both:
  - _test_llm_scrape.py  (CLI test harness, prints results, no DB writes)
  - llm_scraper.py       (production runner, saves to DB, runs scoring)

HOW IT WORKS
------------
Traditional scrapers require custom CSS selectors per site, which break
whenever a site redesigns. This module takes a different approach:

  1. Fetch the page HTML (via requests or Selenium for JS-heavy sites)
  2. Strip HTML down to clean readable text, with hyperlinks inlined as
     "Link Text [/url]" so the LLM can see pagination URLs
  3. Send that text to the LLM with a structured JSON schema, asking it
     to extract events AND find the next page URL
  4. Follow next_page_url across pages until null or max_pages reached

Because the LLM reads plain text rather than HTML structure, this works on
virtually any events page regardless of how it's built.

KNOWN LIMITATIONS
-----------------
  - Bot detection (Akamai/Cloudflare): fetch returns "Access Denied" instead
    of real content. Mitigated with CDP user-agent spoofing + fresh sessions.
  - 503/429 errors from Groq: quota exhaustion; handled with retry+backoff.
  - Pages requiring login or special cookies are not supported.
"""

import re, json, time, httpx, os, requests, urllib3, logging, threading
from bs4 import BeautifulSoup
from groq import Groq
import config
from sources import SITES

# Configure logging
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq client (lazy singleton)
# ---------------------------------------------------------------------------
# Instantiated on first use rather than at import time so that a missing
# GROQ_API_KEY doesn't crash every file that imports this module.
_client = None


def _get_client() -> Groq:
    """Return the shared Groq client, creating it on first call."""
    global _client
    if _client is None:
        transport = httpx.HTTPTransport(verify=False)  # Corporate firewall SSL bypass
        _client = Groq(
            api_key=config.GROQ_API_KEY,
            http_client=httpx.Client(transport=transport, timeout=60),
        )
    return _client

# ---------------------------------------------------------------------------
# Model + schema
# ---------------------------------------------------------------------------
# llama-3.3-70b-versatile: Better output quality, higher TPM (12k vs 6k),
#   but lower RPD (1k vs 14.4k). Used for all scraping.
_MODEL = 'llama-3.3-70b-versatile'

EVENT_SCHEMA = {'type': 'json_object'}

# ---------------------------------------------------------------------------
# User-agent spoofing
# ---------------------------------------------------------------------------
# Akamai-protected sites check User-Agent and block obvious headless strings.
# Combined with CDP setUserAgentOverride (patches JS navigator.userAgent too),
# this bypasses most UA-based bot detection.
_SPOOF_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)

# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def clean_html(html: str) -> str:
    """
    Convert raw HTML into clean plain text suitable for LLM consumption.

    No truncation applied -- ask_llm() handles chunking for large pages.

    Steps:
      1. Remove non-content tags (scripts, styles, nav, footer, etc.)
      2. Inline hyperlinks as "Link Text [/url]" for pagination URL visibility
      3. Extract text from <main> or <body>, collapsing excess whitespace
      4. Remove repetitive content patterns (Google Calendar, ICS links)

    Args:
        html: Raw HTML string

    Returns:
        Clean text string (full, untruncated)
    """
    soup = BeautifulSoup(html, 'html.parser')

    for tag in soup(['script', 'style', 'nav', 'footer', 'header',
                     'noscript', 'svg', 'img']):
        tag.decompose()

    # Inline hrefs so the LLM can see pagination URLs
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href and not href.startswith('#') and not href.startswith('javascript'):
            a.string = f"{a.get_text(strip=True)} [{href}]"

    main = soup.find('main') or soup.find('body')
    text = (main or soup).get_text(separator='\n', strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove repetitive content patterns that bloat the text
    # Remove Google Calendar and ICS export links (they're not events)
    text = re.sub(r'Google Calendar \[http://www\.google\.com/calendar/event\?[^\]]+\]', '', text)
    text = re.sub(r'ICS \[/[^\]]+\?format=ical\]', '', text)
    
    # Clean up extra whitespace after removals
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text

# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str):
    """
    Split text into overlapping windows for multi-call extraction.

    Args:
        text: Full text to chunk

    Yields:
        Tuples of (chunk_str, is_last)
    """
    chunk_size = config.LLM_CHUNK_SIZE
    chunk_overlap = config.LLM_CHUNK_OVERLAP
    step  = chunk_size - chunk_overlap
    total = len(text)
    start = 0
    while start < total:
        end = min(start + chunk_size, total)
        yield text[start:end], (end >= total)
        if end >= total:
            break
        start += step

# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def _ask_llm_single(
    text: str,
    current_url: str,
    site_hint: str = '',
    is_last_chunk: bool = True,
    retries: int = None
) -> dict:
    """
    Single LLM call for one chunk of page text.

    Args:
        text: Cleaned text chunk
        current_url: URL of the page (for context in prompt)
        site_hint: Short label like "Gilbert Gov"
        is_last_chunk: If False, skip pagination search (links only in last chunk)
        retries: Max retry attempts on 503/429 errors (defaults to config.LLM_MAX_RETRIES)

    Returns:
        Dict with 'events' list and 'next_page_url' (str or None)
    """
    if retries is None:
        retries = config.LLM_MAX_RETRIES
    
    if is_last_chunk:
        pagination_instruction = (
            "2. Find the NEXT PAGE URL and put it in 'next_page_url'.\n"
            "   Look for: numbered page links, 'Next' or '>' buttons, 'Load More' links,\n"
            "   or URL patterns like ?page=2. Return the full absolute URL.\n"
            "   If there is no next page, return null.\n"
            "   Links appear as 'Link Text [/path/or/url]' -- use those URLs.\n\n"
        )
    else:
        pagination_instruction = (
            "2. Set 'next_page_url' to null -- pagination is handled separately.\n\n"
        )

    prompt = (
        f"The following is text scraped from an events page"
        f"{' (' + site_hint + ')' if site_hint else ''}.\n"
        f"Current page URL: {current_url}\n\n"
        "1. Extract ALL upcoming events into the 'events' array.\n"
        "   Each event must have these exact keys:\n"
        "     title       (string)\n"
        "     date        (string, MUST be in YYYY-MM-DD format, e.g. '2026-03-22'. If a date range like 'Oct 17, 2025 - Apr 25, 2026', use the START date)\n"
        "     end_date    (string, YYYY-MM-DD format, or null. Only set if the event is a date range e.g. 'Oct 17, 2025 - Apr 25, 2026' -> '2026-04-25')\n"
        "     time        (string e.g. '8:00 PM', or null. Convert formats like '1:30pm' to '1:30 PM')\n"
        "     description (string or null)\n"
        "     venue       (string or null)\n"
        "     url         (full absolute URL to event detail page, or null. COPY the URL exactly as it appears in the text - do NOT paraphrase or modify it)\n"
        "   IMPORTANT: Times often appear on a separate line after the date, or in formats like\n"
        "   'Mar 20 @ 9:00 am - 5:00 pm' or '9:00 am - 4:00 pm' on the next line after the date.\n"
        "   Always capture the start time if present. Use 12-hour format e.g. '9:00 AM'.\n"
        "   CRITICAL: Date MUST be in YYYY-MM-DD format (e.g. '2026-03-22'), not text format. For date ranges, use the start date.\n"
        "   CRITICAL: For calendar grid layouts, the month is shown at the top of the page. Day numbers in the grid belong to THAT month unless clearly labeled otherwise.\n\n"
        + pagination_instruction
        + "Respond with ONLY valid JSON in this exact format, no markdown, no explanation:\n"
        '{"events": [...], "next_page_url": "..." or null}\n'
        'Return your response as json only.\n\n'
        f"PAGE TEXT:\n{text}"
    )

    for attempt in range(retries):
        try:
            response = _get_client().chat.completions.create(
                model=_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                response_format=EVENT_SCHEMA,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            err = str(e)
            if ('503' in err or '429' in err) and attempt < retries - 1:
                wait = config.LLM_RETRY_BASE_DELAY * (attempt + 1)
                log.warning(f"{'503' if '503' in err else '429'} error, retrying in {wait}s...")
                print(f"\n    {'503' if '503' in err else '429'} error, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def ask_llm(text: str, current_url: str, site_hint: str = '', retries: int = None) -> dict:
    """
    Extract events from page text, chunking automatically for large pages.

    Single call for pages <= config.LLM_CHUNK_SIZE chars. For larger pages, splits into
    overlapping chunks, merges results, and deduplicates by title.

    Args:
        text: Full cleaned page text from clean_html()
        current_url: URL of the page being parsed
        site_hint: Short label for the LLM prompt
        retries: Passed through to each single-chunk call (defaults to config.LLM_MAX_RETRIES)

    Returns:
        Dict with 'events' (deduplicated list) and 'next_page_url' (str or None)
    """
    if retries is None:
        retries = config.LLM_MAX_RETRIES
    
    if len(text) <= config.LLM_CHUNK_SIZE:
        return _ask_llm_single(text, current_url, site_hint,
                               is_last_chunk=True, retries=retries)

    chunks = list(_chunk_text(text))
    n = len(chunks)
    log.info(f"Large page: {len(text)} chars -> {n} chunks")
    print(f"\n    large page: {len(text)} chars -> {n} chunks", end='  ')

    all_events  = []
    seen_titles = set()
    next_page_url = None

    for i, (chunk, is_last) in enumerate(chunks):
        if i > 0:
            time.sleep(config.LLM_CHUNK_DELAY)
        result = _ask_llm_single(chunk, current_url, site_hint,
                                 is_last_chunk=is_last, retries=retries)

        for ev in result.get('events', []):
            key = (ev.get('title') or '').strip().lower()
            if key and key not in seen_titles:
                seen_titles.add(key)
                all_events.append(ev)

        if is_last:
            next_page_url = result.get('next_page_url')

    return {'events': all_events, 'next_page_url': next_page_url}

# ---------------------------------------------------------------------------
# Page fetchers
# ---------------------------------------------------------------------------

def fetch_requests(url: str) -> str:
    """
    Fetch a static HTML page using requests (no JavaScript execution).

    SSL verification disabled for corporate firewall compatibility.
    
    Args:
        url: URL to fetch
    
    Returns:
        HTML content as string
    """
    urllib3.disable_warnings()
    r = requests.get(url, timeout=15, verify=False,
                     headers={'User-Agent': _SPOOF_UA})
    return r.text


# Module-level Selenium driver -- reused within a single site's page loop,
# closed and reopened between sites via fetch_selenium.
# Thread safety: Protected by a lock to prevent concurrent access
_selenium_driver = None
_driver_lock = threading.Lock()


def get_driver():
    """
    Create (or return existing) headless Chrome WebDriver.

    Uses local chromedriver.exe in project root to avoid network downloads
    behind the corporate firewall.
    
    Thread-safe: Uses a lock to prevent concurrent driver creation.
    """
    global _selenium_driver
    with _driver_lock:
        if _selenium_driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            service = Service(os.path.join(os.getcwd(), 'chromedriver.exe'))
            _selenium_driver = webdriver.Chrome(service=service, options=options)
            _selenium_driver.set_page_load_timeout(30)
            log.info("Created new Selenium WebDriver instance")
        return _selenium_driver


def close_driver():
    """
    Quit Chrome and release the driver reference.
    
    Thread-safe: Uses a lock to prevent concurrent access.
    """
    global _selenium_driver
    with _driver_lock:
        if _selenium_driver:
            _selenium_driver.quit()
            _selenium_driver = None
            log.info("Closed Selenium WebDriver")


def fetch_selenium(url: str, wait: int = 6, scroll_passes: int = 10) -> str:
    """
    Fetch a URL using Selenium with CDP user-agent spoofing.

    Closes and reopens the driver between sites to reset Akamai session state.
    CDP override patches both the HTTP User-Agent header and JS navigator.userAgent.

    Args:
        url: URL to fetch
        wait: Seconds to sleep after page load for JS rendering
        scroll_passes: Number of times to scroll to bottom (for lazy-loading pages)

    Returns:
        Page HTML string
    """
    close_driver()
    driver = get_driver()

    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        'userAgent': _SPOOF_UA,
        'acceptLanguage': 'en-US,en;q=0.9',
        'platform': 'Win32',
    })

    try:
        driver.get(url)
    except Exception as e:
        # TimeoutException on slow pages -- partial HTML is still useful
        # Log the error but continue with whatever HTML was loaded
        log.warning(f"Page load timeout/error (continuing with partial HTML): {type(e).__name__}")
        print(f"    Page load timeout/error (continuing with partial HTML): {type(e).__name__}")

    time.sleep(wait)

    # Scroll repeatedly to trigger lazy-loading
    last_height = 0
    for _ in range(scroll_passes):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break  # No new content loaded
        last_height = new_height

    return driver.page_source

# SITES is defined in sources.py -- import at top of file.
