"""
debug/pipeline.py -- Full scrape pipeline orchestrator with step-by-step output.

Runs the complete fetch → clean → chunk → LLM → parse → validate flow, pausing
between chunks so you can inspect what the LLM sees and returns without committing
to the full run. Saves artifacts at every stage so you can resume from any point.

USAGE
-----
    python debug/pipeline.py <key>                        # full run, interactive pauses
    python debug/pipeline.py <key> --auto                 # no pauses
    python debug/pipeline.py <key> --page 2               # process page 2 only (LLM sites only)
    python debug/pipeline.py <key> --stop-after fetch     # stop after fetching HTML
    python debug/pipeline.py <key> --stop-after clean     # stop after cleaning
    python debug/pipeline.py <key> --stop-after chunk     # stop after chunking
    python debug/pipeline.py <key> --stop-after llm       # show LLM output, skip final parse summary
    python debug/pipeline.py <key> --no-llm               # fetch+clean+chunk only (no API calls)
    python debug/pipeline.py <key> --from clean           # skip fetch, use saved HTML artifact
    python debug/pipeline.py <key> --from llm             # skip fetch+clean+chunk, use saved chunks
    python debug/pipeline.py <key> --provider ollama      # use Ollama instead of Groq
    python debug/pipeline.py <key> --provider both        # run both providers on each chunk
    python debug/pipeline.py --url https://... --selenium # arbitrary URL (no source key needed)
    python debug/pipeline.py list                         # list all site keys

Flow per page:
  1. RESOLVE  — compute URL for this page
  2. FETCH    — fetch HTML (skipped if --from clean or --from llm)
  3. CLEAN    — run clean_html() + JS placeholder check
  4. CHUNK    — split into overlapping windows
  5. LLM      — per chunk: send to LLM, show raw response
     [interactive] "Continue to chunk N+1? [y/n/skip/save]"
  6. PARSE    — json.loads(), extract events
  7. VALIDATE — field completeness, date-parse drop warnings
  8. DEDUP    — across-chunk dedup stats
  [interactive] "Continue to next page? [y/n]"

Artifacts saved to: /tmp/debug/{source}/

Exit codes: 0 = all stages completed, 1 = failure
"""

import sys, os, time, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from debug import utils as u

STAGE_ORDER = ['fetch', 'clean', 'chunk', 'llm', 'parse']


# ── Prompt builder (mirrors _ask_llm_single exactly) ──────────────────────────

def build_prompt(text: str, url: str, site_hint: str, is_last_chunk: bool) -> str:
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


# ── LLM call ──────────────────────────────────────────────────────────────────

def call_llm(prompt: str, provider: str) -> tuple[str | None, float, object | None]:
    from llm.provider import get_client, _MODELS
    from scrape.core import EVENT_SCHEMA
    model = _MODELS[(provider, 'scraping')]()
    client = get_client(provider)
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
        return None, duration, str(e)


# ── Single page pipeline ───────────────────────────────────────────────────────

