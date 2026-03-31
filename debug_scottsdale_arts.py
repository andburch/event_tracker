#!/usr/bin/env python3
from llm_scrape_core import fetch_selenium, clean_html

url = 'https://scottsdalearts.org/whats-on/?categories=performances,events,programs-workshops'
print("Fetching with scroll...")
html = fetch_selenium(url, wait=15, scroll_passes=10)
text = clean_html(html)
print(f"Total chars: {len(text)}")
print("\n--- First 5000 chars ---")
print(text[:5000])
