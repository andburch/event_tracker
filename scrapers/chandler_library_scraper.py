"""
Chandler Public Library events scraper
Scrapes events from chandler.bibliocommons.com (BiblioCommons platform)
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class ChandlerLibraryScraper(BaseScraper):
    """Scrape events from Chandler Public Library"""

    def __init__(self):
        super().__init__('chandler_library')
        self.base_url = 'https://chandler.bibliocommons.com/v2/events'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Chandler Public Library...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)

            page = 1
            while page <= 5:
                url = self.base_url if page == 1 else f'{self.base_url}?page={page}'
                driver.get(url)
                time.sleep(4)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                items = soup.find_all(class_='cp-events-search-item')

                if not items:
                    break

                new_found = False
                for item in items:
                    try:
                        title_el = item.find(class_='cp-event-title')
                        if not title_el:
                            continue
                        title = title_el.get_text(separator=' ', strip=True)
                        # Strip BiblioCommons status prefixes and badges
                        title = re.sub(r'\b(Featured|In Progress)\b\s*', '', title, flags=re.IGNORECASE)
                        # Strip "Featured Event." prefix pattern
                        title = re.sub(r'^Featured Event\.\s*', '', title, flags=re.IGNORECASE)
                        # Strip trailing/leading "Event." artifacts
                        title = re.sub(r'\s*Event\.\s*', ' ', title, flags=re.IGNORECASE).strip()
                        # Remove duplicate title text (BiblioCommons sometimes repeats it)
                        # e.g. "Foo Bar Foo Bar" -> "Foo Bar"
                        words = title.split()
                        half = len(words) // 2
                        if half >= 2 and words[:half] == words[half:]:
                            title = ' '.join(words[:half])
                        title = re.sub(r'\s{2,}', ' ', title).strip()
                        if not title:
                            continue

                        link = title_el.find('a') or item.find('a', href=True)
                        href = link['href'] if link else ''
                        full_url = href if href.startswith('http') else f'https://chandler.bibliocommons.com{href}'

                        if full_url in seen:
                            continue
                        seen.add(full_url)
                        new_found = True

                        date = self._parse_date(item)

                        desc_el = item.find(class_='cp-event-description')
                        description = desc_el.get_text(separator=' ', strip=True)[:300] if desc_el else ''

                        loc_el = item.find(class_='cp-event-location-name')
                        venue = loc_el.get_text(separator=' ', strip=True) if loc_el else 'Chandler Public Library'
                        # Strip "Event location: " prefix that BiblioCommons adds
                        venue = re.sub(r'Event location:\s*', '', venue, flags=re.IGNORECASE).strip()
                        # BiblioCommons duplicates the location text - take just the first occurrence
                        # e.g. "Sunset Library Event location: Sunset Library" -> "Sunset Library"
                        words = venue.split()
                        half = len(words) // 2
                        if half > 0 and words[:half] == words[half:half*2]:
                            venue = ' '.join(words[:half])
                        if not venue:
                            venue = 'Chandler Public Library'

                        events.append(self.normalize_event({
                            'title': title,
                            'description': description,
                            'venue': venue,
                            'date': date,
                            'url': full_url,
                            'category': 'library'
                        }))
                    except Exception as e:
                        continue

                if not new_found:
                    break
                page += 1

        except Exception as e:
            print(f"Error scraping Chandler Library: {e}")
        finally:
            self.close_driver()

        print(f"Chandler Library: collected {len(events)} events")
        return events

    def _parse_date(self, item):
        date_el = item.find(class_='cp-event-date')
        if not date_el:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

        # Year is in the screen-reader span: "on March 19, 2026"
        sr = date_el.find(class_='cp-screen-reader-message')
        sr_text = sr.get_text(strip=True) if sr else ''

        # Time is in the event-time span: "10:00am–11:30am"
        time_el = date_el.find(class_='event-time')
        time_text = time_el.get_text(separator=' ', strip=True) if time_el else ''

        # Parse date from screen-reader text: "on March 19, 2026"
        dm = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'\.?\s+(\d{1,2}),?\s+(\d{4})',
            sr_text
        )
        if not dm:
            # Fallback: try full date_el text
            full = date_el.get_text(separator=' ', strip=True)
            dm = re.search(
                r'(January|February|March|April|May|June|July|August|September|October|November|December|'
                r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
                r'\.?\s+(\d{1,2}),?\s+(\d{4})',
                full
            )

        if not dm:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

        try:
            month = datetime.strptime(dm.group(1)[:3], '%b').month
            day = int(dm.group(2))
            year = int(dm.group(3))

            # Parse time: "10:00am" or "1:00pm"
            tm = re.search(r'(\d{1,2}):(\d{2})(am|pm)', time_text, re.IGNORECASE)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2))
                ampm = tm.group(3).lower()
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
            else:
                hour, minute = 10, 0

            return datetime(year, month, day, hour, minute)
        except Exception:
            pass

        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
