"""
ASU Kerr Cultural Center events scraper
Scrapes events from asukerr.com/events/
Uses The Events Calendar (WordPress) - clean article structure
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time
import unicodedata


class ASUKerrScraper(BaseScraper):
    """Scrape events from ASU Kerr Cultural Center"""

    def __init__(self):
        super().__init__('asu_kerr')
        self.events_url = 'https://asukerr.com/events/'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping ASU Kerr...")
            driver = self.get_driver()
            driver.set_page_load_timeout(20)
            try:
                driver.get(self.events_url)
            except Exception:
                pass
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            articles = soup.find_all('article', class_=lambda c: c and 'tribe-events' in str(c))
            print(f"  Found {len(articles)} events")

            for article in articles:
                try:
                    link_el = article.find('a', class_='tribe-events-calendar-list__event-title-link')
                    if not link_el:
                        continue
                    url = link_el.get('href', '')
                    if url in seen:
                        continue
                    seen.add(url)

                    title = link_el.get_text(strip=True)
                    if not title:
                        continue

                    # Date from <time datetime="2026-03-25"> + span text "March 25 @ 7:30 pm"
                    time_el = article.find('time')
                    date = datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
                    if time_el:
                        date_str = time_el.get('datetime', '')
                        span = article.find('span', class_='tribe-event-date-start')
                        span_text = span.get_text(strip=True) if span else ''
                        date = self._parse_date(date_str, span_text)

                    # Description
                    desc_el = article.find(class_='tribe-events-calendar-list__event-description')
                    description = desc_el.get_text(separator=' ', strip=True)[:300] if desc_el else ''

                    # Price
                    price_el = article.find(class_='tribe-events-c-small-cta__price')
                    price = price_el.get_text(strip=True) if price_el else ''

                    events.append(self.normalize_event({
                        'title': self._clean_text(title),
                        'description': self._clean_text(description),
                        'venue': 'ASU Kerr Cultural Center',
                        'date': date,
                        'url': url,
                        'category': 'arts',
                        'price': price,
                    }))

                except Exception:
                    continue

        except Exception as e:
            print(f"Error scraping ASU Kerr: {e}")
        finally:
            self.close_driver()

        print(f"ASU Kerr: collected {len(events)} events")
        return events

    def _clean_text(self, text):
        replacements = {'û': '–', 'á': ' ', 'Æ': "'", '\ufe0f': ''}
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return unicodedata.normalize('NFKC', text).strip()

    def _parse_date(self, date_str, span_text):
        """Parse date from datetime attr + span text like 'March 25 @ 7:30 pm'"""
        try:
            # date_str is YYYY-MM-DD
            base = datetime.strptime(date_str, '%Y-%m-%d')
            # Extract time from span: "March 25 @ 7:30 pm"
            m = re.search(r'@\s*(\d{1,2}):(\d{2})\s*(am|pm)', span_text, re.IGNORECASE)
            if m:
                hour, minute = int(m.group(1)), int(m.group(2))
                ampm = m.group(3).lower()
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return base.replace(hour=12, minute=34, second=0, microsecond=0)
        except Exception:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
