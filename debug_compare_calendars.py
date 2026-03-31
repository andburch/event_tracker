#!/usr/bin/env python3
"""Compare TCA April vs Gilbert April raw text to understand why one works and not the other"""
from llm_scrape_core import fetch_selenium, clean_html

print("=== TCA APRIL ===")
html = fetch_selenium('https://www.tempecenterforthearts.com/events/calendar/-curm-4/-cury-2026', wait=15)
tca_text = clean_html(html)
print(tca_text[:2000])

print("\n\n=== GILBERT APRIL ===")
html = fetch_selenium('https://www.gilbertaz.gov/residents/calendar-month-view/-curm-4/-cury-2026', wait=15)
gilbert_text = clean_html(html)
print(gilbert_text[:2000])
