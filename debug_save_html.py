#!/usr/bin/env python3
from llm_scrape_core import fetch_selenium

print("Fetching TCA April...")
html = fetch_selenium('https://www.tempecenterforthearts.com/events/calendar/-curm-4/-cury-2026', wait=15)
with open('debug_tca_april.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f"Saved debug_tca_april.html ({len(html)} chars)")

print("Fetching Gilbert April...")
html = fetch_selenium('https://www.gilbertaz.gov/residents/calendar-month-view/-curm-4/-cury-2026', wait=15)
with open('debug_gilbert_april.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f"Saved debug_gilbert_april.html ({len(html)} chars)")
