#!/usr/bin/env python3
from llm_scrape_core import fetch_selenium, clean_html, ask_llm

url = 'https://scottsdalearts.org/whats-on/?categories=performances,events,programs-workshops'
html = fetch_selenium(url, wait=15)
text = clean_html(html)
chunk = text[:4000]
result = ask_llm(chunk, current_url=url, site_hint='Scottsdale Arts')
for e in result.get('events', [])[:10]:
    print(f"date='{e.get('date')}' time='{e.get('time')}' title='{e.get('title','')[:40]}'")
