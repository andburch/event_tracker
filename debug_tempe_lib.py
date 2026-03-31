#!/usr/bin/env python3
"""Debug Tempe Library page to see how times are formatted"""
from llm_scrape_core import fetch_selenium, clean_html

url = 'https://tempepubliclibrary.libnet.info/events?start=2026-03-28&end=2026-06-26'
print("Fetching...")
html = fetch_selenium(url, wait=8)
text = clean_html(html)
print(f"Total chars: {len(text)}")
print("\n--- First 3000 chars ---")
print(text[:3000])
