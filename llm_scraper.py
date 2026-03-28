"""
llm_scraper.py -- Production LLM-based event scraper

Imports all fetch/LLM/site logic from llm_scrape_core. This file only
contains DB persistence, date parsing, and the CLI entry point.

Usage:
    python llm_scraper.py              # purge events + scrape all sites
    python llm_scraper.py --no-purge   # append to existing events
    python llm_scraper.py <key> [<key2> ...]  # scrape specific sites only
    python llm_scraper.py list         # show all site keys

After scraping, runs LLM batch scoring automatically.
"""

import sys, time
from datetime import datetime, timedelta, date as date_type
from database.models import Session, Event, ScraperRun
from recommender.llm_filter import run_batch_scoring
from llm_scrape_core import (
    fetch_requests, fetch_selenium, close_driver,
    clean_html, ask_llm, SITES,
)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(date_str, time_str):
    """
    Convert LLM-returned date/time strings to a datetime object.
    
    Expects dates in YYYY-MM-DD format as requested in the LLM prompt.
    Falls back to today at 12:34 (sentinel time) if parsing fails.
    """
    if not date_str:
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

    date_str = date_str.strip()
    
    # Primary format: YYYY-MM-DD (as requested from LLM)
    try:
        if time_str:
            combined = f"{date_str} {time_str.strip()}"
            # Try with time first
            for time_fmt in ['%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %H:%M']:
                try:
                    return datetime.strptime(combined, time_fmt)
                except ValueError:
                    continue
        
        # Date only - use noon as default time
        return datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12, minute=0)
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

def scrape_and_save(key, name, start_url, use_selenium, wait, max_pages, session):
    """
    Scrape one site via LLM extraction and save new events to the database.

    Returns:
        (events_found, events_added, success, error_message)
    """
    all_events    = []
    error_message = None
    success       = True
    
    # Special handling for calendar-based sites that need multiple months
    if key == 'dirtydrummer':
        urls_to_scrape = []
        
        # Current month and next 2 months
        base_date = datetime.now()
        for i in range(3):
            month_date = base_date + timedelta(days=30*i)
            month_str = month_date.strftime('%m-%Y')
            url = f"https://www.thedirtydrummer.com/events?view=calendar&month={month_str}"
            urls_to_scrape.append(url)
        
        print(f"  Multi-month scraping: {len(urls_to_scrape)} months")
        
        for month_num, url in enumerate(urls_to_scrape, 1):
            print(f"  Month {month_num}: {url}")
            try:
                html = fetch_selenium(url, wait) if use_selenium else fetch_requests(url)
                text = clean_html(html)
                print(f"    text={len(text)} chars", end='  ')
                
                result = ask_llm(text, current_url=url, site_hint=name)
                page_events = result.get('events', [])
                all_events.extend(page_events)
                print(f"events={len(page_events)}")
                
                if month_num < len(urls_to_scrape):
                    time.sleep(2)
                    
            except Exception as e:
                print(f"\n    ERROR on month {month_num}: {e}")
                if month_num == 1:  # If first month fails, mark as failure
                    success = False
                    error_message = str(e)
    else:
        # Standard pagination-based scraping for other sites
        current_url   = start_url
        visited       = set()
        page_num      = 0

        # Standard pagination-based scraping for other sites
        current_url   = start_url
        visited       = set()
        page_num      = 0

        try:
            while current_url and page_num < max_pages:
                page_num += 1
                if current_url in visited:
                    print(f"    loop detected, stopping")
                    break
                visited.add(current_url)

                print(f"  page {page_num}: {current_url[:80]}")
                try:
                    html = fetch_selenium(current_url, wait) if use_selenium else fetch_requests(current_url)
                except Exception as e:
                    print(f"    FETCH ERROR: {e}")
                    break

                text = clean_html(html)
                print(f"    text={len(text)} chars", end='  ')

                try:
                    result = ask_llm(text, current_url=current_url, site_hint=name)
                except Exception as e:
                    print(f"\n    LLM ERROR: {e}")
                    break

                page_events = result.get('events', [])
                next_url    = result.get('next_page_url')
                all_events.extend(page_events)
                print(f"events={len(page_events)}  next={next_url or 'null'}")

                if next_url and not next_url.startswith('http'):
                    break
                current_url = next_url
                if current_url:
                    time.sleep(2)

        except Exception as e:
            success       = False
            error_message = str(e)
            print(f"  ERROR: {e}")

    # Save to database
    events_added = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for ev in all_events:
        event_dt = parse_date(ev.get('date'), ev.get('time'))
        title    = (ev.get('title') or '').strip()
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

        # Skip events with past dates (single-date events that already happened)
        if event_dt < today:
            continue

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
        for k, (name, url, use_sel, wait, max_pages, note, _color) in SITES.items():
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
            name, url, use_sel, wait, max_pages, note, _color = SITES[key]
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")

            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, session
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

    print("\nRunning batch event scoring...")
    run_batch_scoring()


if __name__ == '__main__':
    main()
