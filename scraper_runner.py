"""
scraper_runner.py -- Orchestrates all legacy BeautifulSoup/Selenium scrapers.

Iterates over every scraper in the SCRAPERS registry, saves new events to the
database, logs a ScraperRun audit record for each, then runs batch LLM scoring.

Usage:
    python scraper_runner.py              # run all scrapers
    python scraper_runner.py <source>     # run one scraper by source_name
"""
import sys
import time
from scrapers import SCRAPERS
from database.models import Session, Event, ScraperRun
from datetime import datetime
from recommender.llm_filter import run_batch_scoring

def run_scrapers(scraper_name=None):
    """Run scrapers and save events to database
    
    Args:
        scraper_name: Optional specific scraper to run (e.g., 'mesa_gov', 'tempe_gov')
                     If None, runs all scrapers
    """
    session = Session()
    
    # Filter scrapers if specific one requested
    scrapers_to_run = SCRAPERS
    if scraper_name:
        scrapers_to_run = [s for s in SCRAPERS if s.source_name == scraper_name]
        if not scrapers_to_run:
            print(f"Scraper '{scraper_name}' not found.")
            print(f"Available scrapers: {', '.join(s.source_name for s in SCRAPERS)}")
            session.close()
            return
    
    for scraper in scrapers_to_run:
        print(f"Running {scraper.source_name} scraper...")
        
        # Track scraper run
        start_time = time.time()
        events_found = 0
        events_added = 0
        success = False
        error_message = None
        
        try:
            events = scraper.scrape()
            events_found = len(events)
            
            for event_data in events:
                # Check if event already exists
                existing = session.query(Event).filter_by(
                    title=event_data['title'],
                    date=event_data['date']
                ).first()
                
                if not existing:
                    event = Event(**event_data)
                    session.add(event)
                    events_added += 1
            
            session.commit()
            success = True
            print(f"Added {events_added} events from {scraper.source_name} ({events_found} found)")
            
        except Exception as e:
            error_message = str(e)
            print(f"Error with {scraper.source_name}: {e}")
            session.rollback()
        
        # Log the scraper run
        duration = time.time() - start_time
        scraper_run = ScraperRun(
            source=scraper.source_name,
            run_timestamp=datetime.utcnow(),
            events_found=events_found,
            events_added=events_added,
            success=success,
            error_message=error_message,
            duration_seconds=duration
        )
        session.add(scraper_run)
        session.commit()
    
    session.close()

    # After all scrapers finish, re-score all future events in one batch call
    print("\nRunning batch event scoring...")
    run_batch_scoring()

if __name__ == '__main__':
    scraper_name = sys.argv[1] if len(sys.argv) > 1 else None
    run_scrapers(scraper_name)
