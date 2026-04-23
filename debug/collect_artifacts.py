"""
Collect page_1_cleaned.txt artifacts for every site.
Skips sites that already have a saved artifact.
Run directly on host: python3 debug/collect_artifacts.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources import SITES
from scrape.core import fetch_requests, fetch_selenium, close_driver, clean_html
from debug import utils as u

skip_existing = '--force' not in sys.argv

for key, entry in SITES.items():
    name, url, use_selenium, wait, max_pages, note, _color, _pag = entry

    artifact = os.path.join(u.DEBUG_DIR, key, 'page_1_cleaned.txt')
    if skip_existing and os.path.exists(artifact):
        print(f'  [skip] {key}  (artifact exists)')
        continue

    print(f'\n  [{key}]  {name}')
    print(f'    url: {url[:70]}')

    try:
        t0 = time.time()
        if use_selenium:
            html = fetch_selenium(url, wait)
            close_driver()
        else:
            html = fetch_requests(url)
        elapsed = time.time() - t0

        text = clean_html(html)
        u.save_artifact(key, 'page_1_raw.html', html)
        u.save_artifact(key, 'page_1_cleaned.txt', text)
        print(f'    fetched {u.fmt_size(len(html))} → cleaned {u.fmt_size(len(text))}  ({u.fmt_time(elapsed)})')

    except Exception as e:
        print(f'    ERROR: {e}')

print('\nDone.')
