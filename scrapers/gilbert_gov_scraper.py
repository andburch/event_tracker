"""
Gilbert.gov calendar scraper
Scrapes events from gilbertaz.gov/residents/calendar-month-view/
Same CivicPlus platform as TCA - calendar_day_with_items / calendar_item structure.
Paginates via "Next Month >" link for 3 months ahead.
Requires CDP user-agent spoofing to bypass Akamai.
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re
import time


class GilbertGovScraper(BaseScraper):
    """Scrape events from Gilbert, AZ city calendar"""

    def __init__(self):
        super().__init__('gilbert_gov')
        self.base_url = 'https://www.gilbertaz.gov'
        self.start_path = '/residents/calendar-month-view/'
        self.months_ahead = 3

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Gilbert Gov calendar...")
            driver = self.get_driver()
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'acceptLanguage': 'en-US,en;q=0.9',
                'platform': 'Win32'
            })
            driver.set_page_load_timeout(20)

            current_path = self.start_path

            for month_idx in range(self.months_ahead):
                url = self.base_url + current_path
                print(f"  Loading month {month_idx + 1}: {url}")
                try:
                    driver.get(url)
                except Exception:
                    pass
                time.sleep(6)

                soup = BeautifulSoup(driver.page_source, 'html.parser')

                if 'Access Denied' in soup.get_text()[:500]:
                    print("  Gilbert blocked by firewall - skipping")
                    break

                # Get month/year from calendar_title table
                month_year = self._get_month_year(soup)
                if not month_year:
                    print("  Could not determine calendar month/year")
                    break
                month, year = month_year
                print(f"  Calendar: {month}/{year}")

                # Parse all day cells with events
                day_cells = soup.find_all('td', class_=lambda c: c and 'calendar_day_with_items' in str(c))
                print(f"  Found {len(day_cells)} days with events")

                for td in day_cells:
                    # Day number is the direct text node before the calendar_items div
                    day_num = None
                    for content in td.contents:
                        text = str(content).strip()
                        if text.isdigit():
                            day_num = int(text)
                            break
                    if not day_num:
                        continue

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
                            event_key = f"{title}|{year}-{month:02d}-{day_num:02d}"
                            if event_key in seen:
                                continue
                            seen.add(event_key)

                            time_el = item.find(class_='calendar_eventtime')
                            time_str = time_el.get_text(strip=True) if time_el else ''
                            date = self._build_date(year, month, day_num, time_str)

                            events.append(self.normalize_event({
                                'title': title,
                                'description': '',
                                'venue': 'Gilbert, AZ',
                                'date': date,
                                'url': full_url,
                                'category': 'community',
                            }))

                        except Exception:
                            continue

                # Find "Next Month >" link for next iteration
                next_link = soup.find('a', class_='next')
                if not next_link or not next_link.get('href'):
                    print("  No next month link found")
                    break
                current_path = next_link['href']

        except Exception as e:
            print(f"Error scraping Gilbert Gov: {e}")
        finally:
            self.close_driver()

        print(f"Gilbert Gov: collected {len(events)} events")
        return events

    def _get_month_year(self, soup):
        """Extract month and year from calendar_title table header."""
        table = soup.find('table', class_='calendar_title')
        if not table:
            return None
        text = table.get_text(separator=' ', strip=True)
        m = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            text, re.IGNORECASE
        )
        if m:
            months = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            return months[m.group(1).lower()], int(m.group(2))
        return None

    def _build_date(self, year, month, day, time_str):
        """Build datetime from year/month/day + time string like '3:00 PM'"""
        hour, minute = 12, 34  # default sentinel
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
