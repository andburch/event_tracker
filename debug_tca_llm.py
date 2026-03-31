#!/usr/bin/env python3
from llm_scrape_core import fetch_selenium, clean_html, ask_llm

url = 'https://www.tempecenterforthearts.com/events/calendar/-curm-4/-cury-2026'
html = fetch_selenium(url, wait=15)
text = clean_html(html)
print(f"Page chars: {len(text)}")
result = ask_llm(text, current_url=url, site_hint='Tempe Center for the Arts')
events = result.get('events', [])
print(f"\nLLM returned {len(events)} events:")
for e in events:
    print(f"  date='{e.get('date')}' time='{e.get('time')}' title='{e.get('title','')[:50]}'")
