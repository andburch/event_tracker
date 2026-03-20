"""
Raising Arizona Kids calendar scraper
Scrapes events from raisingarizonakids.com/calendar/ using LLM-based extraction.
WordPress /page/N/ pagination -- LLM follows up to 4 pages.
"""
from .base_scraper import BaseScraper


class RaisingArizonaKidsScraper(BaseScraper):
    """Scrape Raising Arizona Kids calendar via LLM extraction."""

    def __init__(self):
        super().__init__('raisingarizonakids')
        self.start_url = 'https://www.raisingarizonakids.com/calendar/'

    def scrape(self):
        print("Scraping Raising Arizona Kids...")
        events = self.llm_scrape_page(
            start_url=self.start_url,
            use_selenium=True,
            wait=8,
            max_pages=4,
            category='kids',
            default_venue='Phoenix, AZ',
            site_hint='Raising Arizona Kids family events calendar',
        )
        self.close_driver()
        print(f"Raising Arizona Kids: collected {len(events)} events")
        return events
