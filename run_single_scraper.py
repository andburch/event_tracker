"""
run_single_scraper.py — Lightweight utility for running one scraper and upserting results.

Unlike scraper_runner.py, this script:
  - Does NOT write ScraperRun audit records (keeps health dashboard clean during dev)
  - Does NOT trigger batch scoring afterward
  - Uses (title, date, source) as the dedup key instead of just (title, date),
    so you can re-run without worrying about cross-source collisions

Usage
-----
    python run_single_scraper.py downtown_tempe
    python run_single_scraper.py raisingarizonakids
    python run_single_scraper.py mesa_gov

Add new scrapers to the `scrapers` dict at the bottom of this file.
"""

import sys
from database.models import Session, Event


def run(scraper):
    """
    Scrape events and upsert new ones into the DB.

    Args:
        scraper: An instantiated scraper object (must implement scrape()).
    """
    session = Session()
    events = scraper.scrape()
    added = 0

    for e in events:
        # Dedup by (title, date, source) — tighter than scraper_runner's (title, date)
        # so re-running the same scraper twice doesn't add duplicates.
        exists = session.query(Event).filter_by(
            title=e['title'],
            date=e['date'],
            source=e['source'],
        ).first()

        if not exists:
            session.add(Event(
                title=e['title'],
                description=e.get('description', ''),
                venue=e.get('venue', ''),
                date=e['date'],
                url=e.get('url', ''),
                source=e['source'],
                category=e.get('category', 'general'),
                # score intentionally left NULL — run batch scoring separately if needed
            ))
            added += 1

    session.commit()
    session.close()
    print(f"Done: {added}/{len(events)} new events added")


if __name__ == '__main__':
    # Import scrapers here (not at module level) so this file can be imported
    # without triggering Selenium initialization.
    from scrapers.downtown_tempe_scraper import DowntownTempeScraper
    from scrapers.raisingarizonakids_scraper import RaisingArizonaKidsScraper
    from scrapers.mesa_gov_scraper import MesaGovScraper

    # Map CLI name -> scraper class. Add new entries here as needed.
    scrapers = {
        'downtown_tempe':    DowntownTempeScraper,
        'raisingarizonakids': RaisingArizonaKidsScraper,
        'mesa_gov':          MesaGovScraper,
    }

    name = sys.argv[1] if len(sys.argv) > 1 else 'downtown_tempe'

    if name not in scrapers:
        print(f"Unknown scraper: {name}")
        print(f"Options: {list(scrapers)}")
        sys.exit(1)

    run(scrapers[name]())
