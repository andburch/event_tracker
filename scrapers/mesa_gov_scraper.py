"""
Mesa.gov events scraper
Scrapes events from Mesa city events directory
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
import re
import time

class MesaGovScraper(BaseScraper):
    """Scrape events from Mesa.gov events directory"""
    
    def __init__(self):
        super().__init__('mesa_gov')
        self.base_url = 'https://www.mesaaz.gov/Events-directory'
        
        # Categories to include
        self.target_categories = [
            'Community Class/Program',
            'Special Event/Festival',
            'Parks, Recreation and Community Facilities'
        ]
    
    def scrape(self):
        """Scrape events from Mesa events directory with pagination"""
        events = []
        seen_urls = set()
        
        try:
            print(f"Scraping Mesa events...")
            driver = self.get_driver()
            driver.get(self.base_url)
            
            # Wait for page to fully load — retry once if nothing renders
            print(f"  Waiting for page to load...")
            time.sleep(10)
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            if not soup.find('div', class_='list-item-container'):
                print(f"  No containers yet, waiting longer...")
                time.sleep(10)
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find pagination info to get max pages
            pagination_info = soup.find('div', class_='seamless-pagination-info')
            max_page = 1
            if pagination_info:
                info_text = pagination_info.get_text(strip=True)
                match = re.search(r'Page \d+ of (\d+)', info_text)
                if match:
                    max_page = int(match.group(1))
            
            print(f"  Found {max_page} pages of events")
            
            # Scrape each page
            for page_num in range(1, max_page + 1):
                print(f"  Processing page {page_num}...")
                
                # Navigate to page if not first page
                if page_num > 1:
                    try:
                        print(f"    Navigating to page {page_num}...")
                        # Find the page link using Selenium
                        from selenium.webdriver.common.by import By
                        
                        # Find all links in pagination
                        pagination = driver.find_element(By.CSS_SELECTOR, 'div.seamless-pagination-pages')
                        page_links = pagination.find_elements(By.TAG_NAME, 'a')
                        
                        page_link = None
                        for link in page_links:
                            if link.text.strip() == str(page_num):
                                page_link = link
                                break
                        
                        if page_link:
                            print(f"    Clicking page {page_num}...")
                            page_link.click()
                            time.sleep(4)
                        else:
                            print(f"    Could not find link for page {page_num}")
                            continue
                    except Exception as e:
                        print(f"    Error navigating to page {page_num}: {e}")
                        continue
                
                # Get page source and parse
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Find event listings
                event_containers = soup.find_all('div', class_='list-item-container')
                print(f"    Found {len(event_containers)} event containers on page {page_num}")
                
                for container in event_containers:
                    try:
                        article = container.find('article')
                        if not article:
                            continue
                        
                        # Extract title from h2.list-item-title
                        title_elem = article.find('h2', class_='list-item-title')
                        if not title_elem:
                            continue

                        # Check for canceled badge before extracting text
                        canceled = title_elem.find(string=lambda t: t and 'cancel' in t.lower())
                        if canceled:
                            continue  # Skip canceled events entirely

                        title = title_elem.get_text(strip=True)
                        # Strip any leading "Canceled" prefix just in case
                        import re as _re
                        title = _re.sub(r'^Canceled\s*', '', title, flags=_re.IGNORECASE).strip()
                        if not title:
                            continue

                        # Skip pure government meetings (not public events)
                        _skip_keywords = ('council meeting', 'council study session',
                                          'committee meeting', 'board meeting',
                                          'advisory board', 'commission meeting')
                        if any(kw in title.lower() for kw in _skip_keywords):
                            continue
                        
                        # Extract URL
                        link = article.find('a', href=True)
                        if not link:
                            continue
                        url = link['href']
                        if not url.startswith('http'):
                            url = 'https://www.mesaaz.gov' + url
                        
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        # Extract category from "tagged-as-list"
                        category = self._extract_category(article)
                        
                        # Extract date from span.list-item-block-date
                        date = self._extract_date(article)
                        
                        # Extract venue from p.list-item-address
                        venue = self._extract_venue(article, category)
                        
                        # Extract description from span.list-item-block-desc
                        description = self._extract_description(article, category)
                        
                        events.append(self.normalize_event({
                            'title': title,
                            'description': description,
                            'venue': venue,
                            'date': date,
                            'url': url,
                            'category': 'community'
                        }))
                        
                    except Exception as e:
                        pass
            
            driver.quit()
            print(f"Total Mesa events collected: {len(events)}")
            
        except Exception as e:
            print(f"Error scraping Mesa events: {e}")
        
        return events
    
    def _extract_category(self, item):
        """Extract category from event item - from p.tagged-as-list > span.text"""
        tagged_list = item.find('p', class_='tagged-as-list')
        if tagged_list:
            # Get all span.text elements
            category_spans = tagged_list.find_all('span', class_='text')
            if category_spans:
                categories = [span.get_text(strip=True) for span in category_spans if span.get_text(strip=True)]
                return ', '.join(categories) if categories else None
        
        return None
    
    def _extract_title(self, item):
        """Extract title from event item"""
        # Try h1-h4 tags
        for i in range(1, 5):
            title_elem = item.find(f'h{i}')
            if title_elem:
                title = title_elem.get_text(strip=True)
                if len(title) > 5:
                    return title
        
        # Try title class
        title_elem = item.find(class_=lambda x: x and 'title' in str(x).lower())
        if title_elem:
            return title_elem.get_text(strip=True)
        
        # Try data-title attribute
        if item.get('data-title'):
            return item.get('data-title')
        
        return None
    
    def _extract_url(self, item):
        """Extract URL from event item"""
        # Find first link
        link = item.find('a', href=True)
        if link:
            url = link['href']
            # Make absolute URL
            if url.startswith('/'):
                url = 'https://www.mesaaz.gov' + url
            elif not url.startswith('http'):
                url = 'https://www.mesaaz.gov/' + url
            return url
        
        return None
    
    def _extract_date(self, item):
        """Extract date from span.list-item-block-date with child spans"""
        date_block = item.find('span', class_='list-item-block-date')
        if date_block:
            # Extract date parts from child spans
            day_span = date_block.find('span', class_='part-date')
            month_span = date_block.find('span', class_='part-month')
            year_span = date_block.find('span', class_='part-year')
            
            if day_span and month_span and year_span:
                try:
                    day = int(day_span.get_text(strip=True))
                    month_text = month_span.get_text(strip=True)
                    year = int(year_span.get_text(strip=True))
                    
                    # Map month abbreviations to numbers
                    month_map = {
                        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                    }
                    month = month_map.get(month_text.lower()[:3], 1)
                    
                    return datetime(year, month, day, 12, 34)
                except Exception as e:
                    print(f"  Error parsing date parts: {e}")
        
        # Fallback to default date
        return self._default_date()
    
    def _default_date(self):
        """Return default date (next Saturday)"""
        from datetime import timedelta
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        return today.replace(hour=12, minute=34, second=0, microsecond=0) + timedelta(days=days_ahead)
    
    def _extract_venue(self, item, category):
        """Extract venue from p.list-item-address"""
        address_elem = item.find('p', class_='list-item-address')
        if address_elem:
            venue = address_elem.get_text(strip=True)
            if venue and len(venue) > 3:
                return venue
        
        # Use category as fallback
        if category:
            if 'Parks' in category or 'Recreation' in category:
                return 'Mesa Parks & Recreation'
            elif 'Community' in category:
                return 'Mesa Community Center'
        
        return 'Mesa, AZ'
    
    def _extract_description(self, item, category):
        """Extract description from span.list-item-block-desc"""
        desc_elem = item.find('span', class_='list-item-block-desc')
        if desc_elem:
            desc = desc_elem.get_text(strip=True)
            if desc and len(desc) > 10:
                # Clean and truncate
                desc = ' '.join(desc.split())
                if len(desc) > 200:
                    desc = desc[:200] + '...'
                # Only add category prefix if we have a description
                if category:
                    return f"{category} | {desc}"
                return desc
        
        # If no description, just return category
        return category if category else 'Mesa Community Event'
