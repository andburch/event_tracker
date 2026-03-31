#!/usr/bin/env python3
from llm_scrape_core import clean_html
from bs4 import BeautifulSoup

for fname, label in [('debug_tca_april.html', 'TCA'), ('debug_gilbert_april.html', 'GILBERT')]:
    with open(fname, encoding='utf-8') as f:
        html = f.read()
    text = clean_html(html)
    print(f"\n=== {label} - first 1500 chars of cleaned text ===")
    print(text[:1500])
