"""
Tempe Public Library events scraper
Scrapes events from tempepubliclibrary.libnet.info
"""
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from .base_scraper import BaseScraper
import re
import time


class TempeLibraryScraper(BaseScraper):
    """Scrape events from Tempe Public Library"""

    def __init__(self):
        super().__init__('tempe_library')
        # Use date range to get all upcoming events at once
        today = datetime.now().strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
        self.events_url = f'https://tempepubliclibrary.libnet.info/events?start={today}&end={end}'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Tempe Public Library...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            # Spoof user agent - site blocks headless Chrome
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            driver.get(self.events_url)
            time.sleep(6)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.find_all(class_='eelistevent')
            print(f"  Found {len(items)} events on page")

            for item in items:
                try:
                    title_el = item.find(class_='eelisttitle')
                    if not title_el:
                        continue
                    link = title_el.find('a')
                    title = title_el.get_text(separator=' ', strip=True)
                    if not title:
                        continue

                    href = link['href'] if link else ''
                    full_url = f'https://tempepubliclibrary.libnet.info{href}' if href.startswith('/') else href
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    date = self._parse_date(item)

                    desc_el = item.find(class_='eelistdesc')
                    description = desc_el.get_text(separator=' ', strip=True)[:300] if desc_el else ''

                    loc_el = item.find(class_='eelocation')
                    venue = loc_el.get_text(separator=' ', strip=True) if loc_el else 'Tempe Public Library'
                    # Clean up - remove icon text and extra whitespace
                    venue = re.sub(r'\s+', ' ', venue).strip()
                    # Remove leading icon characters or symbols
                    venue = re.sub(r'^[^\w]+', '', venue).strip()
                    if not venue:
                        venue = 'Tempe Public Library'

                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': venue,
                        'date': date,
                        'url': full_url,
                        'category': 'library'
                    }))
                except Exception:
                    continue

        except Exception as e:
            print(f"Error scraping Tempe Library: {e}")
        finally:
            self.close_driver()

        print(f"Tempe Public Library: collected {len(events)} events")
        return events

    def _parse_date(self, item):
        """Parse date from 'Monday, March 16: 10:00am - 10:30am' format"""
        time_el = item.find(class_='eelisttime')
        date_text = time_el.get_text(separator=' ', strip=True) if time_el else ''

        # "Monday, March 16: 10:00am" or "March 16, 2026: 10:00am"
        m = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'\.?\s+(\d{1,2})(?:,\s*(\d{4}))?[:\s]+(\d{1,2}):(\d{2})(am|pm)',
            date_text, re.IGNORECASE
        )
        if m:
            try:
                month = datetime.strptime(m.group(1)[:3], '%b').month
                day = int(m.group(2))
                year = int(m.group(3)) if m.group(3) else datetime.now().year
                hour = int(m.group(4))
                minute = int(m.group(5))
                ampm = m.group(6).lower()
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                # If no year in text, infer from current date
                if not m.group(3):
                    now = datetime.now()
                    # Build candidate date for this year
                    try:
                        candidate = datetime(now.year, month, day, hour, minute)
                    except ValueError:
                        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
                    # If that date is more than 7 days in the past, try next year
                    if candidate < now - timedelta(days=7):
                        candidate = datetime(now.year + 1, month, day, hour, minute)
                    return candidate
                return datetime(year, month, day, hour, minute)
            except Exception:
                pass

        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
