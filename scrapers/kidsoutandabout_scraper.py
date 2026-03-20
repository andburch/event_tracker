"""
Kids Out and About Phoenix scraper
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re

class KidsOutAndAboutScraper(BaseScraper):
    """Scrape Kids Out and About Phoenix events"""
    
    def __init__(self):
        super().__init__('kidsoutandabout')
        self.base_url = 'https://phoenix.kidsoutandabout.com/'
    
    def scrape(self):
        """Scrape events from Kids Out and About"""
        events = []
        try:
            # Use Selenium for JavaScript-heavy site
            page_source = self.get_page_selenium(self.base_url, wait_seconds=5)
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find event listings - Drupal views-row pattern
            event_items = soup.find_all(class_=lambda x: x and 'views-row' in str(x))
            
            print(f"Found {len(event_items)} Kids Out and About events")
            
            seen_urls = set()
            
            for item in event_items:
                try:
                    full_text = item.get_text(strip=True)
                    
                    # Extract title - first line before description
                    title = self._extract_title(full_text)
                    if not title or len(title) < 5:
                        continue
                    
                    # Extract URL
                    link = item.find('a', href=True)
                    if not link:
                        continue
                    
                    url = link['href']
                    if not url.startswith('http'):
                        url = 'https://phoenix.kidsoutandabout.com' + url
                    
                    # Skip duplicates
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # Extract date
                    date_elem = item.find(class_=lambda x: x and 'date' in str(x).lower())
                    date_text = date_elem.get_text(strip=True) if date_elem else ''
                    
                    # Parse date
                    date = self._parse_date_from_text(date_text)
                    
                    # Extract description (text after title)
                    description = self._extract_description(full_text, title)
                    
                    # Extract price
                    price = self._extract_price(full_text)
                    
                    # Venue defaults to Phoenix area
                    venue = 'Phoenix, AZ'
                    
                    events.append(self.normalize_event({
                        'title': title,
                        'description': description,
                        'venue': venue,
                        'date': date,
                        'url': url,
                        'category': 'kids',
                        'price': price
                    }))
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"Error scraping Kids Out and About: {e}")
        
        return events
    
    def _extract_title(self, text):
        """Extract title from event text"""
        # Title is usually before "This" or "Come" or similar
        match = re.search(r'^(.+?)(?:This |Come |The |Join |Put on )', text)
        if match:
            title = match.group(1).strip()
            # Remove trailing punctuation
            title = re.sub(r'[:\-]+$', '', title).strip()
            return title
        
        # Fallback: get first line
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for line in lines:
            if line and not line.startswith('Dates:') and len(line) > 10 and len(line) < 100:
                if not re.match(r'^\d{2}/\d{2}/\d{4}', line):
                    return line
        
        return None
    
    def _extract_description(self, full_text, title):
        """Extract description from event text"""
        if not title:
            return full_text[:300]
        
        # Get text after title
        desc_start = full_text.find(title) + len(title)
        description = full_text[desc_start:desc_start+300].strip()
        
        # Remove date info
        description = re.sub(r'Dates:\d{2}/\d{2}/\d{4}.*?(?=\s[A-Z]|$)', '', description, flags=re.DOTALL)
        description = re.sub(r'Show more dates.*?Hide these dates.*?(?=\s[A-Z]|$)', '', description, flags=re.DOTALL)
        
        return description.strip()[:300]
    
    def _extract_price(self, text):
        """Extract price from text"""
        text_lower = text.lower()
        
        # Check for free
        if re.search(r'\bfree\b', text_lower):
            return 'Free'
        
        # Check for price patterns
        price_match = re.search(r'\$(\d+(?:\.\d{2})?)\s*-\s*\$(\d+(?:\.\d{2})?)', text)
        if price_match:
            return f"${price_match.group(1)}-${price_match.group(2)}"
        
        price_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
        if price_match:
            return f"${price_match.group(1)}"
        
        # Check for donation
        if 'donation' in text_lower:
            return 'Donation'
        
        return None
    
    def _parse_date_from_text(self, date_text):
        """Parse date from text - format: 03/14/2026"""
        # Pattern: MM/DD/YYYY
        date_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', date_text)
        
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = int(date_match.group(3))
            
            try:
                # Default to 10 AM for kids events
                return datetime(year, month, day, 12, 34)
            except:
                pass
        
        # Default to next Saturday at 10 AM
        from datetime import timedelta
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        return today.replace(hour=12, minute=34, second=0, microsecond=0) + timedelta(days=days_ahead)