def process_page(
    key: str,
    source_label: str,
    name: str,
    url: str,
    use_selenium: bool,
    wait: int,
    page_num: int,
    providers: list[str],
    stop_after: str,
    skip_fetch: bool,    # --from clean or --from llm
    skip_clean: bool,    # --from llm
    no_llm: bool,
    auto: bool,
) -> tuple[list[dict], str | None, bool]:
    """
    Process one page through the pipeline.
    Returns (all_events, next_page_url, should_continue).
    """
    import config
    from scrape.core import clean_html, _chunk_text

    u.banner(f'PAGE {page_num}  ·  {url[:80]}')

    # Timers
    t_fetch = t_clean = t_chunk = t_llm = 0.0

    # ── STEP 1: FETCH ────────────────────────────────────────────────────────
    if skip_fetch:
        # Load from saved artifact
        filename = f'page_{page_num}_raw.html'
        if not u.artifact_exists(source_label, filename):
            u.step('FETCH', 'SKIP', f'--from used but artifact missing: /tmp/debug/{source_label}/{filename}')
            u.step('FETCH', 'FAIL', 'Run without --from first to generate artifacts')
            return [], None, False
        html = u.load_artifact(source_label, filename)
        u.step('FETCH', 'SKIP', f'using saved artifact  ({u.fmt_size(len(html))})')
    else:
        from scrape.core import fetch_requests, fetch_selenium
        t0 = time.time()
        try:
            if use_selenium:
                html = fetch_selenium(url, wait)
            else:
                html = fetch_requests(url)
            t_fetch = time.time() - t0
        except Exception as e:
            u.step('FETCH', 'FAIL', str(e))
            return [], None, False

        # Bot-block detection
        lower = html[:3000].lower()
        flags = []
        if 'access denied' in lower: flags.append('"Access Denied"')
        if 'captcha'        in lower: flags.append('"captcha"')
        if 'just a moment'  in lower: flags.append('Cloudflare')
        if len(html) < 2000         : flags.append('very short response')

        if flags:
            u.step('FETCH', 'WARN',
                   f'{u.fmt_size(len(html))}  ({u.fmt_time(t_fetch)})  — {", ".join(flags)}')
        else:
            u.step('FETCH', 'OK', f'{u.fmt_size(len(html))}  ({u.fmt_time(t_fetch)})')

        # Save artifact
        path = u.save_artifact(source_label, f'page_{page_num}_raw.html', html)
        u.step('SAVED', 'INFO', path)

    if stop_after == 'fetch':
        print(f'\n  [stopped at fetch stage]')
        return [], None, False

    # ── STEP 2: CLEAN ────────────────────────────────────────────────────────
    if skip_clean:
        # Load from saved artifact — but we need text, not HTML
        # For --from llm, we load chunks directly, handled below
        pass

    if not skip_clean:
        t0 = time.time()
        text = clean_html(html)
        t_clean = time.time() - t0

        reduction = 100 - (len(text) * 100 // max(len(html), 1))
        u.step('CLEAN', 'OK',
               f'{u.fmt_size(len(html))} → {u.fmt_size(len(text))} '
               f'({reduction}% reduction)  ({u.fmt_time(t_clean)})')

        # JS placeholder check — abort before LLM if empty/placeholder
        warnings = u.check_empty_or_placeholder(text)
        if warnings:
            for w in warnings:
                u.step('JS-CHECK', 'WARN', w)
            u.step('CLEAN', 'FAIL', 'aborting — empty/placeholder content, no LLM call made')
            print(f'  Tip: try increasing --wait (current: {wait}s)')
            return [], None, False
        else:
            u.step('JS-CHECK', 'OK', 'no placeholder text detected')

        path = u.save_artifact(source_label, f'page_{page_num}_cleaned.txt', text)
        u.step('SAVED', 'INFO', path)
    else:
        # load cleaned text
        filename = f'page_{page_num}_cleaned.txt'
        if u.artifact_exists(source_label, filename):
            text = u.load_artifact(source_label, filename)
            u.step('CLEAN', 'SKIP', f'using saved artifact  ({u.fmt_size(len(text))})')
        else:
            u.step('CLEAN', 'SKIP', 'no saved cleaned text — re-cleaning from HTML')
            text = clean_html(html)

    if stop_after == 'clean':
        print(f'\n  [stopped at clean stage]')
        # Print full cleaned text
        print(f'\n  ── Full cleaned text ──')
        for line in text.splitlines():
            print(f'  │ {line}')
        print(f'  └── end')
        return [], None, False

    # ── STEP 3: CHUNK ────────────────────────────────────────────────────────
    if skip_clean:
        # Try to load pre-saved chunks
        chunk_files = []
        for ci in range(1, 20):
            fn = f'page_{page_num}_chunk_{ci}.txt'
            if u.artifact_exists(source_label, fn):
                chunk_text = u.load_artifact(source_label, fn)
                chunk_files.append(chunk_text)
            else:
                break
        if chunk_files:
            chunks = [(ct, i == len(chunk_files) - 1) for i, ct in enumerate(chunk_files)]
            u.step('CHUNK', 'SKIP', f'using {len(chunks)} saved chunk artifacts')
        else:
            # Fall back to chunking from text
            if len(text) <= config.LLM_CHUNK_SIZE:
                chunks = [(text, True)]
            else:
                chunks = list(_chunk_text(text))
            u.step('CHUNK', 'INFO', f're-chunked from text: {len(chunks)} chunks')
    else:
        t0 = time.time()
        if len(text) <= config.LLM_CHUNK_SIZE:
            chunks = [(text, True)]
            u.step('CHUNK', 'OK', f'{u.fmt_size(len(text))} → 1 chunk (no split needed)')
        else:
            chunks = list(_chunk_text(text))
            sizes = [u.fmt_size(len(c)) for c, _ in chunks]
            u.step('CHUNK', 'OK',
                   f'{u.fmt_size(len(text))} → {len(chunks)} chunks  [{", ".join(sizes)}]')
        t_chunk = time.time() - t0

        for ci, (chunk, _) in enumerate(chunks):
            path = u.save_artifact(source_label, f'page_{page_num}_chunk_{ci+1}.txt', chunk)
        if len(chunks) > 1:
            u.step('SAVED', 'INFO', u.artifact_path(source_label, f'page_{page_num}_chunk_*.txt'))

    if stop_after == 'chunk' or no_llm:
        print(f'\n  [stopped at chunk stage]')
        return [], None, False

    # ── STEPS 4-7: LLM + PARSE + VALIDATE + DEDUP ────────────────────────────
    all_events = []
    seen_titles: set[str] = set()
    next_page_url = None

    for ci, (chunk, is_last) in enumerate(chunks):
        chunk_label = f'chunk {ci+1}/{len(chunks)}'

        for provider in providers:
            u.banner(f'{chunk_label}  ·  provider={provider}')

            prompt = build_prompt(chunk, url, name, is_last)
            print(f'  Prompt size : {u.fmt_size(len(prompt))}  (~{u.estimate_tokens(prompt):,} tokens)')

            # Save prompt artifact
            ppath = u.save_artifact(source_label,
                                    f'page_{page_num}_chunk_{ci+1}_prompt.txt', prompt)
            u.step('SAVED', 'INFO', ppath)

            # Call LLM
            print(f'\n  Calling {provider} ...')
            content, duration, usage_or_err = call_llm(prompt, provider)

            if content is None:
                u.step('LLM', 'FAIL', f'{u.fmt_time(duration)} — {usage_or_err}')
                if stop_after == 'llm':
                    continue
                return all_events, None, False

            tok_info = ''
            if hasattr(usage_or_err, 'prompt_tokens'):
                tok_info = (f'prompt={usage_or_err.prompt_tokens}  '
                            f'completion={usage_or_err.completion_tokens}')
            u.step('LLM', 'OK', f'{u.fmt_time(duration)}  {tok_info}')
            t_llm += duration

            # Save response artifact
            rpath = u.save_artifact(source_label,
                                    f'page_{page_num}_chunk_{ci+1}_response.json', content)
            u.step('SAVED', 'INFO', rpath)

            # Show raw response
            print(f'\n  ── Raw LLM response ──')
            for line in content.splitlines():
                print(f'  │ {line}')
            print(f'  └── end response')

            if stop_after == 'llm':
                continue  # show raw but skip parse summary

            # ── PARSE ──────────────────────────────────────────────────────
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                u.step('PARSE', 'FAIL', f'JSONDecodeError: {e}')
                continue

            page_events = parsed.get('events', [])
            if is_last:
                next_page_url = parsed.get('next_page_url')

            u.step('PARSE', 'OK', f'{len(page_events)} events  next_url={next_page_url or "null"}')

            # ── VALIDATE ───────────────────────────────────────────────────
            drop_count   = 0
            no_url_count = 0
            for ev in page_events:
                ok, _ = u.parse_date_debug(ev.get('date'), ev.get('time') or None)
                if not ok:
                    drop_count += 1
                if not ev.get('url'):
                    no_url_count += 1

            if drop_count:
                u.step('VALIDATE', 'WARN',
                       f'{drop_count}/{len(page_events)} events have unparseable dates '
                       f'(sentinel date in production)')
            else:
                u.step('VALIDATE', 'OK', 'all dates parseable')
            if no_url_count:
                u.step('VALIDATE', 'WARN', f'{no_url_count}/{len(page_events)} events have no URL')

            # ── DEDUP ──────────────────────────────────────────────────────
            new_events = []
            dedup_count = 0
            for ev in page_events:
                title_key = (ev.get('title') or '').strip().lower()
                if title_key and title_key in seen_titles:
                    dedup_count += 1
                else:
                    if title_key:
                        seen_titles.add(title_key)
                    new_events.append(ev)

            all_events.extend(new_events)
            if dedup_count:
                u.step('DEDUP', 'INFO',
                       f'{dedup_count} duplicate titles removed  '
                       f'({len(new_events)} new, {len(all_events)} running total)')
            else:
                u.step('DEDUP', 'OK', f'no duplicates  ({len(all_events)} running total)')

        # Interactive pause between chunks
        if not auto and ci < len(chunks) - 1:
            resp = u.ask(f'Continue to chunk {ci+2}/{len(chunks)}?', 'y/n/skip/save')
            if resp == 'n':
                print('  Stopping.')
                return all_events, next_page_url, False
            elif resp == 'skip':
                print('  Skipping remaining chunks for this page.')
                break
            elif resp == 'save':
                print(f'  Artifacts saved to {u.artifact_path(source_label, "")}')
                print(f'  Resume: python debug/pipeline.py {source_label} --from llm --page {page_num}')
                return all_events, next_page_url, False

    return all_events, next_page_url, True


# ── Main ──────────────────────────────────────────────────────────────────────

def run(key: str, url_override: str | None, use_selenium_override: bool | None,
        wait_override: int | None, providers: list[str], stop_after: str | None,
        from_stage: str | None, no_llm: bool, auto: bool, page_filter: int | None):

    from scrape.core import close_driver

    # Resolve config
    if key:
        entry = u.get_source(key)
        name, start_url, use_selenium, wait, max_pages, note, _color, pag = entry
        url = url_override or start_url
        source_label = key
    else:
        name = url_override
        url = url_override
        use_selenium = use_selenium_override or False
        wait = wait_override or 6
        max_pages = 1
        pag = None
        source_label = 'custom'

    if use_selenium_override is not None:
        use_selenium = use_selenium_override
    if wait_override is not None:
        wait = wait_override

    stop_after = stop_after or ('chunk' if no_llm else None)
    skip_fetch = from_stage in ('clean', 'llm')
    skip_clean = from_stage == 'llm'

    if use_selenium and not skip_fetch:
        if not u.check_selenium_available():
            sys.exit(1)

    pag_type = (pag or {}).get('type', 'llm')

    print(f'\n{"═"*65}')
    print(f'  PIPELINE DEBUG: {name}')
    print(f'  Provider(s): {", ".join(providers)}  |  Pagination: {pag_type}')
    if from_stage:
        print(f'  Resuming from: {from_stage} (using saved artifacts)')
    if stop_after:
        print(f'  Stopping after: {stop_after}')
    print(f'{"═"*65}')

    total_start = time.time()
    grand_events = []
    pages_ok = 0
    pages_total = 0

    try:
        if pag_type == 'llm':
            # LLM pagination: follow next_page_url
            current_url = url
            visited: set[str] = set()
            page_num = 0

            while current_url and page_num < max_pages:
                page_num += 1
                if page_filter and page_num != page_filter:
                    if current_url in visited:
                        break
                    visited.add(current_url)
                    page_num += 1
                    continue

                if current_url in visited:
                    print(f'\n  Loop detected (page {page_num}), stopping.')
                    break
                visited.add(current_url)
                pages_total += 1

                events, next_url, ok = process_page(
                    key=key, source_label=source_label, name=name,
                    url=current_url, use_selenium=use_selenium, wait=wait,
                    page_num=page_num, providers=providers,
                    stop_after=stop_after, skip_fetch=skip_fetch,
                    skip_clean=skip_clean, no_llm=no_llm, auto=auto,
                )
                grand_events.extend(events)
                if ok:
                    pages_ok += 1

                if not ok or stop_after in ('fetch', 'clean', 'chunk'):
                    break

                if next_url and not next_url.startswith('http'):
                    print(f'\n  next_page_url is not absolute, stopping: {next_url}')
                    break

                current_url = next_url

                if current_url and not auto:
                    resp = u.ask(f'Continue to page {page_num+1}?', 'y/n')
                    if resp != 'y':
                        break

                if current_url:
                    time.sleep(2)

        else:
            # Non-LLM pagination: generate URLs upfront
            from debug.source import _compute_urls
            urls = _compute_urls(key, entry)
            for i, page_url in enumerate(urls):
                page_num = i + 1
                if page_filter and page_num != page_filter:
                    continue
                if '(page' in str(page_url):  # skip placeholder entries
                    continue

                pages_total += 1
                events, _, ok = process_page(
                    key=key, source_label=source_label, name=name,
                    url=page_url, use_selenium=use_selenium, wait=wait,
                    page_num=page_num, providers=providers,
                    stop_after=stop_after, skip_fetch=skip_fetch,
                    skip_clean=skip_clean, no_llm=no_llm, auto=auto,
                )
                grand_events.extend(events)
                if ok:
                    pages_ok += 1

                if not ok or stop_after in ('fetch', 'clean', 'chunk'):
                    break

                if not auto and i < len(urls) - 1:
                    resp = u.ask(f'Continue to page {page_num+1}/{len(urls)}?', 'y/n')
                    if resp != 'y':
                        break

    finally:
        if use_selenium:
            close_driver()

    # Final summary
    elapsed = time.time() - total_start
    u.banner('SUMMARY')
    u.step('Pages',  'OK' if pages_ok == pages_total else 'WARN',
           f'{pages_ok}/{pages_total} succeeded')
    u.step('Events', 'INFO', f'{len(grand_events)} total')
    u.step('Time',   'INFO', u.fmt_time(elapsed))
    artifacts_dir = u.artifact_path(source_label, '')
    if os.path.isdir(artifacts_dir):
        u.step('Artifacts', 'INFO', artifacts_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Full debug pipeline orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key from sources.py (or "list")')
    parser.add_argument('--auto', action='store_true',
                        help='No interactive pauses — run to completion')
    parser.add_argument('--page', type=int, default=None,
                        help='Process only this page number (1-indexed)')
    parser.add_argument('--stop-after', choices=['fetch', 'clean', 'chunk', 'llm'],
                        default=None, help='Stop pipeline after this stage')
    parser.add_argument('--no-llm', action='store_true',
                        help='Stop before any LLM calls (same as --stop-after chunk)')
    parser.add_argument('--from', dest='from_stage',
                        choices=['clean', 'llm'],
                        default=None,
                        help='Resume from this stage using saved artifacts '
                             '(clean=skip fetch, llm=skip fetch+clean+chunk)')
    parser.add_argument('--provider', default='default',
                        help='groq | ollama | both | default')
    parser.add_argument('--url', default=None,
                        help='Override start URL (or use without --key for arbitrary URLs)')
    parser.add_argument('--selenium', action='store_true',
                        help='Force Selenium (for --url mode)')
    parser.add_argument('--wait', type=int, default=None,
                        help='Override Selenium wait seconds')
    args = parser.parse_args()

    if args.key == 'list' or (not args.key and not args.url):
        u.list_sources()
        return

    import config
    if args.provider == 'both':
        providers = ['groq', 'ollama']
    elif args.provider == 'default':
        providers = [config.LLM_PROVIDER]
    else:
        providers = [args.provider]

    run(
        key=args.key if args.key not in ('list', None) else None,
        url_override=args.url,
        use_selenium_override=True if args.selenium else None,
        wait_override=args.wait,
        providers=providers,
        stop_after=args.stop_after,
        from_stage=args.from_stage,
        no_llm=args.no_llm,
        auto=args.auto,
        page_filter=args.page,
    )


if __name__ == '__main__':
    main()
