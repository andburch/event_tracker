"""
debug_source.py -- Inspect source config and generated URLs without fetching.

Shows every config field, the URLs that would be fetched for each page,
estimated LLM call count, estimated runtime, and a quick HTTP reachability
check (no Selenium, no LLM).

USAGE
-----
    python debug_source.py <key>       # inspect one source
    python debug_source.py --all       # inspect all sources
    python debug_source.py list        # list keys only
"""

import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import debug_utils as u


def inspect_source(key: str):
    from sources import SITES
    from datetime import datetime, timedelta
    import requests, urllib3

    entry = SITES[key]
    name, start_url, use_selenium, wait, max_pages, note, _color, pag = entry

    u.banner(f'SOURCE  ·  {key}')
    print(f'  Display name  : {name}')
    print(f'  Start URL     : {start_url}')
    print(f'  Fetch mode    : {"Selenium" if use_selenium else "requests"}'
          + (f'  (wait={wait}s)' if use_selenium else ''))
    print(f'  Max pages     : {max_pages}')
    print(f'  Note          : {note or "(none)"}')

    pag_type = (pag or {}).get('type', 'llm')
    print(f'  Pagination    : {pag_type}')
    if pag and pag_type != 'llm':
        for k, v in pag.items():
            if k != 'type':
                print(f'    {k:<18}: {v}')

    # Compute URLs that would be fetched
    print(f'\n  URLs to fetch:')
    urls = _compute_urls(key, entry)
    for i, url in enumerate(urls):
        print(f'    page {i+1}: {url}')

    # Estimate LLM calls (rough: assume 1 chunk for static/requests, 2-3 for large selenium pages)
    avg_chunks = 2 if use_selenium else 1
    est_llm_calls = len(urls) * avg_chunks
    est_fetch_time = len(urls) * (wait + 5 if use_selenium else 2)
    est_llm_time = est_llm_calls * 5  # ~5s per Groq call
    print(f'\n  Estimates:')
    print(f'    LLM calls (rough) : ~{est_llm_calls}  ({avg_chunks} chunks/page × {len(urls)} pages)')
    print(f'    Fetch time        : ~{u.fmt_time(est_fetch_time)}')
    print(f'    LLM time (Groq)   : ~{u.fmt_time(est_llm_time)}')
    print(f'    Total             : ~{u.fmt_time(est_fetch_time + est_llm_time)}')

    # Quick reachability check (HEAD request only, no Selenium)
    print(f'\n  Reachability check (HTTP HEAD, no Selenium):')
    urllib3.disable_warnings()
    try:
        t0 = time.time()
        r = requests.head(
            start_url, timeout=10, verify=False,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; debugger)'},
            allow_redirects=True,
        )
        elapsed = time.time() - t0
        status_ok = r.status_code < 400
        u.step('HEAD', 'OK' if status_ok else 'WARN',
               f'HTTP {r.status_code}  ({u.fmt_time(elapsed)})'
               + (f'  → {r.url}' if r.url != start_url else ''))
    except Exception as e:
        u.step('HEAD', 'FAIL', str(e))


def _compute_urls(key: str, entry: tuple) -> list[str]:
    """Return the list of URLs this source would fetch."""
    name, start_url, use_selenium, wait, max_pages, note, _color, pag = entry
    from datetime import datetime, timedelta

    pag_type = (pag or {}).get('type', 'llm')

    if pag_type == 'llm':
        # LLM pagination: we only know page 1; subsequent pages are LLM-determined
        return [start_url] + [f'(page {i+1}: determined at runtime by LLM)' for i in range(1, max_pages)]

    elif pag_type == 'multi_month':
        url_template = pag.get('url_template', start_url)
        months = pag.get('months', 3)
        base = datetime.now()
        urls = []
        for i in range(months):
            d = base + timedelta(days=30 * i)
            try:
                urls.append(url_template.format(month=d.month, year=d.year))
            except Exception:
                urls.append(url_template.format(month=f'{d.month:02d}', year=d.year))
        return urls

    elif pag_type == 'url_param':
        param_name = pag.get('param_name', 'page')
        start_index = pag.get('start_index', 1)
        import re
        param_pattern = pag.get('param_pattern') or rf'{param_name}=\d+'
        urls = []
        for i in range(max_pages):
            page_index = start_index + i
            if i == 0 and start_index == 1:
                urls.append(start_url)
            else:
                if re.search(param_pattern, start_url):
                    url = re.sub(param_pattern, f'{param_name}={page_index}', start_url)
                else:
                    sep = '&' if '?' in start_url else '?'
                    url = f'{start_url}{sep}{param_name}={page_index}'
                urls.append(url)
        return urls

    elif pag_type in ('js_button', 'calendar_grid'):
        return [f'{start_url} (+ {max_pages-1} JS button clicks)']

    return [start_url]


def main():
    parser = argparse.ArgumentParser(description='Inspect source config and URLs')
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key (or "list" or "--all")')
    parser.add_argument('--all', action='store_true', help='Inspect all sources')
    args = parser.parse_args()

    if args.key == 'list' or (not args.key and not args.all):
        u.list_sources()
        return

    from sources import SITES
    if args.all:
        for key in SITES:
            inspect_source(key)
    else:
        if args.key not in SITES:
            print(f'Unknown key: {args.key}')
            u.list_sources()
            sys.exit(1)
        inspect_source(args.key)


if __name__ == '__main__':
    main()
