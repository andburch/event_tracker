"""
The Dirty Drummer scraper
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re

class DirtyDrummerScraper(BaseScraper):
    """Scrape The Dirty Drummer events"""
    
    def __init__(self):
        super().__init__('dirtydrummer')
        self.base_url = 'https://www.thedirtydrummer.com/events'
    
    def scrape(self):
        """Scrape events from The Dirty Drummer"""
        events = []
        try:
            # Use Selenium for Squarespace site with longer wait
            page_source = self.get_page_selenium(self.base_url, wait_seconds=8)
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Look for noscript section which has the full event list with dates
            noscript = soup.find('noscript')
            if not noscript:
                print("Warning: No noscript section found, trying regular list items")
                event_items = soup.find_all('li')
            else:
                print("Found noscript section with event list")
                event_items = noscript.find_all('li')
            
            print(f"Found {len(event_items)} list items, filtering for events...")
            
            seen_titles = set()
            
            for item in event_items[:100]:
                try:
                    # Look for h1 with event title
                    title_elem = item.find(['h1', 'h2', 'h3'])
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    if len(title) < 3 or title in seen_titles:
                        continue
                    
                    seen_titles.add(title)
                    
                    # Find link
                    link = item.find('a', href=True)
                    if not link:
                        continue
                    
                    url = link.get('href', '')
                    if not url or url in ['/events', '/#featuredevents-section']:
                        continue
                    
                    if not url.startswith('http'):
                        url = 'https://www.thedirtydrummer.com' + url
                    
                    # Extract date - look for div with full date format in noscript section
                    date = None
                    all_divs = item.find_all('div')
                    for div in all_divs:
                        div_text = div.get_text(strip=True)
                        # Look for the full date pattern: "Friday, March 27, 2026, 9:00 PM"
                        if re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}\s+[AP]M', div_text):
                            date = self._parse_date('', '', div_text)
                            break
                    
                    # If no date found, use default
                    if not date:
                        date = self._parse_date('', '', item.get_text())
                    
                    # Extract description
                    desc_elem = item.find('p')
                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else title
                    
                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': 'The Dirty Drummer, Phoenix',
                        'date': date,
                        'url': url,
                        'category': 'music'
                    }))
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"Error scraping The Dirty Drummer: {e}")
        
        return events
    
    def _parse_date(self, date_text, time_text, full_text):
        """Parse date from text"""
        combined_text = f"{date_text} {time_text} {full_text}"
        
        # Pattern: "Friday, March 27, 2026, 9:00 PM" (full format with year)
        full_pattern = r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[.,]?\s+(\d{1,2}),\s+(\d{4}),\s+(\d{1,2}):(\d{2})\s+(AM|PM)'
        match = re.search(full_pattern, combined_text, re.IGNORECASE)
        
        if match:
            month_abbr = match.group(2)
            day = int(match.group(3))
            year = int(match.group(4))
            hour = int(match.group(5))
            minute = int(match.group(6))
            am_pm = match.group(7).upper()
            
            # Convert abbreviated month to full name
            month_map = {
                'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
                'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
                'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
            }
            month_name = month_map.get(month_abbr[:3].lower(), month_abbr)
            
            if am_pm == 'PM' and hour != 12:
                hour += 12
            elif am_pm == 'AM' and hour == 12:
                hour = 0
            
            try:
                date = datetime(year, datetime.strptime(month_name, "%B").month, day, hour, minute)
                return date
            except:
                pass
        
        # Pattern: "Saturday, Feb. 28" or "February 28"
        date_pattern = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[.,]?\s+(\d{1,2})(?:,?\s+(\d{4}))?'
        match = re.search(date_pattern, combined_text, re.IGNORECASE)
        
        if match:
            month_abbr = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else datetime.now().year
            
            # Convert abbreviated month to full name
            month_map = {
                'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
                'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
                'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
            }
            month_name = month_map.get(month_abbr[:3].lower(), month_abbr)
            
            # Extract time (e.g., "8:00 PM" or "8pm")
            time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)'
            time_match = re.search(time_pattern, combined_text, re.IGNORECASE)
            
            hour = 12  # Default 8 PM
            minute = 34
            
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                am_pm = time_match.group(3).upper()
                
                if am_pm == 'PM' and hour != 12:
                    hour += 12
                elif am_pm == 'AM' and hour == 12:
                    hour = 0
            
            try:
                date = datetime(year, datetime.strptime(month_name, "%B").month, day, hour, minute)
                # If date is in the past, assume next year
                if date < datetime.now():
                    date = date.replace(year=year + 1)
                return date
            except:
                pass
        
        # Default to next Saturday at 8 PM
        from datetime import timedelta
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        next_saturday = today.replace(hour=12, minute=34, second=0, microsecond=0)
        return next_saturday + timedelta(days=days_ahead)
