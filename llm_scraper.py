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
from database.models import Session, Event, ScraperRun, utcnow
from scrape.core import close_driver
from scrape.pagination import scrape_with_pagination
from sources import SITES


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """
    Convert LLM-returned date/time strings to a datetime object.
    
    Expects dates in YYYY-MM-DD format as requested in the LLM prompt.
    Returns None if there is no parseable date (the caller skips the event).
    No/unparseable time -> sentinel time 12:34 ("no time given").
    
    Args:
        date_str: Date string in YYYY-MM-DD format (or None)
        time_str: Time string like "8:00 PM" (or None)
    
    Returns:
        datetime object with parsed date/time, or fallback with sentinel time
    """
    if not date_str:
        return None   # no date: skip the event rather than show it as "today"

    date_str = date_str.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]', date_str):   # "2026-12-01T19:00" -> date part only
        date_str = date_str[:10]
    
    # Primary format: YYYY-MM-DD (as requested from LLM)
    try:
        if time_str:
            # Take only the start time from ranges like "1:30 PM - 3:00 PM"
            time_str = re.split(r'[-\u2013\u2014]', time_str)[0].strip()
            # Normalize various am/pm formats to "H:MM AM/PM"
            # Handles: "1:30pm", "1:30 p.m.", "1:30 P.M.", etc.
            time_str = re.sub(r'\s*p\.m\.', ' PM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'\s*a\.m\.', ' AM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'(\d)(am|pm)$', lambda m: m.group(1) + ' ' + m.group(2).upper(), time_str, flags=re.IGNORECASE)
            m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\.?', time_str, re.IGNORECASE)
            if m:   # e.g. "10:00 a.m. AZ Time", "7 PM", "7pm" -> "10:00 AM", "7:00 PM"
                time_str = f"{m.group(1)}:{m.group(2) or '00'} {m.group(3).upper()}M"
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

    # Unparseable date: skip the event (previously it was shown as today, which was misleading)
    return None


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
    session,
    provider: str = None,
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
            key, name, start_url, use_selenium, wait, max_pages, pagination_config,
            provider=provider,
        )
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"  ERROR: {e}")
        all_events = []

    # Save to database, tracking skip reasons for run summary
    events_added = 0
    skipped_past = 0
    skipped_no_title = 0
    skipped_bad_date = 0
    skipped_duplicate = 0
    missing_url = 0
    missing_time = 0
    missing_venue = 0
    month_counts = {}
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for ev in all_events:
        time_str = ev.get('time')
        # "12:00 AM" is almost always a site placeholder (e.g. "12:00 am - 12:00 pm"), not a real start time
        if time_str and re.match(r'^\s*12:00\s*a\.?m', time_str, re.IGNORECASE):
            time_str = None
        # Multi-week runs (exhibits) list daily opening HOURS ("9:00 AM - 5:00 PM"), not a start time: store as
        # "no time" (All day). A single time ("7:30 PM", e.g. a theater run's curtain) is kept.
        try:
            if time_str and re.search(r'[-\u2013\u2014]|\bto\b', time_str) and ev.get('end_date') and ev.get('date') and \
               (datetime.strptime(ev['end_date'].strip()[:10], '%Y-%m-%d') - datetime.strptime(ev['date'].strip()[:10], '%Y-%m-%d')).days >= 7:
                time_str = None
        except ValueError:
            pass
        event_dt = parse_date(ev.get('date'), time_str)
        try:
            if event_dt and ev.get('end_date'):
                end_dt = datetime.strptime(ev['end_date'].strip()[:10], '%Y-%m-%d')
                if end_dt < event_dt.replace(hour=0, minute=0) and event_dt.replace(year=event_dt.year - 1) <= end_dt + timedelta(days=1):
                    event_dt = event_dt.replace(year=event_dt.year - 1)   # model moved a running range's start a year ahead
        except ValueError:
            pass
        title = (ev.get('title') or '').strip()
        if not title:
            skipped_no_title += 1
            continue
        if event_dt is None:
            skipped_bad_date += 1
            continue

        # Track data quality
        if not (ev.get('url') or '').strip():
            missing_url += 1
        if not ev.get('time'):
            missing_time += 1
        if not (ev.get('venue') or '').strip():
            missing_venue += 1

        # Handle date range events: if start is past but end is future, use today
        end_date_str = ev.get('end_date')
        is_ongoing = False
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')
                if event_dt < today and end_dt >= today:
                    # Currently running: show it today, keeping its time (or the
                    # 12:34 "no time" sentinel) instead of a fake midnight start.
                    event_dt = today.replace(hour=event_dt.hour, minute=event_dt.minute)
                    is_ongoing = True
            except ValueError:
                pass

        # Skip past events (before today), unless it's an ongoing event
        if event_dt < today and not is_ongoing:
            skipped_past += 1
            continue

        # Month distribution (for future/current events only)
        month_key = event_dt.strftime('%Y-%m')
        month_counts[month_key] = month_counts.get(month_key, 0) + 1

        existing = session.query(Event).filter_by(title=title, date=event_dt).first()
        if not existing:
            day0 = event_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            same_day = session.query(Event).filter(Event.title == title, Event.date >= day0,
                                                   Event.date < day0 + timedelta(days=1)).all()
            no_time = (event_dt.hour, event_dt.minute) == (12, 34)
            if no_time and same_day:
                existing = same_day[0]                        # we already have it (with a time): skip
            elif not no_time:
                placeholder = next((e for e in same_day if (e.date.hour, e.date.minute) == (12, 34)), None)
                if placeholder:                               # upgrade the no-time copy instead of adding
                    placeholder.date = event_dt
                    existing = placeholder
        if existing:
            skipped_duplicate += 1
        else:
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

    # Append DB-side stats to the run summary artifact
    try:
        import json, os
        from scrape import artifacts as artifact_store
        summary_file = os.path.join(artifact_store.ARTIFACT_ROOT, key, 'run_summary.json')
        if os.path.exists(summary_file):
            with open(summary_file) as f:
                summary = json.load(f)
        else:
            summary = {}
        summary['run_timestamp'] = datetime.now().isoformat()
        summary['events_added'] = events_added
        summary['skipped'] = {
            'past': skipped_past,
            'duplicate': skipped_duplicate,
            'no_title': skipped_no_title,
            'bad_date': skipped_bad_date,
        }
        summary['month_distribution'] = dict(sorted(month_counts.items()))
        summary['data_quality'] = {
            'missing_url': missing_url,
            'missing_time': missing_time,
            'missing_venue': missing_venue,
        }
        artifact_store.save(key, 'run_summary.json', json.dumps(summary, indent=2))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Run summary update failed: {e}")

    return len(all_events), events_added, success, error_message


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args     = sys.argv[1:]
    no_purge = '--no-purge' in args
    args     = [a for a in args if a != '--no-purge']

    # Optional --provider flag: --provider groq  or  --provider ollama
    provider = None
    if '--provider' in args:
        idx = args.index('--provider')
        if idx + 1 < len(args):
            provider = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

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
            pinned_count = session.query(Event).filter(Event.pinned == True).count()
            count = session.query(Event).filter(Event.pinned != True).delete()
            session.commit()
            msg = f"Purged {count} existing events from database."
            if pinned_count:
                msg += f" ({pinned_count} pinned events preserved)"
            print(f"{msg}\n")
        elif no_purge:
            print("--no-purge: appending to existing events.\n")

        total_found = 0
        total_added = 0
        failed_sites = []

        for key in keys:
            name, url, use_sel, wait, max_pages, note, _color, pagination_config = SITES[key]
            # Resolve dynamic date placeholders (e.g. {today}, {plus90}).
            # Other placeholders like {month_name} belong to the pagination
            # engine and must pass through untouched.
            from sources import _today, _plus90, _today_long
            class _PassThrough(dict):
                def __missing__(self, key):
                    return '{' + key + '}'
            url = url.format_map(_PassThrough(
                today=_today(), plus90=_plus90(), today_long=_today_long(),
            ))
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")

            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, pagination_config, session,
                provider=provider,
            )
            duration     = time.time() - start_time
            total_found += found
            total_added += added
            if not success:
                failed_sites.append(key)

            print(f"  -> {added} new events added ({found} found) in {duration:.0f}s")

            session.add(ScraperRun(
                source=key,
                run_timestamp=utcnow(),
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
        if failed_sites:
            print(f"FAILED SITES: {', '.join(failed_sites)}")
        print(f"{'='*60}")

        # Exit non-zero only for a systemic failure (every site errored, or the
        # whole run found nothing) so one flaky site doesn't page every day.
        exit_code = 1 if (len(failed_sites) == len(keys) or total_found == 0) else 0

    finally:
        close_driver()
        session.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
