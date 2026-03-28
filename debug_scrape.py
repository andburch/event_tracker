"""
debug_scrape.py -- Verbose diagnostic scraper for a single site.

Shows everything: raw HTML, cleaned text, full prompt sent to LLM, raw LLM response.

Usage:
    python debug_scrape.py dirtydrummer
    python debug_scrape.py fibber
    python debug_scrape.py rak
    (any key from sources.py SITES dict)
"""

import sys, json, httpx
import config
from sources import SITES
from llm_scrape_core import fetch_requests, fetch_selenium, clean_html, EVENT_SCHEMA, _get_client, _CHUNK_SIZE, _CHUNK_OVERLAP

DIVIDER = '=' * 80

def debug_scrape(key):
    if key not in SITES:
        print(f"Unknown key '{key}'. Valid keys: {', '.join(SITES)}")
        sys.exit(1)

    name, url, use_selenium, wait, max_pages, note, _color = SITES[key]
    print(f"\n{DIVIDER}")
    print(f"SITE: {name}  ({key})")
    print(f"URL:  {url}")
    print(f"FETCH: {'selenium' if use_selenium else 'requests'}  wait={wait}s")
    if note:
        print(f"NOTE: {note}")
    print(DIVIDER)

    # -------------------------------------------------------------------------
    # 1. Fetch raw HTML
    # -------------------------------------------------------------------------
    print("\n[1/4] FETCHING PAGE...")
    if use_selenium:
        html = fetch_selenium(url, wait)
    else:
        html = fetch_requests(url)

    print(f"      Raw HTML length: {len(html)} chars")
    print(f"\n{'─'*40} RAW HTML (first 2000 chars) {'─'*40}")
    print(html[:2000])
    print(f"{'─'*40} END RAW HTML {'─'*40}\n")

    # -------------------------------------------------------------------------
    # 2. Clean HTML
    # -------------------------------------------------------------------------
    print("\n[2/4] CLEANING HTML...")
    text = clean_html(html)
    print(f"      Cleaned text length: {len(text)} chars")
    print(f"\n{'─'*40} CLEANED TEXT (full) {'─'*40}")
    print(text)
    print(f"{'─'*40} END CLEANED TEXT {'─'*40}\n")

    # -------------------------------------------------------------------------
    # 3. Build prompt (same logic as _ask_llm_single)
    # -------------------------------------------------------------------------
    print("\n[3/4] BUILDING PROMPT...")

    # Chunk if needed
    chunks = []
    if len(text) <= 3000:  # Updated to match _CHUNK_SIZE
        chunks = [(text, True)]
    else:
        step = 3000 - 200  # Updated to match _CHUNK_SIZE - _CHUNK_OVERLAP
        start = 0
        while start < len(text):
            end = min(start + 3000, len(text))  # Updated to match _CHUNK_SIZE
            is_last = (end >= len(text))
            chunks.append((text[start:end], is_last))
            if is_last:
                break
            start += step

    print(f"      Chunks: {len(chunks)}")

    for chunk_idx, (chunk, is_last) in enumerate(chunks):
        print(f"\n{'─'*40} CHUNK {chunk_idx+1}/{len(chunks)} (is_last={is_last}, {len(chunk)} chars) {'─'*40}")

        if is_last:
            pagination_instruction = (
                "2. Find the NEXT PAGE URL and put it in 'next_page_url'.\n"
                "   Look for: numbered page links, 'Next' or '>' buttons, 'Load More' links,\n"
                "   or URL patterns like ?page=2. Return the full absolute URL.\n"
                "   If there is no next page, return null.\n"
                "   Links appear as 'Link Text [/path/or/url]' -- use those URLs.\n\n"
            )
        else:
            pagination_instruction = (
                "2. Set 'next_page_url' to null -- pagination is handled separately.\n\n"
            )

        prompt = (
            f"The following is text scraped from an events page"
            f"{' (' + name + ')' if name else ''}.\n"
            f"Current page URL: {url}\n\n"
            "1. Extract ALL upcoming events into the 'events' array.\n"
            "   Each event must have these exact keys:\n"
            "     title       (string)\n"
            "     date        (string, e.g. 'March 22, 2026')\n"
            "     time        (string e.g. '8:00 PM', or null)\n"
            "     description (string or null)\n"
            "     venue       (string or null)\n"
            "     url         (full absolute URL to event detail page, or null)\n"
            "   IMPORTANT: Times often appear on a separate line after the date, or in formats like\n"
            "   'Mar 20 @ 9:00 am - 5:00 pm' or '9:00 am - 4:00 pm' on the next line after the date.\n"
            "   Always capture the start time if present. Use 12-hour format e.g. '9:00 AM'.\n\n"
            + pagination_instruction
            + "Respond with ONLY valid JSON in this exact format, no markdown, no explanation:\n"
            '{"events": [...], "next_page_url": "..." or null}\n'
            'Return your response as json only.\n\n'
            f"PAGE TEXT:\n{chunk}"
        )

        print(f"\n{'─'*40} FULL PROMPT SENT TO LLM {'─'*40}")
        print(prompt)
        print(f"{'─'*40} END PROMPT {'─'*40}\n")

        # Approximate token count (rough: 1 token ~ 4 chars)
        approx_tokens = len(prompt) // 4
        print(f"      Approx prompt tokens: ~{approx_tokens}")

        # -------------------------------------------------------------------------
        # 4. Call LLM and show raw response
        # -------------------------------------------------------------------------
        print(f"\n[4/4] CALLING LLM (chunk {chunk_idx+1})...")
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                response_format=EVENT_SCHEMA,
            )
            raw = response.choices[0].message.content
            print(f"\n{'─'*40} RAW LLM RESPONSE {'─'*40}")
            print(repr(raw))  # repr so we see if it's empty string, None, etc.
            print(f"{'─'*40} END RAW RESPONSE {'─'*40}\n")

            if raw:
                try:
                    parsed = json.loads(raw)
                    events = parsed.get('events', [])
                    print(f"      Parsed OK: {len(events)} events found")
                    for i, ev in enumerate(events):
                        print(f"        [{i+1}] {ev.get('title')} | {ev.get('date')} {ev.get('time')} | {ev.get('venue')}")
                except json.JSONDecodeError as e:
                    print(f"      JSON PARSE ERROR: {e}")
            else:
                print("      *** LLM RETURNED EMPTY RESPONSE ***")

            # Show usage stats
            if hasattr(response, 'usage') and response.usage:
                u = response.usage
                print(f"\n      Token usage: prompt={u.prompt_tokens}, completion={u.completion_tokens}, total={u.total_tokens}")

        except Exception as e:
            print(f"\n      *** LLM ERROR: {e} ***")

    print(f"\n{DIVIDER}")
    print("DEBUG COMPLETE")
    print(DIVIDER)


if __name__ == '__main__':
    key = sys.argv[1] if len(sys.argv) > 1 else 'dirtydrummer'
    debug_scrape(key)
