"""
Chandler Center for the Arts events scraper
Scrapes events from chandlercenter.org/events
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class ChandlerCenterScraper(BaseScraper):
    """Scrape events from Chandler Center for the Arts"""

    def __init__(self):
        super().__init__('chandler_center')
        self.events_url = 'https://www.chandlercenter.org/events'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Chandler Center for the Arts...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            driver.get(self.events_url)
            time.sleep(4)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Event links are /events/slug-name
            links = soup.find_all('a', href=re.compile(r'^/events/[^/]+$'))
            print(f"  Found {len(links)} event links")

            for link in links:
                href = link.get('href', '')
                full_url = f'https://www.chandlercenter.org{href}'
                if full_url in seen:
                    continue
                seen.add(full_url)

                title = link.get_text(separator=' ', strip=True)
                if not title or len(title) < 3:
                    continue

                # Date is in the card div (4 levels up from link)
                # Structure: link > h2.card-title > div.card-body > div.event-hit-area > div.card
                p = link.parent
                date_container = p.parent.parent.parent if (p and p.parent and p.parent.parent) else p
                date = self._parse_date_from_block(date_container)

                # Use surrounding card text as description (category + date info)
                description = ''
                if date_container:
                    full_text = date_container.get_text(separator=' ', strip=True)
                    description = full_text.replace(title, '').strip()[:200]

                events.append(self.normalize_event({
                    'title': title,
                    'description': description or 'Chandler Center for the Arts',
                    'venue': 'Chandler Center for the Arts',
                    'date': date,
                    'url': full_url,
                    'category': 'arts'
                }))

        except Exception as e:
            print(f"Error scraping Chandler Center: {e}")
        finally:
            self.close_driver()

        print(f"Chandler Center for the Arts: collected {len(events)} events")
        return events

    def _parse_date_from_block(self, block):
        if not block:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
        return self._parse_date_text(block.get_text(separator=' ', strip=True))

    def _parse_date_text(self, text):
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        m = re.search(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})(?:.*?(\d{4}))?',
            text, re.IGNORECASE
        )
        if m:
            try:
                month = months[m.group(1).lower()[:3]]
                day = int(m.group(2))
                year = int(m.group(3)) if m.group(3) else datetime.now().year
                return datetime(year, month, day, 19, 30)
            except Exception:
                pass
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
