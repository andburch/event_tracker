"""
Scottsdale Arts events scraper
Scrapes events from scottsdalearts.org/whats-on/
Handles "Load More" pagination via Selenium click
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time
import unicodedata


class ScottsdaleArtsScraper(BaseScraper):
    """Scrape events from Scottsdale Arts (scottsdalearts.org)"""

    def __init__(self):
        super().__init__('scottsdale_arts')
        self.events_url = 'https://scottsdalearts.org/whats-on/?categories=performances,events,programs-workshops'

    def scrape(self):
        events = []
        seen = set()

        try:
            print("Scraping Scottsdale Arts...")
            driver = self.get_driver()
            driver.set_page_load_timeout(20)
            try:
                driver.get(self.events_url)
            except Exception:
                pass
            time.sleep(6)

            # Click "Load More Events" until it disappears
            clicks = 0
            while clicks < 20:
                try:
                    btn = WebDriverWait(driver, 4).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Load More')]"))
                    )
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(3)
                    clicks += 1
                except Exception:
                    break

            print(f"  Clicked Load More {clicks} times")

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Each event is in div.event; the link wraps an image (empty text)
            # Title, date, description are sibling elements inside div.event
            event_divs = soup.find_all(class_='event')
            print(f"  Found {len(event_divs)} event divs")

            for div in event_divs:
                try:
                    # URL from the anchor
                    link = div.find('a', href=re.compile(r'/whats-on/events/'))
                    if not link:
                        continue
                    href = link.get('href', '')
                    full_url = href if href.startswith('http') else f'https://scottsdalearts.org{href}'
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # Title: first non-empty text block in div.event
                    # Structure: link(img), h3/h2/p with title, category tags, date, description
                    title = ''
                    for tag in div.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'span']):
                        t = tag.get_text(strip=True)
                        if t and len(t) > 3 and not re.match(r'^(Events|Performances|Programs|Exhibitions|Special Event|Lifestyle|Dance|Classical|Jazz|Family)', t, re.I):
                            title = t
                            break

                    if not title:
                        # Fallback: derive from URL slug
                        slug = href.rstrip('/').split('/')[-1]
                        title = slug.replace('-', ' ').title()

                    if not title or len(title) < 3:
                        continue

                    # Date: look for pattern "Mar 20, 2026 / 7:00 p.m." or "Mar 20 – Mar 21, 2026"
                    div_text = div.get_text(separator=' ', strip=True)
                    date = self._parse_date(div_text)

                    # Description: text after the date
                    description = ''
                    desc_el = div.find(class_=re.compile(r'desc|excerpt|summary|body|content|blurb', re.I))
                    if desc_el:
                        description = desc_el.get_text(separator=' ', strip=True)[:300]
                    if not description:
                        # Use div text minus title
                        description = div_text.replace(title, '').strip()[:300]

                    events.append(self.normalize_event({
                        'title': self._clean_text(title),
                        'description': self._clean_text(description),
                        'venue': 'Scottsdale Arts',
                        'date': date,
                        'url': full_url,
                        'category': 'arts'
                    }))

                except Exception:
                    continue

        except Exception as e:
            print(f"Error scraping Scottsdale Arts: {e}")
        finally:
            self.close_driver()

        print(f"Scottsdale Arts: collected {len(events)} events")
        return events

    def _clean_text(self, text):
        """Fix mojibake and stray unicode from Windows-1252 mis-encoding"""
        replacements = {
            'á': ' ',   # non-breaking space mis-encoded
            'Æ': "'",   # right single quote mis-encoded
            'û': '–',   # em-dash mis-encoded
            '\u00e2\u0080\u0099': "'",
            '\ufe0f': '',  # variation selector (emoji modifier)
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        # Normalize unicode and strip control chars
        text = unicodedata.normalize('NFKC', text)
        return text.strip()

    def _parse_date(self, text):
        """Parse date from 'Mar 20, 2026 / 7:00 p.m.' or 'Mar 20 - Mar 21, 2026'"""
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        # Match "Mar 20, 2026 / 7:00 p.m." or "Mar 20, 2026"
        m = re.search(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+(\d{1,2}),?\s+(\d{4})'
            r'(?:\s*/\s*(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.|am|pm))?',
            text, re.IGNORECASE
        )
        if m:
            try:
                month = months[m.group(1).lower()[:3]]
                day = int(m.group(2))
                year = int(m.group(3))
                hour = int(m.group(4)) if m.group(4) else 19
                minute = int(m.group(5)) if m.group(5) else 30
                ampm = m.group(6).replace('.', '').lower() if m.group(6) else 'pm'
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                return datetime(year, month, day, hour, minute)
            except Exception:
                pass
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)
