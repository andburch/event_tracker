"""
Phoenix.gov calendar scraper using Selenium
"""
from bs4 import BeautifulSoup
from datetime import datetime
from .base_scraper import BaseScraper
import re

class PhoenixGovScraper(BaseScraper):
    """Scrape Phoenix.gov calendar using Selenium"""
    
    def __init__(self):
        super().__init__('phoenix_gov')
        self.base_url = 'https://www.phoenix.gov/calendar.html'
    
    def scrape(self):
        """Scrape events from Phoenix.gov calendar with pagination"""
        events = []
        driver = None
        try:
            import time
            from selenium.webdriver.common.by import By
            from selenium.common.exceptions import TimeoutException
            
            driver = self.get_driver()
            driver.set_page_load_timeout(30)  # 30 second timeout
            
            print("Loading Phoenix.gov calendar...")
            try:
                driver.get(self.base_url)
            except TimeoutException:
                print("⚠️  Page load timeout, but continuing...")
            
            time.sleep(5)
            
            page_num = 1
            max_pages = 10  # Safety limit
            
            while page_num <= max_pages:
                print(f"Scraping page {page_num}...")
                
                # Scroll down a bit to ensure content is loaded
                for i in range(2):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Find all event cards on this page
                event_cards = soup.find_all('div', class_='cmp-event-card-search__card')
                print(f"  Found {len(event_cards)} events on page {page_num}")
                
                for card in event_cards:
                    try:
                        # Extract title and URL from h2 > a
                        title_elem = card.find('h2')
                        if not title_elem:
                            continue
                        
                        link = title_elem.find('a', href=True)
                        if not link:
                            continue
                        
                        title = link.get_text(strip=True)
                        url = link.get('href', '')
                        if url and not url.startswith('http'):
                            url = 'https://www.phoenix.gov' + url
                        
                        # Get all text from the card
                        text_content = card.get_text()
                        
                        # Extract date - format: "Tuesday, March 10, 2026"
                        date_text = ''
                        date_match = re.search(
                            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+)\s+(\d{1,2}),\s+(\d{4})',
                            text_content,
                            re.IGNORECASE
                        )
                        if date_match:
                            date_text = date_match.group(0)
                        
                        # Extract time - format: "8:00 AM - 2:00 PM"
                        time_text = ''
                        time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)', text_content, re.IGNORECASE)
                        if time_match:
                            time_text = time_match.group(0)
                        
                        # Parse date
                        date = self._parse_date(date_text, time_text)
                        
                        # Extract location - look for address patterns
                        location = 'Phoenix, AZ'
                        location_patterns = [
                            r'([^,\n]+,\s*\d+[^,\n]+(?:St\.|Street|Ave\.|Avenue|Rd\.|Road|Way|Blvd\.|Boulevard)[^,\n]*)',
                            r'(\d+\s+[NSEW]\.?\s+[^,\n]+(?:St\.|Street|Ave\.|Avenue|Rd\.|Road|Way|Blvd\.|Boulevard))',
                            r'([A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:Center|Library|College|Building|Hall|Room))'
                        ]
                        for pattern in location_patterns:
                            loc_match = re.search(pattern, text_content, re.IGNORECASE)
                            if loc_match:
                                location = loc_match.group(1).strip()
                                break
                        
                        # Extract category from byline
                        byline = card.find('div', class_='cmp-byline')
                        category = ''
                        if byline:
                            category_text = byline.get_text(strip=True)
                            if category_text:
                                category = category_text
                        
                        # Build better description
                        desc_parts = []
                        if category:
                            desc_parts.append(f"Category: {category}")
                        if time_text:
                            desc_parts.append(f"Time: {time_text}")
                        if location and location != 'Phoenix, AZ':
                            desc_parts.append(f"Location: {location}")
                        
                        description = ' | '.join(desc_parts) if desc_parts else f'City of Phoenix event'
                        
                        events.append(self.normalize_event({
                            'title': title,
                            'description': description,
                            'venue': location,
                            'date': date,
                            'url': url,
                            'category': 'government'
                        }))
                        
                    except Exception as e:
                        print(f"  Error parsing event: {e}")
                        continue
                
                # Try to click Next button
                try:
                    next_buttons = driver.find_elements(By.CSS_SELECTOR, "a.cmp-searchCustom__pagination-btn")
                    
                    if len(next_buttons) >= 2:
                        next_btn = next_buttons[1]  # Second button is Next
                        is_disabled = next_btn.get_attribute('disabled')
                        
                        if is_disabled:
                            print(f"  Reached last page (page {page_num})")
                            break
                        
                        # Click Next
                        driver.execute_script("arguments[0].click();", next_btn)
                        time.sleep(3)
                        page_num += 1
                    else:
                        print("  No pagination buttons found")
                        break
                        
                except Exception as e:
                    print(f"  Error with pagination: {e}")
                    break
            
        except Exception as e:
            print(f"Error scraping Phoenix.gov: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        
        return events
    
    def _parse_date(self, date_text, time_text):
        """Parse date from text like 'Tuesday, March 10, 2026' and '8:00 AM - 2:00 PM'"""
        try:
            if not date_text:
                return datetime.now()
            
            # Pattern: "Tuesday, March 10, 2026"
            date_match = re.search(
                r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+)\s+(\d{1,2}),\s+(\d{4})',
                date_text,
                re.IGNORECASE
            )
            
            if not date_match:
                return datetime.now()
            
            month_name = date_match.group(2)
            day = int(date_match.group(3))
            year = int(date_match.group(4))
            
            # Parse time - get start time from "8:00 AM - 2:00 PM"
            hour = 12  # Default sentinel (12:34 = no real time found)
            minute = 34
            
            if time_text:
                time_match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_text, re.IGNORECASE)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    am_pm = time_match.group(3).upper()
                    
                    if am_pm == 'PM' and hour != 12:
                        hour += 12
                    elif am_pm == 'AM' and hour == 12:
                        hour = 0
            
            # Create datetime
            month = datetime.strptime(month_name, "%B").month
            return datetime(year, month, day, hour, minute)
            
        except Exception as e:
            print(f"Error parsing date '{date_text}' '{time_text}': {e}")
            return datetime.now()
