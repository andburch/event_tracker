"""
enhance_descriptions.py — Enrich music event descriptions with genre info via Groq web search.

Uses Groq's compound-beta model (which has built-in web search / tool use) to look up
musical acts that have no real description and writes a short genre/style blurb back
into Event.description.

Which events get enriched
-------------------------
An event qualifies if ALL of the following are true:
  1. source is one of the music venue sources (fibbermagees, yuccatap, dirtydrummer)
  2. description is blank, None, or identical to the title (scraper fallback)
  3. The event is in the future (no point enriching past events)

Usage
-----
Dry run (print what would be updated, don't write to DB):
    python enhance_descriptions.py --dry-run

Enrich up to 20 events:
    python enhance_descriptions.py --limit 20

Enrich a specific source only:
    python enhance_descriptions.py --source fibbermagees

Enrich everything that qualifies:
    python enhance_descriptions.py

Notes
-----
- compound-beta is a Groq model with web search tool use built in. It will search
  the web for the artist name and return genre/style information.
- Rate limiting: we sleep 3s between calls to stay under free-tier limits.
- SSL verification is disabled (corporate firewall).
- This script is intentionally standalone — it does NOT run automatically as part
  of scraper_runner.py. Run it manually when you want to enrich descriptions.
"""

import argparse
import time
import logging
import httpx
from groq import Groq
from datetime import datetime
import config
from database.models import Session, Event

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# Sources that contain music acts with potentially empty descriptions.
# Keys must match the source values stored in the DB (LLM scraper keys).
MUSIC_SOURCES = {'fibber', 'yuccatap', 'dirtydrummer'}

# groq/compound-mini: single web search per request, ~3x lower latency than groq/compound.
# Perfect for simple artist lookups — we only need one search per act.
ENRICH_MODEL = 'groq/compound'

# Seconds to wait between API calls (free-tier rate limit buffer)
CALL_DELAY = 3

_client = None


def _get_client() -> Groq:
    """Lazy Groq client with SSL verification disabled for corporate firewall."""
    global _client
    if _client is None:
        transport   = httpx.HTTPTransport(verify=False)
        http_client = httpx.Client(transport=transport)
        _client     = Groq(api_key=config.GROQ_API_KEY, http_client=http_client)
    return _client


def _needs_enrichment(event: Event) -> bool:
    """
    Return True if this event's description should be enriched.

    Qualifies when description is missing or is just a copy of the title
    (which is what the scrapers write as a fallback when no real description exists).
    """
    desc = (event.description or '').strip()
    title = (event.title or '').strip()
    return not desc or desc == title


def _lookup_genre(artist_name: str) -> str | None:
    """
    Ask Groq compound-beta to web-search the artist and return a short genre blurb.

    The prompt is tightly constrained so the model returns only a genre/style
    description — no preamble, no "I found...", just the genre text.

    Returns the genre string, or None if the call fails or returns nothing useful.
    """
    prompt = (
        f'Search the web for the musical artist or band "{artist_name}".\n'
        f'Return ONLY a short genre and style description (1-2 sentences max).\n'
        f'Example output: "Blues rock band known for high-energy live performances."\n'
        f'If you cannot find any information, return exactly: unknown\n'
        f'Do not include the artist name in your response. No preamble.'
    )

    try:
        response = _get_client().chat.completions.create(
            model=ENRICH_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2,
        )
        result = response.choices[0].message.content.strip()

        # Reject useless responses
        if not result or result.lower() in ('unknown', 'n/a', 'none', ''):
            return None

        # Truncate to a reasonable description length
        return result[:300]

    except Exception as e:
        log.error(f"Genre lookup failed for '{artist_name}': {e}")
        return None


def enrich_music_descriptions(
    sources: set = None,
    limit: int = None,
    dry_run: bool = False,
) -> dict:
    """
    Find qualifying music events and enrich their descriptions with genre info.

    Args:
        sources:  Set of source names to process. Defaults to MUSIC_SOURCES.
        limit:    Max number of events to enrich in one run. None = no limit.
        dry_run:  If True, print what would be updated but don't write to DB.

    Returns:
        Dict with keys: checked, enriched, skipped, failed
    """
    if sources is None:
        sources = MUSIC_SOURCES

    session = Session()
    stats = {'checked': 0, 'enriched': 0, 'skipped': 0, 'failed': 0}

    try:
        # Query: future events from music sources only
        query = (
            session.query(Event)
            .filter(
                Event.source.in_(sources),
                Event.date >= datetime.now(),
            )
            .order_by(Event.date)
        )
        if limit:
            query = query.limit(limit)

        events = query.all()
        print(f"Found {len(events)} future music events to check across: {', '.join(sources)}")

        for event in events:
            stats['checked'] += 1

            if not _needs_enrichment(event):
                log.debug(f"Skipping '{event.title}' — already has description")
                stats['skipped'] += 1
                continue

            print(f"  Looking up: {event.title} ({event.source})")

            if dry_run:
                print(f"    [dry-run] Would search for genre info")
                stats['enriched'] += 1
                continue

            genre = _lookup_genre(event.title)

            if genre:
                event.description = genre
                session.commit()
                print(f"    -> {genre}")
                stats['enriched'] += 1
            else:
                print(f"    -> No genre found, skipping")
                stats['failed'] += 1

            # Throttle between calls
            time.sleep(CALL_DELAY)

    except Exception as e:
        log.error(f"Enrichment run failed: {e}")
        session.rollback()
    finally:
        session.close()

    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Enrich music event descriptions with genre info via Groq web search.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print what would be updated without writing to the DB',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='Max number of events to enrich (default: no limit)',
    )
    parser.add_argument(
        '--source', type=str, default=None,
        help=f'Only enrich a specific source (options: {", ".join(sorted(MUSIC_SOURCES))})',
    )
    args = parser.parse_args()

    if not config.GROQ_API_KEY or config.GROQ_API_KEY == 'your_groq_api_key_here':
        print("Error: GROQ_API_KEY not configured in .env")
        exit(1)

    sources = {args.source} if args.source else MUSIC_SOURCES

    if args.source and args.source not in MUSIC_SOURCES:
        print(f"Unknown source: {args.source}. Options: {', '.join(sorted(MUSIC_SOURCES))}")
        exit(1)

    mode = '[DRY RUN] ' if args.dry_run else ''
    print(f"{mode}Enriching music descriptions...")
    print(f"Sources: {', '.join(sorted(sources))}")
    if args.limit:
        print(f"Limit: {args.limit} events")
    print()

    stats = enrich_music_descriptions(
        sources=sources,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(f"\nDone. Checked: {stats['checked']} | "
          f"Enriched: {stats['enriched']} | "
          f"Skipped (had desc): {stats['skipped']} | "
          f"Failed (no info): {stats['failed']}")
