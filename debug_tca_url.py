#!/usr/bin/env python3
from llm_scrape_core import fetch_selenium, clean_html

url = 'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar'
print("Fetching TCA real URL...")
html = fetch_selenium(url, wait=15)
text = clean_html(html)
print(f"Total chars: {len(text)}")
print("\n--- First 3000 chars ---")
print(text[:3000])
