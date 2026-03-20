"""
scrapers/base_scraper.py — Abstract base class for all event scrapers.

Every scraper in this project inherits from BaseScraper and implements scrape().
The base class provides:
  - get_page()          — Simple requests-based HTTP fetch (SSL verification disabled)
  - get_driver()        — Lazy-initialized Selenium WebDriver (headless Chrome)
  - get_page_selenium() — Fetch a URL via Selenium and return raw HTML
  - close_driver()      — Quit the Chrome process
  - normalize_event()   — Coerce a raw dict into the standard event schema
  - llm_scrape_page()   — LLM-based extraction with automatic pagination

SSL note: SSL verification is disabled throughout (requests + Selenium) because
the corporate network uses a self-signed certificate that Python's ssl module
rejects. This is intentional and expected.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import json
import re
import requests
import urllib3
import httpx
from groq import Groq
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import config

# Suppress the "InsecureRequestWarning: Unverified HTTPS request" noise that
# requests prints every time verify=False is used.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BaseScraper(ABC):
    """Abstract base class for all Phoenix Valley event scrapers."""

    def __init__(self, source_name: str):
        """
        Args:
            source_name: Short identifier for this scraper (e.g. 'mesa_gov').
                         Used as Event.source and in ScraperRun records.
        """
        self.source_name = source_name
        self._driver = None  # Lazily created on first call to get_driver()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def get_page(self, url: str, timeout: int = 10):
        """
        Fetch a URL with requests, SSL verification disabled.

        Use this for simple static pages that don't require JavaScript.
        For JS-heavy pages, use get_page_selenium() instead.

        Returns:
            requests.Response object
        """
        return requests.get(url, timeout=timeout, verify=False)

    # ------------------------------------------------------------------
    # Selenium helpers
    # ------------------------------------------------------------------

    def get_driver(self):
        """
        Return the shared Selenium WebDriver, creating it on first call.

        Driver is reused across multiple get_page_selenium() calls within
        a single scrape() invocation to avoid the overhead of launching
        Chrome repeatedly. Call close_driver() when done.

        ChromeDriver resolution order:
          1. chromedriver.exe in the project root (checked first — avoids
             network download behind corporate firewall)
          2. C:\\chromedriver\\chromedriver.exe
          3. chromedriver.exe anywhere on PATH
          4. webdriver-manager auto-download (will fail behind firewall)

        Chrome flags used:
          --headless                  No GUI window
          --no-sandbox                Required in some CI/container environments
          --disable-dev-shm-usage     Prevents crashes in low-memory environments
          --ignore-certificate-errors Corporate firewall SSL bypass
          --disable-gpu               Avoids GPU-related crashes in headless mode
          --window-size=1920,1080     Ensures full-width layout for scraping
          --disable-blink-features=AutomationControlled
                                      Reduces bot-detection fingerprint

        Returns:
            selenium.webdriver.Chrome instance
        """
        if self._driver is None:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--ignore-certificate-errors')  # Corporate firewall SSL bypass
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')

            # Forward proxy to Chrome if configured in .env
            if hasattr(config, 'HTTP_PROXY') and config.HTTP_PROXY:
                options.add_argument(f'--proxy-server={config.HTTP_PROXY}')

            try:
                # Prefer a locally placed chromedriver.exe to avoid network calls
                import os
                local_paths = [
                    os.path.join(os.getcwd(), 'chromedriver.exe'),
                    r'C:\chromedriver\chromedriver.exe',
                    'chromedriver.exe',  # Anywhere on PATH
                ]

                driver_path = None
                for path in local_paths:
                    if os.path.exists(path):
                        driver_path = path
                        print(f"Using local ChromeDriver: {path}")
                        break

                if driver_path:
                    service = Service(driver_path)
                    self._driver = webdriver.Chrome(service=service, options=options)
                else:
                    # Fall back to webdriver-manager (requires internet access)
                    print("No local ChromeDriver found, attempting download...")
                    print("If this fails, run: python setup_chromedriver.py")
                    service = Service(ChromeDriverManager().install())
                    self._driver = webdriver.Chrome(service=service, options=options)

                # Global page-load timeout — prevents hanging on slow/broken pages
                self._driver.set_page_load_timeout(30)

            except Exception as e:
                print(f"Failed to initialize Chrome driver: {e}")
                print("\n  ChromeDriver not found!")
                print("Run this command for instructions:")
                print("  python setup_chromedriver.py")
                raise

        return self._driver

    def get_page_selenium(self, url: str, wait_seconds: int = 3) -> str:
        """
        Navigate to a URL with Selenium and return the rendered HTML.

        Waits `wait_seconds` after page load to allow JavaScript to finish
        rendering. Increase this for pages with heavy async content.

        Handles TimeoutException gracefully — if the page load times out
        (e.g. a slow CDN asset), we continue with whatever HTML was loaded
        rather than crashing the entire scrape.

        Args:
            url:          Full URL to fetch.
            wait_seconds: Seconds to sleep after navigation for JS rendering.

        Returns:
            Page HTML as a string (driver.page_source).
        """
        from selenium.common.exceptions import TimeoutException
        driver = self.get_driver()
        driver.set_page_load_timeout(30)
        try:
            driver.get(url)
        except TimeoutException:
            # Page timed out but partial HTML may still be usable
            print(f"  Page load timeout for {url}, continuing with partial content...")
        time.sleep(wait_seconds)  # Let JavaScript finish rendering
        return driver.page_source

    def close_driver(self):
        """
        Quit the Chrome process and release the driver reference.

        Called automatically by __del__ but can also be called explicitly
        at the end of scrape() to free resources sooner.
        """
        if self._driver:
            self._driver.quit()
            self._driver = None

    def __del__(self):
        """Ensure Chrome is cleaned up when the scraper object is garbage-collected."""
        self.close_driver()

    # ------------------------------------------------------------------
    # LLM-based scraping
    # ------------------------------------------------------------------

    # Shared Groq client (one per process, SSL verification disabled for firewall)
    _groq_client = None

    @classmethod
    def _get_groq_client(cls):
        if cls._groq_client is None:
            transport = httpx.HTTPTransport(verify=False)
            cls._groq_client = Groq(
                api_key=config.GROQ_API_KEY,
                http_client=httpx.Client(transport=transport, timeout=60),
            )
        return cls._groq_client

    # JSON schema for the LLM response
    _LLM_EVENT_SCHEMA = {
        'type': 'json_schema',
        'json_schema': {
            'name': 'events_page',
            'strict': False,
            'schema': {
                'type': 'object',
                'properties': {
                    'events': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'title':       {'type': 'string'},
                                'date':        {'type': 'string'},
                                'time':        {'type': ['string', 'null']},
                                'description': {'type': ['string', 'null']},
                                'venue':       {'type': ['string', 'null']},
                                'url':         {'type': ['string', 'null']},
                            },
                            'required': ['title', 'date', 'time', 'description', 'venue', 'url'],
                        }
                    },
                    'next_page_url': {'type': ['string', 'null']},
                },
                'required': ['events', 'next_page_url'],
            }
        }
    }

    @staticmethod
    def _clean_html_for_llm(html, char_limit=8000):
        """
        Strip HTML to readable text with inlined hrefs for LLM consumption.

        Links are rendered as "Link Text [/url]" so the LLM can identify
        pagination URLs without needing to parse raw HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'img']):
            tag.decompose()
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if href and not href.startswith('#') and not href.startswith('javascript'):
                a.string = f"{a.get_text(strip=True)} [{href}]"
        main = soup.find('main') or soup.find('body')
        text = (main or soup).get_text(separator='\n', strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text[:char_limit]

    def _ask_llm(self, text, current_url, site_hint='', retries=3):
        """
        Send page text to kimi-k2 and return parsed JSON with events + next_page_url.

        Retries up to `retries` times on 503 overload errors with backoff.
        """
        prompt = (
            f"The following is text scraped from an events page"
            f"{' (' + site_hint + ')' if site_hint else ''}.\n"
            f"Current page URL: {current_url}\n\n"
            "1. Extract ALL upcoming events into the 'events' array.\n"
            "   Each event: title, date (e.g. 'March 22, 2026'), time (e.g. '8:00 PM' or null),\n"
            "   description (or null), venue (or null), url (full absolute URL or null).\n\n"
            "2. Find the NEXT PAGE URL and put it in 'next_page_url'.\n"
            "   Look for: numbered page links, 'Next' or '>' buttons, 'Load More' links,\n"
            "   or URL patterns like ?page=2. Return the full absolute URL.\n"
            "   If there is no next page, return null.\n"
            "   Links appear as 'Link Text [/path/or/url]' -- use those URLs.\n\n"
            f"PAGE TEXT:\n{text}"
        )
        client = self._get_groq_client()
        for attempt in range(retries):
            try:
                response = client.chat.completions.create(
                    model='moonshotai/kimi-k2-instruct-0905',
                    messages=[{'role': 'user', 'content': prompt}],
                    temperature=0.1,
                    response_format=self._LLM_EVENT_SCHEMA,
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                if '503' in str(e) and attempt < retries - 1:
                    wait = 15 * (attempt + 1)
                    print(f"    503 overloaded, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def _parse_llm_date(self, date_str, time_str):
        """
        Convert LLM-returned date/time strings to a datetime object.

        Tries several common formats. Falls back to the 12:34 sentinel time
        on the current date if parsing fails entirely.

        Args:
            date_str: e.g. 'March 22, 2026' or '2026-03-22'
            time_str: e.g. '8:00 PM' or None

        Returns:
            datetime
        """
        if not date_str:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

        # Combine date + time for parsing
        combined = date_str.strip()
        if time_str:
            combined = f"{combined} {time_str.strip()}"

        formats = [
            '%B %d, %Y %I:%M %p',   # March 22, 2026 8:00 PM
            '%B %d, %Y %I:%M%p',    # March 22, 2026 8:00PM
            '%B %d, %Y',            # March 22, 2026
            '%b %d, %Y %I:%M %p',   # Mar 22, 2026 8:00 PM
            '%b %d, %Y',            # Mar 22, 2026
            '%Y-%m-%d %I:%M %p',    # 2026-03-22 8:00 PM
            '%Y-%m-%d',             # 2026-03-22
            '%m/%d/%Y',             # 03/22/2026
        ]
        for fmt in formats:
            try:
                return datetime.strptime(combined, fmt)
            except ValueError:
                continue

        # Fallback: try just the date part with sentinel time
        for fmt in ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(hour=12, minute=34)
            except ValueError:
                continue

        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

    def llm_scrape_page(self, start_url, use_selenium=False, wait=5,
                        max_pages=3, category='general', default_venue='',
                        site_hint=''):
        """
        Fetch one or more pages and use the LLM to extract events + pagination.

        This is the primary method for LLM-based scrapers. It handles:
          - Fetching via requests or Selenium
          - Cleaning HTML for LLM consumption
          - Calling kimi-k2 with json_schema response format
          - Following next_page_url across pages (with visited-URL guard)
          - Parsing LLM date/time strings into datetime objects
          - Normalizing results into the standard event schema

        Args:
            start_url:     First URL to fetch.
            use_selenium:  True to use Selenium (JS-heavy pages), False for requests.
            wait:          Seconds to wait after Selenium page load.
            max_pages:     Maximum pages to follow before stopping.
            category:      Event category string for normalize_event().
            default_venue: Fallback venue name if LLM returns null.
            site_hint:     Short label passed to the LLM prompt for context.

        Returns:
            List of normalized event dicts (same format as normalize_event()).
        """
        all_events = []
        current_url = start_url
        visited = set()
        page_num = 0

        while current_url and page_num < max_pages:
            page_num += 1
            if current_url in visited:
                print(f"  Page {page_num}: loop detected, stopping")
                break
            visited.add(current_url)

            print(f"  Page {page_num}: {current_url[:80]}")
            try:
                if use_selenium:
                    html = self.get_page_selenium(current_url, wait_seconds=wait)
                else:
                    resp = self.get_page(current_url)
                    html = resp.text
            except Exception as e:
                print(f"    fetch error: {e}")
                break

            text = self._clean_html_for_llm(html)
            print(f"    text={len(text)} chars", end='  ')

            try:
                result = self._ask_llm(text, current_url=current_url, site_hint=site_hint)
            except Exception as e:
                print(f"\n    LLM error: {e}")
                break

            page_events = result.get('events', [])
            next_url = result.get('next_page_url')
            print(f"events={len(page_events)}  next={next_url or 'null'}")

            for ev in page_events:
                dt = self._parse_llm_date(ev.get('date'), ev.get('time'))
                url = ev.get('url') or ''
                # Make relative URLs absolute using the start domain
                if url and not url.startswith('http'):
                    from urllib.parse import urljoin
                    url = urljoin(start_url, url)
                all_events.append(self.normalize_event({
                    'title':       ev.get('title', ''),
                    'description': ev.get('description') or '',
                    'venue':       ev.get('venue') or default_venue,
                    'date':        dt,
                    'url':         url,
                    'category':    category,
                }))

            # Validate next URL before following
            if next_url and not next_url.startswith('http'):
                print(f"    next_page_url not absolute, stopping")
                break
            current_url = next_url

            if current_url:
                time.sleep(2)  # Polite delay between pages

        return all_events

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self) -> list:
        """
        Fetch and parse events from the source.

        Must be implemented by every subclass.

        Returns:
            List of event dicts. Each dict should contain at minimum:
              title       (str)      — Event name
              date        (datetime) — Start date/time
              url         (str)      — Link to event detail page
            Optional keys:
              description (str)
              venue       (str)
              category    (str)      — e.g. 'music', 'family', 'arts'
              price       (str)      — e.g. 'Free', '$10'

            Pass each dict through normalize_event() before returning.
        """
        pass

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_event(self, raw_event: dict) -> dict:
        """
        Coerce a raw event dict into the standard schema expected by scraper_runner.

        Strips whitespace from string fields and fills in defaults for missing
        optional fields. The `source` field is always set to self.source_name
        regardless of what the raw dict contains.

        Args:
            raw_event: Dict with any subset of the event fields.

        Returns:
            Normalized dict with keys: title, description, venue, date,
            url, source, category.
        """
        return {
            'title':       raw_event.get('title', '').strip(),
            'description': raw_event.get('description', '').strip(),
            'venue':       raw_event.get('venue', '').strip(),
            'date':        raw_event.get('date'),
            'url':         raw_event.get('url', '').strip(),
            'source':      self.source_name,
            'category':    raw_event.get('category', 'general'),
        }
