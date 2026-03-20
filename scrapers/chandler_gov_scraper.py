"""
Chandler.gov events scraper
Scrapes events from Chandler city events directory
"""
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from .base_scraper import BaseScraper
import time

class ChandlerGovScraper(BaseScraper):
    """Scrape events from Chandler.gov events directory"""
    
    def __init__(self):
        super().__init__('chandler_gov')
        # URL with pre-filtered categories for relevant events
        self.base_url = 'https://www.chandleraz.gov/events-result?keyword=&categories%5B2%5D=2&categories%5B3%5D=3&categories%5B5%5D=5&categories%5B558%5D=558&categories%5B6%5D=6&categories%5B7%5D=7&categories%5B8%5D=8&categories%5B11%5D=11&categories%5B14%5D=14&categories%5B15%5D=15&categories%5B19%5D=19&categories%5B17%5D=17&categories%5B20%5D=20'
    
    def scrape(self):
        """Scrape events from Chandler events directory with pagination"""
        events = []
        seen_urls = set()  # Track URLs to avoid exact duplicates
        driver = None
        
        try:
            from selenium.common.exceptions import TimeoutException
            
            print(f"Scraping Chandler events...")
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            
            page = 1
            max_pages = 9  # Force 9 pages - we know they exist
            
            while page <= max_pages:
                print(f"  Processing page {page}...")
                
                # Build URL with page parameter (0-indexed: page 1 = page=0, page 2 = page=1, etc.)
                page_param = page - 1
                url = self.base_url + f'&page={page_param}'
                
                try:
                    driver.get(url)
                    time.sleep(4)  # Wait for page to load
                except TimeoutException:
                    print("⚠️  Page load timeout, but continuing...")
                    time.sleep(2)
                
                # Get page source and parse
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Find event cards - they're in div.event-wrap containers
                event_cards = soup.find_all('div', class_='event-wrap')
                
                print(f"    Found {len(event_cards)} event cards")
                
                if len(event_cards) == 0:
                    print(f"    No events on page {page}, stopping")
                    break
                
                page_events = 0
                for card in event_cards:
                    try:
                        # Extract title from div.title > a
                        title_elem = card.find('div', class_='title')
                        if title_elem:
                            title_link = title_elem.find('a')
                            if title_link:
                                title = title_link.get_text(separator=' ', strip=True)
                                title = ' '.join(title.split())  # Clean up multiple spaces
                            else:
                                continue
                        else:
                            continue
                        
                        if not title or len(title) < 3:
                            continue
                        
                        # Extract URL from the title link
                        url = title_link.get('href', '')
                        if not url:
                            continue
                        
                        if not url.startswith('http'):
                            url = 'https://www.chandleraz.gov' + url
                        
                        # Extract date from div.date structure (day + month)
                        # Time is in div.day inside div.content: "March 18, 2026 | 10:30 - 11:15 a.m."
                        date_div = card.find('div', class_='date')
                        content_div = card.find('div', class_='content')
                        content_day_div = content_div.find('div', class_='day') if content_div else None

                        if date_div:
                            day_elem = date_div.find('div', class_='day')
                            month_elem = date_div.find('div', class_='month')

                            if day_elem and month_elem:
                                day = day_elem.get_text(strip=True)
                                month = month_elem.get_text(strip=True)
                                # Get time from content div.day: "March 18, 2026 | 10:30 - 11:15 a.m."
                                time_str = ''
                                if content_day_div:
                                    day_text = content_day_div.get_text(separator=' ', strip=True)
                                    # Text after the "|" separator
                                    if '|' in day_text:
                                        time_str = day_text.split('|', 1)[1].strip()
                                date = self._parse_date_from_day_month(day, month, time_str)
                            else:
                                date = self._default_date()
                        else:
                            date = self._default_date()
                        
                        # Skip if we've seen this URL before
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        # Extract venue
                        venue = 'Chandler, AZ'
                        
                        # Extract description - look for any paragraph or description text
                        description = title  # Use title as description for now
                        
                        events.append(self.normalize_event({
                            'title': title,
                            'description': description,
                            'venue': venue,
                            'date': date,
                            'url': url,
                            'category': 'community'
                        }))
                        
                        page_events += 1
                        
                    except Exception as e:
                        print(f"      Error parsing event card: {e}")
                        continue
                
                print(f"    Collected {page_events} unique events from page {page}")
                
                # Move to next page (we're forcing 9 pages)
                page += 1
            
            driver.quit()
            print(f"Total Chandler events collected: {len(events)}")
            
        except Exception as e:
            print(f"Error scraping Chandler events: {e}")
            import traceback
            traceback.print_exc()
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        
        return events
    
    def _extract_date_from_card(self, card):
        """Extract date from event card - look for date badge with day and month"""
        import re
        
        # Look for the date badge structure (e.g., "13 March")
        # Try to find elements with date-related classes or the large date display
        date_badge = card.find('div', class_=lambda x: x and 'date' in str(x).lower())
        if not date_badge:
            date_badge = card.find('time')
        
        if date_badge:
            # Try datetime attribute first
            if date_badge.get('datetime'):
                try:
                    return datetime.fromisoformat(date_badge['datetime'].replace('Z', '+00:00'))
                except:
                    pass
            
            # Parse text like "13 March" or "March 13, 2026"
            date_text = date_badge.get_text(strip=True)
            parsed = self._parse_date_text(date_text)
            if parsed:
                return parsed
        
        # Look for date in the full card text
        card_text = card.get_text()
        
        # Pattern: "March 13, 2026" or "March 13, 2026 | 7:30 p.m."
        match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', card_text, re.IGNORECASE)
        if match:
            month_name, day, year = match.groups()
            month_map = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month = month_map[month_name.lower()]
            
            # Look for time in the same text
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.|am|pm)', card_text, re.IGNORECASE)
            if time_match:
                hour, minute, period = time_match.groups()
                hour = int(hour)
                minute = int(minute)
                if 'p' in period.lower() and hour != 12:
                    hour += 12
                elif 'a' in period.lower() and hour == 12:
                    hour = 0
                return datetime(int(year), month, int(day), hour, minute)
            else:
                return datetime(int(year), month, int(day), 12, 34)
        
        # Pattern: "13 March" (need to add current year)
        match = re.search(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)', card_text, re.IGNORECASE)
        if match:
            day, month_name = match.groups()
            month_map = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month = month_map[month_name.lower()]
            year = datetime.now().year
            return datetime(year, month, int(day), 10, 0)
        
        return self._default_date()
    
    def _extract_date(self, item):
        """Extract date from event item"""
        # Look for date elements
        date_selectors = [
            ('time', {}),
            ('span', {'class': lambda x: x and 'date' in str(x).lower()}),
            ('div', {'class': lambda x: x and 'date' in str(x).lower()}),
        ]
        
        for tag, attrs in date_selectors:
            date_elem = item.find(tag, attrs)
            if date_elem:
                # Try datetime attribute
                if date_elem.get('datetime'):
                    try:
                        return datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    except:
                        pass
                
                # Try parsing text
                date_text = date_elem.get_text(strip=True)
                if date_text:
                    return self._parse_date_text(date_text)
        
        # Return default date
        return self._default_date()
    
    def _parse_date_text(self, text):
        """Parse date from text"""
        if not text:
            return self._default_date()
        
        # Try common date formats
        import re
        
        # Pattern: MM/DD/YYYY
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            try:
                month, day, year = map(int, match.groups())
                return datetime(year, month, day, 12, 34)
            except:
                pass
        
        # Pattern: Month DD, YYYY
        match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', text, re.IGNORECASE)
        if match:
            try:
                month_name, day, year = match.groups()
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                month = month_map[month_name.lower()]
                return datetime(int(year), month, int(day), 12, 34)
            except:
                pass
        
        return self._default_date()
    
    def _default_date(self):
        """Return default date (next Saturday)"""
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        return today.replace(hour=12, minute=34, second=0, microsecond=0) + timedelta(days=days_ahead)
    
    def _extract_venue(self, item):
        """Extract venue from event item"""
        # Look for venue/location elements
        venue_selectors = [
            ('span', {'class': lambda x: x and ('location' in str(x).lower() or 'venue' in str(x).lower())}),
            ('div', {'class': lambda x: x and ('location' in str(x).lower() or 'venue' in str(x).lower())}),
            ('p', {'class': lambda x: x and ('location' in str(x).lower() or 'venue' in str(x).lower())}),
        ]
        
        for tag, attrs in venue_selectors:
            venue_elem = item.find(tag, attrs)
            if venue_elem:
                venue = venue_elem.get_text(strip=True)
                if venue and len(venue) > 3 and len(venue) < 100:
                    return venue
        
        return 'Chandler, AZ'
    
    def _extract_description(self, item):
        """Extract description from event item"""
        # Look for description elements
        desc_selectors = [
            ('p', {'class': lambda x: x and 'description' in str(x).lower()}),
            ('div', {'class': lambda x: x and 'description' in str(x).lower()}),
            ('span', {'class': lambda x: x and 'description' in str(x).lower()}),
        ]
        
        for tag, attrs in desc_selectors:
            desc_elem = item.find(tag, attrs)
            if desc_elem:
                desc = desc_elem.get_text(strip=True)
                if desc and len(desc) > 10:
                    # Clean and truncate
                    desc = ' '.join(desc.split())
                    if len(desc) > 200:
                        desc = desc[:200] + '...'
                    return desc
        
        return 'Chandler Community Event'

    def _parse_date_from_day_month(self, day, month, time_str=''):
        """Parse date from day number, month name, and optional time string.
        time_str example: '10:30 - 11:15 a.m.' or '7:30 p.m.'
        """
        import re as _re
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

        try:
            day_num = int(day)
            month_num = month_map.get(month.lower())

            if month_num:
                year = datetime.now().year

                # Parse time from time_str: "10:30 - 11:15 a.m." or "7:30 p.m."
                hour, minute = 12, 34  # default sentinel
                if time_str:
                    # Grab the first time token (start time)
                    tm = _re.search(r'(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.|am|pm)?', time_str, _re.IGNORECASE)
                    if tm:
                        hour = int(tm.group(1))
                        minute = int(tm.group(2))
                        period = (tm.group(3) or '').replace('.', '').lower()
                        # If no explicit am/pm, look anywhere in the time_str
                        if not period:
                            pm_match = _re.search(r'p\.m\.|pm', time_str, _re.IGNORECASE)
                            am_match = _re.search(r'a\.m\.|am', time_str, _re.IGNORECASE)
                            if pm_match:
                                period = 'pm'
                            elif am_match:
                                period = 'am'
                        if period == 'pm' and hour != 12:
                            hour += 12
                        elif period == 'am' and hour == 12:
                            hour = 0

                try:
                    date = datetime(year, month_num, day_num, hour, minute)
                    if date < datetime.now():
                        date = datetime(year + 1, month_num, day_num, hour, minute)
                    return date
                except ValueError:
                    pass
        except Exception:
            pass

        return self._default_date()
