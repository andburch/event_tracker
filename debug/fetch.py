"""
debug_fetch.py -- Stage 1: Fetch raw HTML and inspect it.

Fetches a source URL and shows the raw HTML size, fetch time, and the first
1000 chars so you can check for bot-blocks before running the full pipeline.

USAGE
-----
    python debug_fetch.py <key>                    # use source config
    python debug_fetch.py <key> --wait 20          # override Selenium wait seconds
    python debug_fetch.py <key> --scroll 5         # override scroll passes
    python debug_fetch.py <key> --page 2           # fetch page 2 (url_param sites)
    python debug_fetch.py --url https://... --selenium  # arbitrary URL with Selenium
    python debug_fetch.py --url https://...        # arbitrary URL with requests
    python debug_fetch.py list                     # list all site keys
    python debug_fetch.py <key> --no-save          # don't write artifact

Saves: /tmp/debug/{source}/page_N_raw.html
"""

import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import debug_utils as u


def run(key: str, url_override: str, use_selenium_override: bool | None,
        wait_override: int | None, scroll_override: int | None,
        page_num: int, save: bool):

    from llm_scrape_core import fetch_requests, fetch_selenium, close_driver

    source_label = key or 'custom'

    # Resolve config
    if key:
        entry = u.get_source(key)
        name, start_url, use_selenium, wait, max_pages, note, _color, pag = entry
        url = url_override or start_url
    else:
        name = url_override
        url = url_override
        use_selenium = use_selenium_override or False
        wait = wait_override or 6

    if use_selenium_override is not None:
        use_selenium = use_selenium_override
    if wait_override is not None:
        wait = wait_override
    scroll = scroll_override if scroll_override is not None else 10

    u.banner(f'FETCH  ·  {name}')
    print(f'  URL        : {url}')
    print(f'  Mode       : {"Selenium" if use_selenium else "requests"}'
          + (f'  (wait={wait}s, scroll={scroll})' if use_selenium else ''))
    if page_num > 1:
        print(f'  Page       : {page_num} (note: only applicable to url_param sites)')

    # Selenium prereq check
    if use_selenium and not u.check_selenium_available():
        sys.exit(1)

    t0 = time.time()
    try:
        if use_selenium:
            html = fetch_selenium(url, wait, scroll_passes=scroll)
        else:
            html = fetch_requests(url)
        elapsed = time.time() - t0
    except Exception as e:
        u.step('FETCH', 'FAIL', str(e))
        sys.exit(1)
    finally:
        if use_selenium:
            close_driver()

    u.step('FETCH', 'OK', f'{u.fmt_size(len(html))}  ({u.fmt_time(elapsed)})')

    # Bot-block detection
    lower = html[:3000].lower()
    flags = []
    if 'access denied'    in lower: flags.append('"Access Denied" in first 3000 chars')
    if 'captcha'          in lower: flags.append('"captcha" in first 3000 chars')
    if 'just a moment'    in lower: flags.append('Cloudflare "Just a moment" detected')
    if '<title>403'       in lower: flags.append('403 in <title>')
    if len(html) < 2000          : flags.append(f'Very short response ({len(html)} chars) — possible block')

    if flags:
        for f in flags:
            u.step('BOT-CHECK', 'WARN', f)
    else:
        u.step('BOT-CHECK', 'OK', 'no signals detected')

    # Show first 1000 chars
    print(f'\n  ── First 1000 chars of raw HTML ──')
    for line in html[:1000].splitlines():
        print(f'  │ {line}')
    if len(html) > 1000:
        print(f'  │ ... [{len(html) - 1000} more chars]')

    # Save artifact
    if save:
        filename = f'page_{page_num}_raw.html'
        path = u.save_artifact(source_label, filename, html)
        u.step('SAVED', 'OK', path)
        print(f'\n  Next step:')
        if key:
            print(f'    docker compose run --rm web python debug_clean.py {key}  --from clean (using saved artifact)')
        print(f'    docker compose run --rm web python debug_clean.py --file {path}' + (f' --source {key}' if key else ''))


def main():
    parser = argparse.ArgumentParser(
        description='Fetch raw HTML and inspect it',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key from sources.py (or "list")')
    parser.add_argument('--url', default=None, help='Override URL')
    parser.add_argument('--selenium', action='store_true', default=None,
                        help='Force Selenium (for --url mode)')
    parser.add_argument('--wait', type=int, default=None,
                        help='Override Selenium wait seconds')
    parser.add_argument('--scroll', type=int, default=None,
                        help='Override scroll passes')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number for artifact filename (default: 1)')
    parser.add_argument('--no-save', action='store_true',
                        help="Don't save artifact to /tmp/debug/")
    args = parser.parse_args()

    if args.key == 'list' or (not args.key and not args.url):
        u.list_sources()
        return

    if not args.key and not args.url:
        parser.print_help()
        sys.exit(1)

    run(
        key=args.key if args.key != 'list' else None,
        url_override=args.url,
        use_selenium_override=True if args.selenium else None,
        wait_override=args.wait,
        scroll_override=args.scroll,
        page_num=args.page,
        save=not args.no_save,
    )


if __name__ == '__main__':
    main()
