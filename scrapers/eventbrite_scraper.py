"""
Eventbrite scraper using Selenium to handle JavaScript
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import json

class EventbriteScraper(BaseScraper):
    """Scrape Eventbrite for Phoenix events using Selenium"""
    
    def __init__(self):
        super().__init__('eventbrite')
        self.base_url = 'https://www.eventbrite.com/d/az--phoenix/events/'
    
    def scrape(self):
        """Scrape events from Eventbrite Phoenix page"""
        events = []
        try:
            # Use Selenium to load the page with JavaScript
            html = self.get_page_selenium(self.base_url, wait_seconds=5)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try JSON-LD structured data first
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    
                    # Handle ItemList (Eventbrite uses this)
                    if isinstance(data, dict) and data.get('@type') == 'ItemList':
                        for item in data.get('itemListElement', []):
                            event_data = item.get('item', {})
                            if event_data:
                                event = self._parse_json_event(event_data)
                                if event:
                                    events.append(event)
                    
                    # Handle single Event
                    elif isinstance(data, dict) and data.get('@type') == 'Event':
                        event = self._parse_json_event(data)
                        if event:
                            events.append(event)
                    
                    # Handle list of events
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'Event':
                                event = self._parse_json_event(item)
                                if event:
                                    events.append(event)
                except:
                    continue
            
            # Parse HTML if no structured data
            if not events:
                events = self._parse_html_events(soup)
            
        except Exception as e:
            print(f"Error scraping Eventbrite: {e}")
        finally:
            self.close_driver()
        
        return events
    
    def _parse_json_event(self, data):
        """Parse event from JSON-LD"""
        try:
            title = data.get('name', '')
            description = data.get('description', '')
            url = data.get('url', '')
            
            # Try different date field names
            start_date = data.get('startDate', '') or data.get('start', '')
            if start_date:
                # Handle date-only format (YYYY-MM-DD)
                if 'T' in str(start_date):
                    date = datetime.fromisoformat(str(start_date).replace('Z', '+00:00'))
                    # Date only, no time in data - use sentinel
                    date = datetime.strptime(str(start_date), '%Y-%m-%d').replace(hour=12, minute=34)
            else:
                return None
            
            location = data.get('location', {})
            if isinstance(location, dict):
                venue = location.get('name', '') or location.get('address', {}).get('addressLocality', 'Phoenix, AZ')
            else:
                venue = str(location) if location else 'Phoenix, AZ'
            
            return self.normalize_event({
                'title': title,
                'description': description[:1000],
                'venue': venue,
                'date': date,
                'url': url,
                'category': 'general'
            })
        except Exception as e:
            return None
    
    def _parse_html_events(self, soup):
        """Parse events from HTML"""
        events = []
        
        # Look for event cards - Eventbrite uses various class names
        selectors = [
            'div[class*="event-card"]',
            'div[class*="EventCard"]',
            'article[class*="event"]',
            'div[data-testid*="event"]'
        ]
        
        event_cards = []
        for selector in selectors:
            event_cards = soup.select(selector)
            if event_cards:
                break
        
        for card in event_cards[:20]:
            try:
                # Extract title
                title_elem = card.select_one('h2, h3, [class*="title"], [class*="Title"]')
                title = title_elem.get_text(strip=True) if title_elem else 'Unknown Event'
                
                # Extract URL
                link = card.find('a', href=True)
                url = link['href'] if link else ''
                if url and not url.startswith('http'):
                    url = 'https://www.eventbrite.com' + url
                
                # Extract description
                desc_elem = card.select_one('p, [class*="description"], [class*="Description"]')
                description = desc_elem.get_text(strip=True)[:500] if desc_elem else 'Event in Phoenix'
                
                events.append(self.normalize_event({
                    'title': title,
                    'description': description,
                    'venue': 'Phoenix, AZ',
                    'date': datetime.now(),
                    'url': url,
                    'category': 'general'
                }))
            except:
                continue
        
        return events
