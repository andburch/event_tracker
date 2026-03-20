"""
Mesa Arts Center events scraper
Scrapes shows/events from mesaartscenter.com/shows/
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class MesaArtsScraper(BaseScraper):
    """Scrape events from Mesa Arts Center"""

    def __init__(self):
        super().__init__('mesa_arts')
        self.shows_url = 'https://www.mesaartscenter.com/shows/'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Mesa Arts Center...")
            driver = self.get_driver()
            driver.set_page_load_timeout(20)
            try:
                driver.get(self.shows_url)
            except Exception:
                pass
            time.sleep(8)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Each show is in a div.show-item containing title text, date, and a show-details link
            show_items = soup.find_all(class_='show-item')
            print(f"  Found {len(show_items)} show-item containers")

            for item in show_items:
                try:
                    # The "Learn More" link has the URL
                    link = item.find('a', href=re.compile(r'show-details'))
                    if not link:
                        continue
                    href = link.get('href', '')
                    full_url = href if href.startswith('http') else f'https://www.mesaartscenter.com{href}'

                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # Title and date are text nodes in show-item
                    # Format: "Show Title\nDate\nLearn More"
                    item_text = item.get_text(separator='\n', strip=True)
                    lines = [l.strip() for l in item_text.split('\n') if l.strip() and l.strip() != 'Learn More']

                    if not lines:
                        continue
                    title = lines[0]
                    # Clean up garbled em-dash characters
                    title = title.replace('û', '–').replace('\u00fb', '–')
                    if not title or len(title) < 3:
                        continue

                    # Date is the second line (e.g. "Mar 18, 2026" or "Mar 18 – Mar 19, 2026")
                    date_text = lines[1] if len(lines) > 1 else ''
                    date = self._parse_date(date_text)

                    events.append(self.normalize_event({
                        'title': title,
                        'description': 'Mesa Arts Center performance',
                        'venue': 'Mesa Arts Center',
                        'date': date,
                        'url': full_url,
                        'category': 'arts'
                    }))
                except Exception:
                    continue

        except Exception as e:
            print(f"Error scraping Mesa Arts Center: {e}")
        finally:
            self.close_driver()

        print(f"Mesa Arts Center: collected {len(events)} events")
        return events

    def _parse_date(self, text):
        """Parse date from 'Mar 18, 2026' or 'Mar 18 – Mar 19, 2026' or 'Jun 9, 2026'"""
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        m = re.search(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?',
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
