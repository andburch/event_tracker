"""
debug/llm.py -- Stage 4+5: LLM call inspector and response parser.

Sends a single text chunk to the LLM and shows everything: the full prompt,
the raw response string before JSON parsing, parsed events with field detail,
and which events would be dropped in production due to unparseable dates.

USAGE
-----
    python debug/llm.py <key>                                       # fetch+clean+chunk → send chunk 1
    python debug/llm.py --file /tmp/debug/source/page_1_chunk_1.txt --source <key>
    python debug/llm.py --file chunk.txt --source test --dry-run    # show prompt only, no API call
    python debug/llm.py --file chunk.txt --source test --provider ollama
    python debug/llm.py --file chunk.txt --source test --provider both  # compare groq + ollama
    python debug/llm.py --file chunk.txt --source test --chunk 2   # mark as chunk 2 (not last)
    python debug/llm.py list                                        # list all site keys

Saves: /tmp/debug/{source}/page_N_chunk_M_prompt.txt
       /tmp/debug/{source}/page_N_chunk_M_response.json
"""

import sys, os, time, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from debug import utils as u


def build_prompt(text: str, url: str, site_hint: str, is_last_chunk: bool) -> str:
    """Reconstruct the exact prompt _ask_llm_single() would send."""
    if is_last_chunk:
        pagination_instruction = (
            "2. Find the NEXT PAGE URL and put it in 'next_page_url'.\n"
            "   Look for: numbered page links, 'Next' or '>' buttons, 'Load More' links,\n"
            "   or URL patterns like ?page=2. Return the full absolute URL.\n"
            "   If there is no next page, return null.\n"
            "   Links appear as 'Link Text [/path/or/url]' -- use those URLs.\n\n"
        )
    else:
        pagination_instruction = (
            "2. Set 'next_page_url' to null -- pagination is handled separately.\n\n"
        )

    return (
        f"The following is text scraped from an events page"
        f"{' (' + site_hint + ')' if site_hint else ''}.\n"
        f"Current page URL: {url}\n\n"
        "1. Extract all events into the 'events' array.\n"
        "   Each event must have these exact keys:\n"
        "     title       (string)\n"
        "     date        (string, MUST be in YYYY-MM-DD format, e.g. '2026-03-22'. If a date range like 'Oct 17, 2025 - Apr 25, 2026', use the START date)\n"
        "     end_date    (string, YYYY-MM-DD format, or null. Only set if the event is a date range e.g. 'Oct 17, 2025 - Apr 25, 2026' -> '2026-04-25')\n"
        "     time        (string e.g. '8:00 PM', or null. Convert formats like '1:30pm' to '1:30 PM')\n"
        "     description (string or null)\n"
        "     venue       (string or null)\n"
        "     url         (full absolute URL to event detail page, or null. COPY the URL exactly as it appears in the text - do NOT paraphrase or modify it)\n"
        "   IMPORTANT: Times often appear on a separate line after the date, or in formats like\n"
        "   'Mar 20 @ 9:00 am - 5:00 pm' or '9:00 am - 4:00 pm' on the next line after the date.\n"
        "   Always capture the start time if present. Use 12-hour format e.g. '9:00 AM'.\n"
        "   CRITICAL: Date MUST be in YYYY-MM-DD format (e.g. '2026-03-22'), not text format. For date ranges, use the start date.\n"
        "   CRITICAL: For calendar grid layouts, the month is shown at the top of the page. Day numbers in the grid belong to THAT month unless clearly labeled otherwise.\n\n"
        + pagination_instruction
        + "Respond with ONLY valid JSON in this exact format, no markdown, no explanation:\n"
        '{"events": [...], "next_page_url": "..." or null}\n'
        'Return your response as json only.\n\n'
        f"PAGE TEXT:\n{text}"
    )


def call_llm(prompt: str, provider: str, source_label: str) -> tuple[str | None, float, object | None]:
    """Call LLM and return (content, duration, usage). content=None on error."""
    from llm.provider import get_client, _MODELS
    from scrape.core import EVENT_SCHEMA

    model = _MODELS[(provider, 'scraping')]()
    client = get_client(provider)

    print(f'  Calling {provider} / {model} ...')
    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
            response_format=EVENT_SCHEMA,
        )
        duration = time.time() - t0
        return response.choices[0].message.content, duration, response.usage
    except Exception as e:
        duration = time.time() - t0
        u.step('LLM', 'FAIL', f'{u.fmt_time(duration)} — {e}')
        return None, duration, None


