"""
Fibber Magees Pub scraper
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re

class FibberMageesScraper(BaseScraper):
    """Scrape Fibber Magees current events"""

    def __init__(self):
        super().__init__('fibbermagees')
        self.base_url = 'https://www.fibbermageespub.com/fibber-magees-events'

    def scrape(self):
        events = []
        try:
            response = self.get_page(self.base_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            articles = soup.find_all('article', class_=lambda x: x and 'eventlist-event' in x)
            print(f"Found {len(articles)} event articles")

            for article in articles[:60]:
                try:
                    # Title
                    title_elem = article.select_one('.eventlist-title')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    if len(title) < 3:
                        continue

                    # URL
                    link = article.select_one('a.eventlist-title-link, a[href]')
                    url = link['href'] if link else self.base_url
                    if url and not url.startswith('http'):
                        url = 'https://www.fibbermageespub.com' + url

                    # Date + time from .eventlist-meta
                    # Meta text looks like: "Saturday, March 14, 20268:30 PM11:30 PM..."
                    meta_elem = article.select_one('.eventlist-meta')
                    date = self._parse_meta_date(meta_elem.get_text(strip=True) if meta_elem else '')

                    # Description
                    desc_elem = article.select_one('.eventlist-description, [class*="excerpt"], p')
                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else title

                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': "Fibber Magee's Pub, Phoenix",
                        'date': date,
                        'url': url,
                        'category': 'music',
                    }))
                except Exception as e:
                    print(f"Error parsing event: {e}")
                    continue

        except Exception as e:
            print(f"Error scraping Fibber Magees: {e}")

        return events

    def _parse_meta_date(self, text):
        """
        Parse date+time from meta text like:
          'Saturday, March 14, 20268:30 PM11:30 PMGoogle CalendarICS'
        The year and time run together because there's no separator.
        """
        # Extract date: month day, year (year may be glued to time)
        date_match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            r'\s+(\d{1,2}),?\s+(\d{4})',
            text, re.IGNORECASE
        )
        # Extract first time occurrence: e.g. "8:30 PM" or "11:00 AM"
        # Use word boundary / non-digit lookbehind to avoid matching "20268:30"
        time_match = re.search(r'(?<!\d)([1-9]|1[0-2]):\d{2}\s*[AP]M', text, re.IGNORECASE)

        if date_match:
            month_str = date_match.group(1)
            day = int(date_match.group(2))
            year = int(date_match.group(3))
            hour, minute = 12, 34  # sentinel default

            if time_match:
                try:
                    t = datetime.strptime(time_match.group(0).strip(), '%I:%M %p')
                    hour, minute = t.hour, t.minute
                except ValueError:
                    pass

            try:
                return datetime(year, datetime.strptime(month_str, '%B').month, day, hour, minute)
            except ValueError:
                pass

        # Fallback: sentinel date
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
