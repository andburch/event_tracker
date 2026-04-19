"""
_test_llm_scrape.py -- CLI test harness for LLM-based event extraction

Imports all fetch/LLM/site logic from llm_scrape_core. This file only
contains the test runner (pretty-prints results, no DB writes) and the
CLI entry point.

USAGE
-----
    python _test_llm_scrape.py list                  # show all site keys + URLs
    python _test_llm_scrape.py <site_key>            # test one site
    python _test_llm_scrape.py <key1> <key2> ...     # test multiple sites
    python _test_llm_scrape.py all                   # run every site sequentially
    python _test_llm_scrape.py <site_key> --dump     # also print raw text sent to LLM
"""

import sys, time
from llm_scrape_core import (
    fetch_requests, fetch_selenium, close_driver,
    clean_html, ask_llm,
)
from sources import SITES
from pagination_engine import apply_trim


def run_test(name, start_url, use_selenium=False, wait=5, max_pages=3,
             note='', dump=False, site_key=''):
    """
    Run the LLM extraction loop for one site and print results.

    Follows pagination until next_page_url is null or max_pages reached.
    Does NOT write to the database -- for testing and debugging only.

    Args:
        name:         Display name (e.g. 'Gilbert Gov')
        start_url:    First URL to fetch
        use_selenium: True for JS-heavy sites
        wait:         Seconds to wait after Selenium page load
        max_pages:    Safety cap on pagination depth
        note:         Informational note printed in header
        dump:         If True, print raw text sent to LLM (diagnose 0-event results)
    """
    print(f"\n{'='*60}")
    print(f"SITE: {name}  (max {max_pages} pages)")
    if note:
        print(f"NOTE: {note}")
    print(f"{'='*60}")

    all_events  = []
    current_url = start_url
    visited     = set()
    page_num    = 0

    while current_url and page_num < max_pages:
        page_num += 1

        if current_url in visited:
            print(f"  Page {page_num}: loop detected, stopping")
            break
        visited.add(current_url)

        print(f"  Page {page_num}: {current_url[:80]}")

        try:
            html = fetch_selenium(current_url, wait) if use_selenium else fetch_requests(current_url)
        except Exception as e:
            print(f"    FETCH ERROR: {e}")
            break

        text = apply_trim(clean_html(html), site_key)
        print(f"    text={len(text)} chars", end='  ')

        if dump:
            print(f"\n--- RAW TEXT SENT TO LLM (first 2000 chars) ---")
            print(text[:2000])
            print(f"--- END ---\n", end='  ')

        try:
            result      = ask_llm(text, current_url=current_url, site_hint=name)
            page_events = result.get('events', [])
            next_url    = result.get('next_page_url')
            all_events.extend(page_events)
            print(f"events={len(page_events)}  next={next_url or 'null'}")

            if next_url and not next_url.startswith('http'):
                print(f"    next_page_url not absolute, stopping")
                break

            current_url = next_url
        except Exception as e:
            print(f"\n    LLM ERROR: {e}")
            break

        if current_url:
            time.sleep(2)

    print(f"\n  TOTAL: {len(all_events)} events across {page_num} page(s)")
    no_url = sum(1 for e in all_events if not e.get('url'))
    if no_url:
        print(f"  WARNING: {no_url}/{len(all_events)} events have no URL")
    for e in all_events[:8]:
        url_display = (e.get('url') or 'NO URL')[:45]
        print(f"    {str(e.get('date','?')):18} | {e.get('title','?')[:35]:<35} | {url_display}")
    if len(all_events) > 8:
        print(f"    ... and {len(all_events)-8} more")


if __name__ == '__main__':
    args   = sys.argv[1:]
    dump   = '--dump' in args
    args   = [a for a in args if a != '--dump']
    target = args[0] if args else None

    if not target or target in ('-h', '--help'):
        print("Usage: python _test_llm_scrape.py <site_key> [<key2> ...] [--dump]")
        print("       python _test_llm_scrape.py all [--dump]")
        print("       python _test_llm_scrape.py list")
        print(f"\nSite keys:")
        for k, entry in SITES.items():
            name, url, use_sel, wait, max_pages, note = entry[:6]
            sel = 'selenium' if use_sel else 'requests'
            print(f"  {k:<18} {sel:<10} {url[:60]}")
        sys.exit(0)

    if target == 'list':
        print(f"{'KEY':<18} {'FETCH':<10} {'PAGES':<7} URL")
        print('-' * 80)
        for k, entry in SITES.items():
            name, url, use_sel, wait, max_pages, note = entry[:6]
            sel  = 'selenium' if use_sel else 'requests'
            flag = f'  [{note}]' if note else ''
            print(f"  {k:<16} {sel:<10} max={max_pages}  {url[:55]}{flag}")
        sys.exit(0)

    try:
        if target == 'all':
            keys = list(SITES)
        else:
            keys    = args
            unknown = [k for k in keys if k not in SITES]
            if unknown:
                print(f"Unknown site(s): {', '.join(unknown)}")
                print(f"Valid keys: {', '.join(SITES)}")
                sys.exit(1)

        for key in keys:
            # SITES tuple: (name, url, use_sel, wait, max_pages, note, color, pagination_cfg)
            entry = SITES[key]
            name, url, use_sel, wait, max_pages, note = entry[:6]
            from sources import _today, _plus90
            url = url.format(today=_today(), plus90=_plus90())
            run_test(name, url, use_sel, wait, max_pages, note, dump=dump, site_key=key)
            if key != keys[-1]:
                time.sleep(3)

    finally:
        close_driver()