def show_events(events: list, next_url: str | None):
    """Print parsed events with field completeness and date-parse status."""
    print(f'\n  Events found : {len(events)}')
    print(f'  Next page URL: {next_url or "null"}')

    date_drop_count = 0
    no_url_count    = 0
    no_title_count  = 0

    for i, ev in enumerate(events):
        title = ev.get('title') or ''
        date  = ev.get('date')  or ''
        time_ = ev.get('time')  or ''
        url_  = ev.get('url')   or ''

        ok, date_result = u.parse_date_debug(date, time_ or None)
        if not ok:
            date_drop_count += 1
        if not url_:
            no_url_count += 1
        if not title:
            no_title_count += 1

        date_flag = '' if ok else '  ← WOULD DROP in production'
        print(f'\n  [{i+1}] {title[:60] or "(no title)"}')
        print(f'       date        : {date or "(none)"}  → {date_result}{date_flag}')
        print(f'       time        : {time_ or "(none)"}')
        print(f'       venue       : {(ev.get("venue") or "(none)")[:60]}')
        print(f'       url         : {url_[:80] or "(none)"}')
        desc = (ev.get('description') or '').strip()
        if desc:
            print(f'       description : {desc[:120]}{"..." if len(desc) > 120 else ""}')

    # Summary warnings
    if date_drop_count:
        u.step('DATE-DROPS', 'WARN',
               f'{date_drop_count}/{len(events)} events have unparseable dates — '
               f'would use sentinel date (12:34) in production')
    else:
        u.step('DATE-PARSE', 'OK', f'all {len(events)} dates parsed cleanly')

    if no_url_count:
        u.step('MISSING-URL', 'WARN', f'{no_url_count}/{len(events)} events have no URL')
    if no_title_count:
        u.step('MISSING-TTL', 'WARN', f'{no_title_count}/{len(events)} events have no title')


def run_for_provider(provider: str, prompt: str, text: str, url: str,
                     source_label: str, page_num: int, chunk_num: int,
                     dry_run: bool, save: bool):

    u.banner(f'LLM  ·  provider={provider}')

    # Show prompt
    print(f'  Prompt size : {u.fmt_size(len(prompt))}  (~{u.estimate_tokens(prompt):,} tokens)')
    print(f'\n  ── Full prompt ──')
    for line in prompt.splitlines():
        print(f'  │ {line}')
    print(f'  └── end prompt')

    if save:
        fname = f'page_{page_num}_chunk_{chunk_num}_prompt.txt'
        path = u.save_artifact(source_label, fname, prompt)
        u.step('SAVED', 'OK', f'prompt → {path}')

    if dry_run:
        u.step('LLM', 'SKIP', '--dry-run: skipping API call')
        return

    # Call LLM
    content, duration, usage = call_llm(prompt, provider, source_label)
    if content is None:
        return

    tok_info = ''
    if usage:
        tok_info = f'prompt={usage.prompt_tokens}  completion={usage.completion_tokens}'
    u.step('LLM', 'OK', f'{u.fmt_time(duration)}  {tok_info}')

    # Show raw response
    print(f'\n  ── Raw LLM response ──')
    for line in content.splitlines():
        print(f'  │ {line}')
    print(f'  └── end response')

    if save:
        fname = f'page_{page_num}_chunk_{chunk_num}_response.json'
        path = u.save_artifact(source_label, fname, content)
        u.step('SAVED', 'OK', f'response → {path}')

    # Parse
    u.banner(f'PARSE  ·  provider={provider}')
    try:
        parsed = json.loads(content)
        events = parsed.get('events', [])
        next_url = parsed.get('next_page_url')
        u.step('PARSE', 'OK', f'{len(events)} events')
        show_events(events, next_url)
    except json.JSONDecodeError as e:
        u.step('PARSE', 'FAIL', f'JSONDecodeError: {e}')
        print(f'  Raw content was:\n{content[:500]}')


