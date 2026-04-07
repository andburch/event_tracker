"""
debug_clean.py -- Stage 2: Clean HTML and inspect the result.

Shows exactly what clean_html() strips and what survives, including tag removal
counts, whether a <main> root was found, JS placeholder detection, and the full
cleaned text.

USAGE
-----
    python debug_clean.py <key>                                    # fetch + clean live
    python debug_clean.py <key> --page 2                          # fetch page 2
    python debug_clean.py --file /tmp/debug/source/page_1_raw.html  # from saved artifact
    python debug_clean.py --file page.html --source <key>         # --source for artifact naming
    python debug_clean.py list                                     # list all site keys

Saves: /tmp/debug/{source}/page_N_cleaned.txt
"""

import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import debug_utils as u


def clean_and_inspect(html: str) -> tuple[str, dict]:
    """
    Run clean_html() and collect stats on what was removed.
    Returns (cleaned_text, stats_dict).
    """
    from bs4 import BeautifulSoup
    import re

    soup = BeautifulSoup(html, 'html.parser')

    # Count tags before removal
    tag_counts = {}
    for tag_name in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'img']:
        tag_counts[tag_name] = len(soup.find_all(tag_name))

    # Run standard clean_html()
    from llm_scrape_core import clean_html
    cleaned = clean_html(html)

    # Determine content root (re-parse to check)
    soup2 = BeautifulSoup(html, 'html.parser')
    root = 'main' if soup2.find('main') else 'body'

    return cleaned, {'tag_counts': tag_counts, 'root': root}


def run(key: str | None, source_label: str, html_file: str | None,
        page_num: int, save: bool):

    u.banner(f'CLEAN  ·  {source_label}')

    # Get raw HTML
    if html_file:
        print(f'  Source: file  {html_file}')
        try:
            with open(html_file) as f:
                html = f.read()
        except FileNotFoundError:
            u.step('LOAD', 'FAIL', f'File not found: {html_file}')
            sys.exit(1)
        u.step('LOAD', 'OK', u.fmt_size(len(html)))
    else:
        # Fetch live
        entry = u.get_source(key)
        name, start_url, use_selenium, wait, max_pages, note, _color, _pag = entry
        print(f'  Source: live  {start_url}')
        from llm_scrape_core import fetch_requests, fetch_selenium, close_driver
        t0 = time.time()
        try:
            if use_selenium:
                if not u.check_selenium_available():
                    sys.exit(1)
                html = fetch_selenium(start_url, wait)
            else:
                html = fetch_requests(start_url)
            elapsed = time.time() - t0
            u.step('FETCH', 'OK', f'{u.fmt_size(len(html))}  ({u.fmt_time(elapsed)})')
        except Exception as e:
            u.step('FETCH', 'FAIL', str(e))
            sys.exit(1)
        finally:
            if use_selenium:
                close_driver()

    # Clean
    t0 = time.time()
    cleaned, stats = clean_and_inspect(html)
    elapsed = time.time() - t0

    reduction = 100 - (len(cleaned) * 100 // max(len(html), 1))
    u.step('CLEAN', 'OK',
           f'{u.fmt_size(len(html))} → {u.fmt_size(len(cleaned))} '
           f'({reduction}% reduction)  ({u.fmt_time(elapsed)})')

    # Tag removal stats
    tag_counts = stats['tag_counts']
    removed = {k: v for k, v in tag_counts.items() if v > 0}
    if removed:
        print(f'  Tags removed : ' + '  '.join(f'{k}={v}' for k, v in removed.items()))
    else:
        print(f'  Tags removed : none')
    print(f'  Content root : <{stats["root"]}>')
    print(f'  Token est.   : ~{u.estimate_tokens(cleaned):,} tokens')

    # JS placeholder / empty check — MUST happen before any LLM call
    warnings = u.check_empty_or_placeholder(cleaned)
    if warnings:
        for w in warnings:
            u.step('JS-CHECK', 'WARN', w)
    else:
        u.step('JS-CHECK', 'OK', 'no placeholder text detected')

    # Full cleaned text
    print(f'\n  ── Full cleaned text ({u.fmt_size(len(cleaned))}) ──')
    for line in cleaned.splitlines():
        print(f'  │ {line}')
    print(f'  └── end')

    # Save artifact
    if save:
        filename = f'page_{page_num}_cleaned.txt'
        path = u.save_artifact(source_label, filename, cleaned)
        u.step('SAVED', 'OK', path)
        print(f'\n  Next step:')
        print(f'    python debug_chunk.py --file {path}')
        if key:
            print(f'    python debug_chunk.py --file {path} --source {key}')


def main():
    parser = argparse.ArgumentParser(description='Clean HTML and inspect the result')
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key from sources.py (or "list")')
    parser.add_argument('--file', default=None,
                        help='Use saved raw HTML file instead of fetching live')
    parser.add_argument('--source', default=None,
                        help='Source key for artifact naming (required with --file)')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number for artifact filename (default: 1)')
    parser.add_argument('--no-save', action='store_true',
                        help="Don't save cleaned text artifact")
    args = parser.parse_args()

    if args.key == 'list':
        u.list_sources()
        return

    if not args.key and not args.file:
        parser.print_help()
        sys.exit(1)

    key = args.key
    source_label = key or args.source or 'custom'

    run(
        key=key,
        source_label=source_label,
        html_file=args.file,
        page_num=args.page,
        save=not args.no_save,
    )


if __name__ == '__main__':
    main()
