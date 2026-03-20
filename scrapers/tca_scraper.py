"""
Tempe Center for the Arts events scraper
Scrapes events from tempecenterforthearts.com/events/calendar
Uses CDP user-agent spoofing to bypass Akamai firewall
Parses calendar grid: each <td> is a day, contains calendar_item divs with time+title
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class TCAScraper(BaseScraper):
    """Scrape events from Tempe Center for the Arts"""

    def __init__(self):
        super().__init__('tca')
        self.calendar_url = 'https://www.tempecenterforthearts.com/events/calendar'
        self.base_url = 'https://www.tempecenterforthearts.com'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Tempe Center for the Arts...")
            driver = self.get_driver()
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'acceptLanguage': 'en-US,en;q=0.9',
                'platform': 'Win32'
            })
            driver.set_page_load_timeout(20)
            try:
                driver.get(self.calendar_url)
            except Exception:
                pass
            time.sleep(10)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            if 'Access Denied' in soup.get_text()[:500]:
                print("  TCA blocked by firewall - skipping")
                return []

            # Get month/year from calendar table header row
            # Table has class 'calendar_title', second row contains "March 2026"
            month_year = self._get_month_year(soup)
            if not month_year:
                print("  Could not determine calendar month/year")
                return []
            month, year = month_year
            print(f"  Calendar month: {month}/{year}")

            # Each <td> with class containing 'calendar_day_with_items' is a day cell
            # The day number is the first text node in the <td>
            day_cells = soup.find_all('td', class_=lambda c: c and 'calendar_day_with_items' in str(c))
            print(f"  Found {len(day_cells)} days with events")

            for td in day_cells:
                # Day number is the direct text of the td (before any child divs)
                day_num = None
                for content in td.contents:
                    text = str(content).strip()
                    if text.isdigit():
                        day_num = int(text)
                        break
                if not day_num:
                    continue

                # Each calendar_item has a time span and an event link
                for item in td.find_all(class_='calendar_item'):
                    try:
                        link = item.find('a', class_='calendar_eventlink')
                        if not link:
                            continue

                        href = link.get('href', '')
                        title = link.get('title') or link.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        full_url = self.base_url + href if href.startswith('/') else href
                        event_key = title + str(day_num)
                        if event_key in seen:
                            continue
                        seen.add(event_key)

                        # Time from calendar_eventtime span
                        time_el = item.find(class_='calendar_eventtime')
                        time_str = time_el.get_text(strip=True) if time_el else ''
                        date = self._build_date(year, month, day_num, time_str)

                        events.append(self.normalize_event({
                            'title': title,
                            'description': '',
                            'venue': 'Tempe Center for the Arts',
                            'date': date,
                            'url': full_url,
                            'category': 'arts',
                        }))

                    except Exception:
                        continue

        except Exception as e:
            print(f"Error scraping TCA: {e}")
        finally:
            self.close_driver()

        print(f"TCA: collected {len(events)} events")
        return events

    def _get_month_year(self, soup):
        """Extract month and year from the calendar table header."""
        table = soup.find('table', class_='calendar_title')
        if not table:
            return None
        # Second row contains "March 2026" or "Mar 2026"
        rows = table.find_all('tr')
        for row in rows:
            text = row.get_text(separator=' ', strip=True)
            m = re.search(
                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
                text, re.IGNORECASE
            )
            if m:
                months = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
                          'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}
                return months[m.group(1).lower()], int(m.group(2))
        return None

    def _build_date(self, year, month, day, time_str):
        """Build datetime from year/month/day + time string like '3:00 PM'"""
        hour, minute = 19, 30  # default
        m = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str, re.IGNORECASE)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if m.group(3).upper() == 'PM' and hour != 12:
                hour += 12
            elif m.group(3).upper() == 'AM' and hour == 12:
                hour = 0
        try:
            return datetime(year, month, day, hour, minute)
        except Exception:
            return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
