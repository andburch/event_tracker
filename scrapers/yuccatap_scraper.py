"""
Yucca Tap Room scraper
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re

class YuccaTapScraper(BaseScraper):
    """Scrape Yucca Tap Room events"""
    
    def __init__(self):
        super().__init__('yuccatap')
        self.base_url = 'https://yuccatap.com/events'
    
    def scrape(self):
        """Scrape events from Yucca Tap Room"""
        events = []
        try:
            # Use Selenium and scroll to load more events
            driver = self.get_driver()
            driver.get(self.base_url)
            
            # Wait for initial load
            import time
            time.sleep(5)
            
            # Scroll down multiple times to trigger infinite scroll
            print("Scrolling to load more events...")
            scroll_pause_time = 3
            
            # Get initial scroll height
            last_height = driver.execute_script("return document.body.scrollHeight")
            events_loaded = 0
            
            for scroll_attempt in range(10):  # Try up to 10 scrolls
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for page to load
                time.sleep(scroll_pause_time)
                
                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script("return document.body.scrollHeight")
                
                # Count visible events
                soup_temp = BeautifulSoup(driver.page_source, 'html.parser')
                current_events = len(soup_temp.find_all(['article', 'li', 'div'], class_=lambda x: x and 'event' in str(x).lower()))
                
                print(f"Scroll {scroll_attempt + 1}: height={new_height}, events visible={current_events}")
                
                if new_height == last_height and current_events == events_loaded:
                    print(f"No more content loaded after scroll {scroll_attempt + 1}")
                    break
                    
                last_height = new_height
                events_loaded = current_events
            
            # Get the page source after scrolling
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Look for event items in Squarespace calendar
            event_items = soup.find_all(['article', 'li', 'div'], class_=lambda x: x and any(
                keyword in str(x).lower() for keyword in ['event', 'calendar', 'summary']
            ))
            
            print(f"Found {len(event_items)} potential event items")
            
            seen_urls = set()  # Track URLs to avoid duplicates
            
            for item in event_items[:100]:
                try:
                    # Extract title
                    title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'a'], class_=lambda x: x and 'title' in str(x).lower())
                    if not title_elem:
                        title_elem = item.find(['h1', 'h2', 'h3', 'h4'])
                    
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    if len(title) < 3 or title.lower() in ['view event', 'more info', 'tickets']:
                        continue
                    
                    # Extract URL
                    link = item.find('a', href=True)
                    url = link['href'] if link else self.base_url
                    if url and not url.startswith('http'):
                        url = 'https://yuccatap.com' + url
                    
                    # Skip duplicates
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # Extract date/time
                    date_elem = item.find(['time', 'span', 'div'], class_=lambda x: x and 'date' in str(x).lower())
                    date_text = date_elem.get_text(strip=True) if date_elem else ''
                    
                    # Try to find time separately
                    time_elem = item.find(['time', 'span', 'div'], class_=lambda x: x and 'time' in str(x).lower())
                    time_text = time_elem.get_text(strip=True) if time_elem else ''
                    
                    date = self._parse_date(date_text, time_text, item.get_text())
                    
                    # Extract description
                    desc_elem = item.find(['p', 'div'], class_=lambda x: x and any(
                        keyword in str(x).lower() for keyword in ['description', 'excerpt', 'summary']
                    ))
                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else title
                    
                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': 'Yucca Tap Room, Tempe',
                        'date': date,
                        'url': url,
                        'category': 'music'
                    }))
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"Error scraping Yucca Tap Room: {e}")
        
        return events
    
    def _parse_date(self, date_text, time_text, full_text):
        """Parse date from text"""
        combined_text = f"{date_text} {time_text} {full_text}"
        
        # Try datetime attribute first
        if 'datetime' in combined_text:
            try:
                # Look for ISO format
                iso_match = re.search(r'\d{4}-\d{2}-\d{2}', combined_text)
                if iso_match:
                    return datetime.fromisoformat(iso_match.group(0))
            except:
                pass
        
        # Pattern: "March 10, 2026" or "Tuesday, March 10, 2026"
        date_pattern = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})'
        match = re.search(date_pattern, combined_text, re.IGNORECASE)
        
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3))
            
            # Extract time (e.g., "8:00 PM")
            time_pattern = r'(\d{1,2}):(\d{2})\s*(AM|PM)'
            time_match = re.search(time_pattern, combined_text, re.IGNORECASE)
            
            hour = 12  # Default sentinel
            minute = 34
        simple_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})'
        match = re.search(simple_pattern, combined_text, re.IGNORECASE)
        
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = datetime.now().year
            
            try:
                date = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y")
                if date < datetime.now():
                    date = date.replace(year=year + 1)
                return date.replace(hour=12, minute=34)
            except:
                pass
        
        # Default to next Saturday at 8 PM
        from datetime import timedelta
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        next_saturday = today.replace(hour=12, minute=34, second=0, microsecond=0)
        return next_saturday + timedelta(days=days_ahead)
