"""
Desert Botanical Garden events scraper
Scrapes events from dbg.org/explore/events/
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class DBGScraper(BaseScraper):
    """Scrape events from Desert Botanical Garden"""

    def __init__(self):
        super().__init__('dbg')
        self.events_url = 'https://dbg.org/explore/events/'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Desert Botanical Garden...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            driver.get(self.events_url)
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            events = self._parse_events(soup, seen)

        except Exception as e:
            print(f"Error scraping DBG: {e}")
        finally:
            self.close_driver()

        print(f"Desert Botanical Garden: collected {len(events)} events")
        return events

    def _parse_events(self, soup, seen):
        events = []

        # DBG uses cards/tiles for events
        items = (
            soup.find_all('article') or
            soup.find_all('div', class_=re.compile(r'event|card|item|post', re.I))
        )

        for item in items:
            try:
                link = item.find('a', href=True)
                if not link:
                    continue

                href = link['href']
                full_url = href if href.startswith('http') else f'https://dbg.org{href}'
                if full_url in seen:
                    continue

                # Get title
                title_el = item.find(['h2', 'h3', 'h4']) or link
                title = title_el.get_text(separator=' ', strip=True)
                if not title or len(title) < 3:
                    continue

                seen.add(full_url)

                date = self._parse_date(item)

                desc_el = item.find(class_=re.compile(r'desc|summary|excerpt|content|body'))
                description = desc_el.get_text(separator=' ', strip=True)[:300] if desc_el else ''

                events.append(self.normalize_event({
                    'title': title,
                    'description': description,
                    'venue': 'Desert Botanical Garden',
                    'date': date,
                    'url': full_url,
                    'category': 'nature'
                }))
            except Exception:
                continue

        return events

    def _parse_date(self, item):
        text = item.get_text(separator=' ', strip=True)

        # "March 21, 2026" or "Mar 21, 2026" or "March 21 – April 5, 2026"
        m = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'\.?\s+(\d{1,2}),?\s+(\d{4})(?:.*?(\d{1,2}):(\d{2})\s*(AM|PM|am|pm))?',
            text
        )
        if m:
            try:
                month = datetime.strptime(m.group(1)[:3], '%b').month
                day = int(m.group(2))
                year = int(m.group(3))
                hour = int(m.group(4)) if m.group(4) else 10
                minute = int(m.group(5)) if m.group(5) else 0
                ampm = m.group(6).upper() if m.group(6) else 'AM'
                if ampm == 'PM' and hour != 12:
                    hour += 12
                elif ampm == 'AM' and hour == 12:
                    hour = 0
                return datetime(year, month, day, hour, minute)
            except Exception:
                pass

        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
