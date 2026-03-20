"""
Arizona Museum of Natural History events scraper
Scrapes events from azmnh.org/azmnh-events
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class AZMNHScraper(BaseScraper):
    """Scrape events from Arizona Museum of Natural History (Mesa)"""

    def __init__(self):
        super().__init__('azmnh')
        self.events_url = 'https://www.azmnh.org/azmnh-events'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Arizona Museum of Natural History...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            driver.get(self.events_url)
            time.sleep(10)  # Site is slow to render

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Events are in class-grid-section, links are /related-event-details/N
            section = soup.find(class_='class-grid-section')
            if not section:
                section = soup.find(class_='classes-shows-listing')
            if not section:
                section = soup

            # Find all "Learn More" links pointing to event detail pages
            links = section.find_all('a', href=re.compile(r'related-event-details', re.I))
            print(f"  Found {len(links)} event links")

            for link in links:
                href = link.get('href', '')
                full_url = href if href.startswith('http') else f'https://www.azmnh.org{href}'
                if full_url in seen:
                    continue
                seen.add(full_url)

                # Title is in the aria-label: "Learn more about EVENT NAME"
                aria = link.get('aria-label', '')
                title = re.sub(r'^learn more about\s+', '', aria, flags=re.IGNORECASE).strip()
                if not title or len(title) < 3:
                    continue

                # Walk up to event-details div (level 2 up from link)
                # Structure: link > btn-group > event-details > event-card
                card = link.parent.parent  # event-details div has title, date, description

                date = self._parse_date(card)

                # Get description from card text, stripping title and date
                description = ''
                if card:
                    full_text = card.get_text(separator=' ', strip=True)
                    # Remove title from start of text
                    desc_text = full_text.replace(title, '', 1).strip()
                    description = desc_text[:300]

                events.append(self.normalize_event({
                    'title': title,
                    'description': description,
                    'venue': 'Arizona Museum of Natural History',
                    'date': date,
                    'url': full_url,
                    'category': 'museum'
                }))

        except Exception as e:
            print(f"Error scraping AZMNH: {e}")
        finally:
            self.close_driver()

        print(f"AZMNH: collected {len(events)} events")
        return events

    def _parse_date(self, card):
        """Parse date from card text like 'March 28, 2026 10:00 AM - 12:00 PM'"""
        if not card:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

        text = card.get_text(separator=' ', strip=True)

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
