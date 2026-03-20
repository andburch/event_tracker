"""
Hale Theatre Arizona scraper
Scrapes season plays and concert series from static press release pages.

Both pages share this line structure:
  Title
  - (or "- Description text")
  Description text (may span multiple lines)
  Title (repeated)
  will run from / begins on / opens on / plays between
  Month Nth to/through Month Nth, Year.
"""
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}

DATE_VERB_RE = re.compile(
    r'^(will run from|will be playing from|begins on|opens on|plays between|playing on)$',
    re.IGNORECASE
)

# Matches "Month Nth to/through Month Nth, Year" or "Month Nth, Year"
DATE_LINE_RE = re.compile(
    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+(\d{1,2})(?:st|nd|rd|th)?'
    r'(?:[^.]*?(\d{4}))?',
    re.IGNORECASE
)

BOILERPLATE = {
    'press release', 'gilbert, az', 'season of', 'concert series',
    'skip to', 'search', 'share on', 'download', 'press packet',
    'for immediate release', 'hale centre theatre', 'hale concert hall',
    'embedded files', 'navigation', 'home', 'announcing',
}


class HaleTheatreScraper(BaseScraper):
    """Scrape shows from Hale Theatre Arizona press release pages"""

    def __init__(self):
        super().__init__('hale_theatre')
        self.sources = [
            {
                'url': 'https://press.haletheatrearizona.com/2025-2026-season-of-plays',
                'category': 'arts',
                'venue': 'Hale Centre Theatre, Gilbert',
            },
            {
                'url': 'https://press.haletheatrearizona.com/2026-concert-series',
                'category': 'music',
                'venue': 'Hale Concert Hall, Gilbert',
            },
        ]

    def scrape(self):
        events = []
        session = requests.Session()
        session.verify = False
        session.headers['User-Agent'] = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        for source in self.sources:
            try:
                print(f"Scraping Hale Theatre: {source['url']}")
                resp = session.get(source['url'], timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')
                text = soup.get_text(separator='\n')
                text = text.replace('\xa0', ' ').replace('\u200b', '')
                shows = self._parse_shows(text, source)
                events.extend(shows)
                print(f"  Found {len(shows)} shows")
            except Exception as e:
                print(f"  Error: {e}")
        print(f"Hale Theatre: collected {len(events)} events")
        return events

    def _is_boilerplate(self, line):
        low = line.lower()
        return any(bp in low for bp in BOILERPLATE) or len(line) < 4 or len(line) > 150

    def _parse_shows(self, text, source):
        """
        State machine over lines:
        1. Find a title line (non-boilerplate, followed by '-' or '- desc')
        2. Collect description lines
        3. Find date verb line ('will run from', 'begins on', etc.)
        4. Next line has the date: 'Month Nth to Month Nth, Year'
        """
        events = []
        lines = [l.strip() for l in text.split('\n')]

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for a title: non-boilerplate line followed by '-' or '- ...'
            if (line and not self._is_boilerplate(line) and
                    i + 1 < len(lines) and
                    (lines[i + 1] == '-' or lines[i + 1].startswith('- '))):

                title = line
                i += 1  # move to '-' line

                # Collect description lines until we hit a date verb or another title+dash
                desc_lines = []
                date_verb = None
                date_line = None

                while i < len(lines):
                    l = lines[i]

                    # Check for date verb
                    if DATE_VERB_RE.match(l):
                        date_verb = l
                        # Next non-empty line should be the date
                        i += 1
                        while i < len(lines) and not lines[i]:
                            i += 1
                        if i < len(lines):
                            date_line = lines[i]
                        break

                    # Check for inline date sentence (season plays format)
                    inline = re.search(
                        r'(?:will run from|will be playing from|begins on|opens on|plays between)'
                        r'\s+(January|February|March|April|May|June|July|August|'
                        r'September|October|November|December)\s+(\d{1,2})',
                        l, re.IGNORECASE
                    )
                    if inline:
                        date_line = l
                        break

                    # Stop if we hit the next show's title+dash pattern
                    if (l and not self._is_boilerplate(l) and
                            i + 1 < len(lines) and
                            (lines[i + 1] == '-' or lines[i + 1].startswith('- '))):
                        break

                    if l and l != '-' and not l.startswith('- '):
                        desc_lines.append(l)
                    elif l.startswith('- '):
                        desc_lines.append(l[2:])
                    i += 1

                if not date_line:
                    continue

                # Parse the date
                m = DATE_LINE_RE.search(date_line)
                if not m:
                    continue

                month = MONTH_MAP[m.group(1).lower()]
                day = int(m.group(2))
                year_str = m.group(3)
                year = int(year_str) if year_str else self._infer_year(month)

                try:
                    date = datetime(year, month, day, 19, 30)
                except Exception:
                    continue

                if date < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
                    i += 1
                    continue

                description = re.sub(r'\s+', ' ', ' '.join(desc_lines)).strip()
                # Remove repeated title from description
                if description.startswith(title):
                    description = description[len(title):].strip()
                description = description[:500]

                events.append(self.normalize_event({
                    'title': title,
                    'description': description,
                    'venue': source['venue'],
                    'date': date,
                    'url': source['url'],
                    'category': source['category'],
                }))
            else:
                i += 1

        return events

    def _infer_year(self, month):
        now = datetime.now()
        year = now.year
        if month < now.month:
            year += 1
        return year
