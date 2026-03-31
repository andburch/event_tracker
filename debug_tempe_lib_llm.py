#!/usr/bin/env python3
"""Debug what the LLM actually returns for Tempe Library events"""
from llm_scrape_core import fetch_selenium, clean_html, ask_llm

url = 'https://tempepubliclibrary.libnet.info/events?start=2026-03-28&end=2026-06-26'
print("Fetching...")
html = fetch_selenium(url, wait=8)
text = clean_html(html)

# Just run the first chunk to see what the LLM returns
chunk = text[:4000]
result = ask_llm(chunk, current_url=url, site_hint='Tempe Public Library')
events = result.get('events', [])

print(f"\nFirst {len(events)} events - raw date/time from LLM:")
for e in events[:10]:
    print(f"  date='{e.get('date')}' time='{e.get('time')}' title='{e.get('title', '')[:40]}'")
