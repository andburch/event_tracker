"""
Downtown Tempe events scraper.
Strategy:
  1. Selenium loads the JS-rendered /events listing page, collects event detail URLs.
  2. Selenium loads each detail page (corporate firewall blocks requests SSL).
  3. Parse dates from visible text — handles ranges like "January 24-25, 2026"
     and single dates like "November 9, 2025". Multi-day events → one row per day.
"""
import re
from bs4 import BeautifulSoup
from datetime import datetime
from scrapers.base_scraper import BaseScraper

BASE_URL = 'https://www.downtowntempe.com'
EVENTS_URL = f'{BASE_URL}/events'

# Slugs that are nav/utility pages, not actual events
_SKIP_SLUGS = {
    'volunteer', 'calendar', 'sponsorship', 'be-a-vendor',
    'vendor', 'sponsor', 'contact', 'about', 'map',
}

MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def _parse_time(time_str):
    """'10:00 AM' or '10 AM' → (hour, minute). Returns (12, 34) sentinel on failure."""
    if not time_str:
        return 12, 34
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)', time_str.strip(), re.IGNORECASE)
    if not m:
        return 12, 34
    hour, minute, period = int(m.group(1)), int(m.group(2) or 0), m.group(3).upper()
    if period == 'PM' and hour != 12:
        hour += 12
    if period == 'AM' and hour == 12:
        hour = 0
    return hour, minute


def _parse_dates_and_time(text):
    """
    Extract list of (datetime, hour, minute) tuples from visible page text.
    Each date range match is paired with the time that immediately follows it.
    Falls back to 12:34 sentinel when no time is found near a date.

    Handles:
      "January 24-25, 2026 10:00 AM - 5:00 PM"
      "December 4-6"   (year inferred)
      "November 9, 2025"
      "March 12-14, 2027"
    """
    now = datetime.now()

    # Match date ranges: "Month D-D, YYYY" or "Month D-D"
    range_pat = re.compile(
        r'\b(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+(\d{1,2})-(\d{1,2})'
        r'(?:,\s*(\d{4}))?',
        re.IGNORECASE,
    )
    # Match single dates: "Month D, YYYY" or "Month D"
    single_pat = re.compile(
        r'\b(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+(\d{1,2})(?:,\s*(\d{4}))?',
        re.IGNORECASE,
    )
    # Time pattern to search near each date match
    time_pat = re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:AM|PM))', re.IGNORECASE)

    def time_near(match_end):
        """Find first time within 60 chars after a date match."""
        snippet = text[match_end:match_end + 60]
        t = time_pat.search(snippet)
        return _parse_time(t.group(1)) if t else (12, 34)

    # Collect (datetime, seen_key) pairs, dedup by (month, day, year)
    seen = set()
    dates = []

    for m in range_pat.finditer(text):
        mon = MONTHS[m.group(1).lower()]
        start, end = int(m.group(2)), int(m.group(3))
        yr = int(m.group(4)) if m.group(4) else (now.year if mon >= now.month else now.year + 1)
        hour, minute = time_near(m.end())
        for day in range(start, end + 1):
            key = (yr, mon, day)
            if key in seen:
                continue
            seen.add(key)
            try:
                dates.append(datetime(yr, mon, day, hour, minute))
            except ValueError:
                pass

    if not dates:
        for m in single_pat.finditer(text):
            mon = MONTHS[m.group(1).lower()]
            day = int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else (now.year if mon >= now.month else now.year + 1)
            key = (yr, mon, day)
            if key in seen:
                continue
            seen.add(key)
            hour, minute = time_near(m.end())
            try:
                dates.append(datetime(yr, mon, day, hour, minute))
            except ValueError:
                pass

    return dates


class DowntownTempeScraper(BaseScraper):
    def __init__(self):
        super().__init__('downtown_tempe')

    def _get_event_links(self):
        """Selenium: load listing page, return list of detail URLs."""
        html = self.get_page_selenium(EVENTS_URL, wait_seconds=7)
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Normalise to absolute
            if href.startswith('/events/'):
                href = BASE_URL + href
            if not re.match(r'https?://www\.downtowntempe\.com/events/[^/]+$', href):
                continue
            slug = href.rstrip('/').split('/')[-1]
            if slug in _SKIP_SLUGS:
                continue
            links.add(href)
        return list(links)

    def _scrape_detail(self, url):
        """Selenium: load detail page, parse title + dates, return event dicts."""
        try:
            html = self.get_page_selenium(url, wait_seconds=5)
        except Exception as e:
            print(f"  [downtown_tempe] Selenium failed for {url}: {e}")
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Title from <title>, strip suffix
        raw_title = soup.title.string if soup.title else ''
        title = re.sub(r'\s*\|.*$', '', raw_title).strip()
        if not title:
            title = url.split('/')[-1].replace('-', ' ').title()

        # First substantial paragraph as description
        description = ''
        for p in soup.find_all('p'):
            txt = p.get_text(strip=True)
            if len(txt) > 60:
                description = txt[:500]
                break

        # Search full visible text for dates/times (nav/header pushes content down)
        visible = soup.get_text(separator=' ')
        dates = _parse_dates_and_time(visible)

        if not dates:
            print(f"  [downtown_tempe] No dates found: {url}")
            return []

        now = datetime.now()
        events = []
        for dt in dates:
            if dt < now:
                continue
            events.append(self.normalize_event({
                'title': title,
                'description': description,
                'venue': 'Downtown Tempe / Mill Avenue',
                'date': dt,
                'url': url,
                'category': 'festival',
            }))
        return events

    def scrape(self):
        print('[downtown_tempe] Loading events listing...')
        try:
            links = self._get_event_links()
        except Exception as e:
            print(f'[downtown_tempe] Failed to load listing: {e}')
            return []

        print(f'[downtown_tempe] Found {len(links)} event pages')
        events = []
        for url in links:
            detail = self._scrape_detail(url)
            events.extend(detail)
            print(f'  {url.split("/")[-1]} -> {len(detail)} event(s)')

        self.close_driver()
        print(f'[downtown_tempe] Total: {len(events)} future events')
        return events
