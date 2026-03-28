#!/usr/bin/env python3
"""
Debug script to see what dates the LLM is returning for Fibber Magees
and how they're being parsed.
"""

from llm_scrape_core import fetch_requests, clean_html, ask_llm
from sources import SITES
from llm_scraper import parse_date

def debug_fibber_dates():
    name, url, use_selenium, wait, max_pages, note, color = SITES['fibber']
    
    print(f"Fetching {name} from {url}")
    html = fetch_requests(url)
    text = clean_html(html)
    
    print(f"Cleaned text length: {len(text)} chars")
    
    result = ask_llm(text, current_url=url, site_hint=name)
    events = result.get('events', [])
    
    print(f"\nFound {len(events)} events:")
    print("Raw LLM output -> Parsed date")
    print("-" * 60)
    
    for i, event in enumerate(events):
        raw_date = event.get('date', '')
        raw_time = event.get('time', '')
        parsed_dt = parse_date(raw_date, raw_time)
        
        print(f"{i+1:2d}. '{raw_date}' + '{raw_time}' -> {parsed_dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"    Title: {event.get('title', 'No title')}")
        
        if i >= 15:  # Show first 15 for debugging
            print(f"    ... and {len(events) - 16} more")
            break

if __name__ == "__main__":
    debug_fibber_dates()