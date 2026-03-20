"""
Tempe.gov RSS feed scraper
Aggregates events from multiple Tempe city RSS feeds
"""
import feedparser
from datetime import datetime
from .base_scraper import BaseScraper
import re

class TempeGovScraper(BaseScraper):
    """Scrape events from Tempe.gov RSS feeds"""
    
    def __init__(self):
        super().__init__('tempe_gov')
        self.base_url = 'https://www.tempe.gov/Home/Components/RssFeeds/RssFeed/View?ctID=6&cateIDs='
        
        # RSS feed category IDs to scrape
        self.feed_categories = {
            '15': 'Community Events',
            '267': 'Family Fun',
            '29': 'Library',
            '129': 'Library Youth',
            '140': 'Arts Events',
            '338': 'Kid Zone',
            '34': 'Tempe Center for the Arts',
            '310': 'TCA Presents',
            '311': 'TCA Gallery',
            '36': 'Tempe History Museum',
            '125': 'Town Lake/Beach Park',
            '313': 'Mill Avenue Events',
            '321': 'Kiwanis Park Events'
        }
    
    def scrape(self):
        """Scrape events from all Tempe RSS feeds"""
        # Collect all entries across feeds first, then deduplicate by URL.
        # We track the best (most specific) category name per URL so that
        # e.g. an event in both "TCA Presents" and "Community Events" keeps
        # the more specific label.
        entries_by_url = {}  # url -> (entry, category_name)

        for category_id, category_name in self.feed_categories.items():
            try:
                feed_url = f"{self.base_url}{category_id}"
                feed = feedparser.parse(feed_url)
                count = 0
                for entry in feed.entries:
                    url = getattr(entry, 'link', None)
                    if not url:
                        continue
                    # Keep entry if not seen yet, or if this category is more specific
                    if url not in entries_by_url:
                        entries_by_url[url] = (entry, category_name)
                        count += 1
                print(f"  Tempe {category_name}: {len(feed.entries)} entries ({count} new)")
            except Exception as e:
                print(f"  Error fetching Tempe {category_name}: {e}")

        events = []
        for url, (entry, category_name) in entries_by_url.items():
            try:
                raw_title = entry.title if hasattr(entry, 'title') else 'Untitled Event'
                # Strip the appended date from title: "Event Name (03/18/2026 ...)"
                title = re.sub(r'\s*\(\d{1,2}/\d{1,2}/\d{4}.*?\)\s*$', '', raw_title).strip()
                if not title:
                    title = raw_title

                description = ''
                if hasattr(entry, 'summary'):
                    description = self._clean_html(entry.summary)
                elif hasattr(entry, 'description'):
                    description = self._clean_html(entry.description)

                date = self._parse_date(entry)
                venue = self._extract_venue(description, category_name)
                clean_desc = f"{category_name} | {description[:200]}" if description else category_name

                events.append(self.normalize_event({
                    'title': title,
                    'description': clean_desc,
                    'venue': venue,
                    'date': date,
                    'url': url,
                    'category': 'community'
                }))
            except Exception as e:
                print(f"  Error parsing entry: {e}")

        print(f"Total Tempe events collected: {len(events)}")
        return events
    
    def _clean_html(self, html_text):
        """Remove HTML tags and clean up text"""
        if not html_text:
            return ''
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_text)
        
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        
        # Clean up whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _parse_date(self, entry):
        """Parse date from RSS entry - date is always in the title parens"""
        if hasattr(entry, 'title'):
            # Pattern: "Event Name (03/12/2026 7:30 PM - 9:30 PM)"
            m = re.search(r'\((\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*(AM|PM))?\s*[-–]', entry.title)
            if m:
                try:
                    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    hour = int(m.group(4)) if m.group(4) else 12
                    minute = int(m.group(5)) if m.group(5) else 34
                    am_pm = m.group(6) if m.group(6) else None
                    if am_pm == 'PM' and hour != 12:
                        hour += 12
                    elif am_pm == 'AM' and hour == 12:
                        hour = 0
                    return datetime(year, month, day, hour, minute)
                except Exception:
                    pass

        # Last resort default
        from datetime import timedelta
        today = datetime.now()
        days_ahead = (5 - today.weekday()) % 7 or 7
        return today.replace(hour=12, minute=34, second=0, microsecond=0) + timedelta(days=days_ahead)
    
    def _extract_venue(self, description, category_name):
        """Extract venue from description or use category as fallback"""
        if not description:
            return f"Tempe, AZ - {category_name}"
        
        # Look for common venue patterns
        venue_patterns = [
            r'(?:at|@)\s+([A-Z][^,\.]+(?:Center|Library|Museum|Park|Arts|Hall|Theater|Theatre))',
            r'(?:Location|Venue):\s*([^,\.]+)',
        ]
        
        for pattern in venue_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                venue = match.group(1).strip()
                if len(venue) > 5 and len(venue) < 100:
                    return venue
        
        # Use category-specific defaults
        if 'Library' in category_name:
            return 'Tempe Public Library'
        elif 'TCA' in category_name or 'Center for the Arts' in category_name:
            return 'Tempe Center for the Arts'
        elif 'Museum' in category_name:
            return 'Tempe History Museum'
        elif 'Town Lake' in category_name or 'Beach Park' in category_name:
            return 'Tempe Town Lake'
        elif 'Mill Avenue' in category_name:
            return 'Mill Avenue District, Tempe'
        elif 'Kiwanis' in category_name:
            return 'Kiwanis Park, Tempe'
        
        return 'Tempe, AZ'
