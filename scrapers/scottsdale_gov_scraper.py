"""
Scottsdale.gov community calendar scraper
Uses the community.scottsdaleaz.gov platform (WithApps).

Structure per event:
  <li data-date="<unix_ts>" data-ends="..." data-key="...">
    <article class="activity-item">
      <a href="/scottsdaleaz_main/<id>">
        <div class="activity-titles">
          <span class="leader-name">Org Name</span>
          <div class="activity-name">Event Title</div>
        </div>
        <div style="display: none !important;">Description text</div>
      </a>
    </article>
  </li>
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import time


class ScottsdaleGovScraper(BaseScraper):
    """Scrape events from Scottsdale community calendar"""

    def __init__(self):
        super().__init__('scottsdale_gov')
        self.base_url = 'https://community.scottsdaleaz.gov/scottsdaleaz_main/calendar'

    def scrape(self):
        events = []
        seen_keys = set()

        try:
            print("Scraping Scottsdale Gov calendar...")
            driver = self.get_driver()
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'acceptLanguage': 'en-US,en;q=0.9',
                'platform': 'Win32'
            })
            driver.set_page_load_timeout(30)

            try:
                driver.get(self.base_url)
            except Exception:
                pass
            time.sleep(6)

            # Scroll to trigger lazy loading
            for _ in range(4):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Events are in <li> tags with data-date (unix timestamp)
            list_items = soup.select('ul.activities-list li[data-date]')
            print(f"  Found {len(list_items)} event list items")

            for li in list_items:
                try:
                    article = li.find('article', class_='activity-item')
                    if not article:
                        continue

                    # Unique key
                    key = li.get('data-key', '')
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    # Title from .activity-name
                    name_el = article.select_one('.activity-name')
                    if not name_el:
                        continue
                    title = name_el.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    # Venue/org from .leader-name
                    leader_el = article.select_one('.leader-name')
                    venue = leader_el.get_text(strip=True) if leader_el else 'Scottsdale, AZ'

                    # Description from the hidden div
                    hidden_div = article.find('div', style=lambda s: s and 'display: none' in s)
                    description = hidden_div.get_text(separator=' ', strip=True) if hidden_div else ''
                    description = ' '.join(description.split())[:500]

                    # Date from data-date (unix timestamp in seconds)
                    ts = li.get('data-date')
                    try:
                        date = datetime.fromtimestamp(int(ts))
                    except Exception:
                        date = datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

                    # URL
                    link = article.find('a', href=True)
                    url = link['href'] if link else self.base_url
                    if url.startswith('/'):
                        url = 'https://community.scottsdaleaz.gov' + url

                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': venue,
                        'date': date,
                        'url': url,
                        'category': 'community',
                    }))

                except Exception as e:
                    continue

        except Exception as e:
            print(f"Error scraping Scottsdale Gov: {e}")
        finally:
            self.close_driver()

        print(f"Scottsdale Gov: collected {len(events)} events")
        return events