def run(key: str | None, source_label: str, text_file: str | None,
        url: str, providers: list[str], chunk_num: int, is_last_chunk: bool,
        page_num: int, dry_run: bool, save: bool):

    import config

    # Get text chunk
    if text_file:
        try:
            with open(text_file) as f:
                text = f.read()
        except FileNotFoundError:
            u.step('LOAD', 'FAIL', f'File not found: {text_file}')
            sys.exit(1)
    else:
        # Fetch + clean + chunk live, use chunk_num
        entry = u.get_source(key)
        name, start_url, use_selenium, wait, max_pages, note, _color, _pag = entry
        url = url or start_url
        from scrape.core import fetch_requests, fetch_selenium, close_driver, clean_html, _chunk_text
        try:
            if use_selenium:
                if not u.check_selenium_available():
                    sys.exit(1)
                html = fetch_selenium(start_url, wait)
            else:
                html = fetch_requests(start_url)
            cleaned = clean_html(html)
        except Exception as e:
            u.step('FETCH+CLEAN', 'FAIL', str(e))
            sys.exit(1)
        finally:
            if use_selenium:
                close_driver()

        warnings = u.check_empty_or_placeholder(cleaned)
        if warnings:
            for w in warnings:
                u.step('JS-CHECK', 'WARN', w)

        if len(cleaned) <= config.LLM_CHUNK_SIZE:
            chunks = [(cleaned, True)]
        else:
            chunks = list(_chunk_text(cleaned))

        if chunk_num > len(chunks):
            u.step('CHUNK', 'FAIL', f'--chunk {chunk_num} requested but only {len(chunks)} chunks exist')
            sys.exit(1)

        text, is_last_chunk = chunks[chunk_num - 1]
        print(f'  Using chunk {chunk_num}/{len(chunks)}  ({u.fmt_size(len(text))})')

    # JS check on the text we're about to send
    warnings = u.check_empty_or_placeholder(text)
    if warnings:
        for w in warnings:
            u.step('JS-CHECK', 'WARN', w)

    # Build prompt
    entry_url = url or (u.get_source(key)[1] if key else 'https://unknown')
    site_hint = u.get_source(key)[0] if key else source_label
    prompt = build_prompt(text, entry_url, site_hint, is_last_chunk)

    # Run for each provider
    for provider in providers:
        run_for_provider(
            provider=provider,
            prompt=prompt,
            text=text,
            url=entry_url,
            source_label=source_label,
            page_num=page_num,
            chunk_num=chunk_num,
            dry_run=dry_run,
            save=save,
        )


def main():
    parser = argparse.ArgumentParser(
        description='LLM call inspector: show prompt, raw response, parsed events',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key from sources.py (or "list")')
    parser.add_argument('--file', default=None,
                        help='Use saved chunk text file')
    parser.add_argument('--source', default=None,
                        help='Source key for naming/hints (used with --file)')
    parser.add_argument('--url', default=None,
                        help='URL to use in prompt context (used with --file)')
    parser.add_argument('--provider', default='default',
                        help='groq | ollama | both | default')
    parser.add_argument('--chunk', type=int, default=1,
                        help='Which chunk to send (1-indexed, default: 1)')
    parser.add_argument('--not-last', action='store_true',
                        help='Mark chunk as intermediate (disables pagination instruction)')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number for artifact naming (default: 1)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show prompt only, do not call the LLM')
    parser.add_argument('--no-save', action='store_true',
                        help="Don't save prompt/response artifacts")
    args = parser.parse_args()

    if args.key == 'list':
        u.list_sources()
        return

    if not args.key and not args.file:
        parser.print_help()
        sys.exit(1)

    import config
    if args.provider == 'both':
        providers = ['groq', 'ollama']
    elif args.provider == 'default':
        providers = [config.LLM_PROVIDER]
    else:
        providers = [args.provider]

    source_label = args.key or args.source or 'custom'

    run(
        key=args.key,
        source_label=source_label,
        text_file=args.file,
        url=args.url,
        providers=providers,
        chunk_num=args.chunk,
        is_last_chunk=not args.not_last,
        page_num=args.page,
        dry_run=args.dry_run,
        save=not args.no_save,
    )


if __name__ == '__main__':
    main()
