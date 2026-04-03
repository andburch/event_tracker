"""
llm_scraper.py -- Production LLM-based event scraper

Imports all fetch/LLM/site logic from llm_scrape_core. This file only
contains DB persistence, date parsing, and the CLI entry point.

Uses pagination_engine for all scraping - no site-specific code here.

Usage:
    python llm_scraper.py              # scrape all sites
    python llm_scraper.py --no-purge   # append to existing events
    python llm_scraper.py <key> [<key2> ...]  # scrape specific sites only
    python llm_scraper.py list         # show all site keys

Run scoring separately after scraping:
    python score_events.py
"""

import sys, time, re
from datetime import datetime, timedelta, date as date_type
from database.models import Session, Event, ScraperRun
from llm_scrape_core import close_driver
from pagination_engine import scrape_with_pagination
from sources import SITES


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """
    Convert LLM-returned date/time strings to a datetime object.
    
    Expects dates in YYYY-MM-DD format as requested in the LLM prompt.
    Falls back to today at 12:34 (sentinel time) if parsing fails.
    
    Args:
        date_str: Date string in YYYY-MM-DD format (or None)
        time_str: Time string like "8:00 PM" (or None)
    
    Returns:
        datetime object with parsed date/time, or fallback with sentinel time
    """
    if not date_str:
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

    date_str = date_str.strip()
    
    # Primary format: YYYY-MM-DD (as requested from LLM)
    try:
        if time_str:
            # Take only the start time from ranges like "1:30 PM - 3:00 PM"
            time_str = time_str.split('-')[0].strip()
            # Normalize various am/pm formats to "H:MM AM/PM"
            # Handles: "1:30pm", "1:30 p.m.", "1:30 P.M.", etc.
            time_str = re.sub(r'\s*p\.m\.', ' PM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'\s*a\.m\.', ' AM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'(\d)(am|pm)$', lambda m: m.group(1) + ' ' + m.group(2).upper(), time_str, flags=re.IGNORECASE)
            combined = f"{date_str} {time_str}"
            # Try with time first
            for time_fmt in ['%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %H:%M']:
                try:
                    return datetime.strptime(combined, time_fmt)
                except ValueError:
                    continue
        
        # Date only - use sentinel time 12:34 to indicate no time was found
        return datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12, minute=34)
    except ValueError:
        pass
    
    # Fallback: try legacy formats in case LLM doesn't follow instructions
    legacy_formats = [
        '%B %d, %Y', '%b %d, %Y', '%A, %B %d, %Y', '%A, %b %d, %Y',
        '%m/%d/%Y', '%Y-%m-%d'
    ]
    
    for fmt in legacy_formats:
        try:
            return datetime.strptime(date_str, fmt).replace(hour=12, minute=34)
        except ValueError:
            continue

    # Ultimate fallback
    return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Scrape + save
# ---------------------------------------------------------------------------

def scrape_and_save(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    pagination_config: dict | None,
    session
) -> tuple[int, int, bool, str | None]:
    """
    Scrape one site via pagination engine and save new events to the database.
    
    This function is now a thin wrapper around pagination_engine.scrape_with_pagination().
    All pagination logic has been moved to the engine - this just handles DB persistence.

    Args:
        key: Site key from SITES dict (e.g., 'fibber', 'mesa')
        name: Display name for the site
        start_url: Starting URL to scrape
        use_selenium: Whether to use Selenium (True) or requests (False)
        wait: Seconds to wait after page load
        max_pages: Maximum number of pages to scrape
        pagination_config: Pagination configuration dict (or None for default)
        session: SQLAlchemy session for database operations

    Returns:
        Tuple of (events_found, events_added, success, error_message)
    """
    error_message = None
    success = True
    
    try:
        # Delegate all scraping to the pagination engine
        all_events = scrape_with_pagination(
            key, name, start_url, use_selenium, wait, max_pages, pagination_config
        )
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"  ERROR: {e}")
        all_events = []

    # Save to database
    events_added = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for ev in all_events:
        event_dt = parse_date(ev.get('date'), ev.get('time'))
        title = (ev.get('title') or '').strip()
        if not title:
            continue

        # Handle date range events: if start is past but end is future, use today
        end_date_str = ev.get('end_date')
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')
                if event_dt < today and end_dt >= today:
                    event_dt = today  # Currently running - use today
            except ValueError:
                pass

        existing = session.query(Event).filter_by(title=title, date=event_dt).first()
        if not existing:
            url = (ev.get('url') or '').strip()
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(start_url, url)

            session.add(Event(
                title=title,
                description=(ev.get('description') or '').strip(),
                venue=(ev.get('venue') or '').strip(),
                date=event_dt,
                url=url,
                source=key,
                category='general',
            ))
            events_added += 1

    session.commit()
    return len(all_events), events_added, success, error_message


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args     = sys.argv[1:]
    no_purge = '--no-purge' in args
    args     = [a for a in args if a != '--no-purge']
    target   = args[0] if args else None

    if target == 'list':
        print(f"{'KEY':<18} {'FETCH':<10} {'PAGES':<7} URL")
        print('-' * 80)
        for k, (name, url, use_sel, wait, max_pages, note, _color, _pagination) in SITES.items():
            sel  = 'selenium' if use_sel else 'requests'
            flag = f'  [{note}]' if note else ''
            print(f"  {k:<16} {sel:<10} max={max_pages}  {url[:55]}{flag}")
        sys.exit(0)

    if not target or target == 'all':
        keys = list(SITES)
    elif all(a in SITES for a in args):
        keys    = args
        unknown = [k for k in keys if k not in SITES]
        if unknown:
            print(f"Unknown site(s): {', '.join(unknown)}")
            print(f"Valid keys: {', '.join(SITES)}")
            sys.exit(1)
    else:
        print(f"Unknown site '{target}'. Run with 'list' to see valid keys.")
        sys.exit(1)

    session = Session()

    try:
        if not no_purge and (not target or target == 'all'):
            count = session.query(Event).delete()
            session.commit()
            print(f"Purged {count} existing events from database.\n")
        elif no_purge:
            print("--no-purge: appending to existing events.\n")

        total_found = 0
        total_added = 0

        for key in keys:
            name, url, use_sel, wait, max_pages, note, _color, pagination_config = SITES[key]
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")

            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, pagination_config, session
            )
            duration     = time.time() - start_time
            total_found += found
            total_added += added

            print(f"  -> {added} new events added ({found} found) in {duration:.0f}s")

            session.add(ScraperRun(
                source=key,
                run_timestamp=datetime.utcnow(),
                events_found=found,
                events_added=added,
                success=success,
                error_message=error,
                duration_seconds=duration,
            ))
            session.commit()

            if key != keys[-1]:
                time.sleep(3)

        print(f"\n{'='*60}")
        print(f"DONE: {total_added} new events added ({total_found} found across {len(keys)} sites)")
        print(f"{'='*60}")

    finally:
        close_driver()
        session.close()


if __name__ == '__main__':
    main()
