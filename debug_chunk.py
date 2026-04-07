"""
debug_chunk.py -- Stage 3: Visualize how cleaned text gets chunked.

Shows chunk count, sizes, estimated tokens, first/last 200 chars of each chunk,
and the overlap zones between adjacent chunks. Useful for spotting events that
fall across chunk boundaries.

USAGE
-----
    python debug_chunk.py <key>                                      # fetch + clean + chunk
    python debug_chunk.py <key> --page 2                            # page 2
    python debug_chunk.py --file /tmp/debug/source/page_1_cleaned.txt
    python debug_chunk.py --file text.txt --chunk-size 8000 --overlap 500
    python debug_chunk.py list                                       # list all site keys

Saves: /tmp/debug/{source}/page_N_chunk_M.txt  (one file per chunk)
"""

import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import debug_utils as u


def run(key: str | None, source_label: str, text_file: str | None,
        page_num: int, chunk_size_override: int | None,
        overlap_override: int | None, save: bool):

    import config
    from llm_scrape_core import _chunk_text

    u.banner(f'CHUNK  ·  {source_label}')

    chunk_size = chunk_size_override or config.LLM_CHUNK_SIZE
    overlap    = overlap_override    or config.LLM_CHUNK_OVERLAP

    print(f'  Chunk size : {chunk_size:,} chars')
    print(f'  Overlap    : {overlap:,} chars')

    # Get cleaned text
    if text_file:
        print(f'  Source     : file  {text_file}')
        try:
            with open(text_file) as f:
                text = f.read()
        except FileNotFoundError:
            u.step('LOAD', 'FAIL', f'File not found: {text_file}')
            sys.exit(1)
        u.step('LOAD', 'OK', u.fmt_size(len(text)))
    else:
        # Fetch + clean live
        entry = u.get_source(key)
        name, start_url, use_selenium, wait, max_pages, note, _color, _pag = entry
        print(f'  Source     : live  {start_url}')
        from llm_scrape_core import fetch_requests, fetch_selenium, close_driver, clean_html
        try:
            if use_selenium:
                if not u.check_selenium_available():
                    sys.exit(1)
                html = fetch_selenium(start_url, wait)
            else:
                html = fetch_requests(start_url)
            text = clean_html(html)
            u.step('FETCH+CLEAN', 'OK', u.fmt_size(len(text)))
        except Exception as e:
            u.step('FETCH+CLEAN', 'FAIL', str(e))
            sys.exit(1)
        finally:
            if use_selenium:
                close_driver()

    # JS placeholder check before chunking
    warnings = u.check_empty_or_placeholder(text)
    if warnings:
        for w in warnings:
            u.step('JS-CHECK', 'WARN', w)
        u.step('CHUNK', 'SKIP', 'skipping chunk step due to empty/placeholder text')
        return

    # Chunk
    if len(text) <= chunk_size:
        chunks = [(text, True)]
        u.step('CHUNK', 'OK', f'{u.fmt_size(len(text))} → 1 chunk (no split needed)')
    else:
        chunks = list(_chunk_text(text))
        sizes = [u.fmt_size(len(c)) for c, _ in chunks]
        u.step('CHUNK', 'OK',
               f'{u.fmt_size(len(text))} → {len(chunks)} chunks  [{", ".join(sizes)}]')

    # Per-chunk detail
    for i, (chunk, is_last) in enumerate(chunks):
        role = 'last — pagination search active' if is_last else 'intermediate — no pagination search'
        print(f'\n  ── Chunk {i+1}/{len(chunks)}  ({u.fmt_size(len(chunk))},  '
              f'~{u.estimate_tokens(chunk):,} tokens)  [{role}]')

        # First 200 chars
        lines_start = chunk[:200].splitlines()
        print(f'  │ [first 200 chars]')
        for line in lines_start:
            print(f'  │ {line}')

        # Last 200 chars (if different)
        if len(chunk) > 400:
            print(f'  │ ...')
            lines_end = chunk[-200:].splitlines()
            print(f'  │ [last 200 chars]')
            for line in lines_end:
                print(f'  │ {line}')

        # Overlap zone to next chunk
        if i < len(chunks) - 1:
            overlap_actual = config.LLM_CHUNK_OVERLAP
            overlap_text = chunk[-overlap_actual:]
            next_chunk = chunks[i+1][0]
            next_start  = next_chunk[:overlap_actual]
            print(f'\n  ── Overlap zone {i+1}→{i+2}  ({overlap_actual} chars from end of chunk {i+1})')
            for line in overlap_text.splitlines():
                print(f'  ║ {line}')

        # Save chunk artifact
        if save:
            filename = f'page_{page_num}_chunk_{i+1}.txt'
            path = u.save_artifact(source_label, filename, chunk)

    if save:
        last_chunk_path = u.artifact_path(source_label, f'page_{page_num}_chunk_{len(chunks)}.txt')
        chunk1_path = u.artifact_path(source_label, f'page_{page_num}_chunk_1.txt')
        u.step('SAVED', 'OK', u.artifact_path(source_label, f'page_{page_num}_chunk_*.txt'))
        print(f'\n  Next step:')
        print(f'    docker compose run --rm web python debug_llm.py --file {chunk1_path} --source {source_label}')


def main():
    parser = argparse.ArgumentParser(description='Visualize text chunking')
    parser.add_argument('key', nargs='?', default=None,
                        help='Site key from sources.py (or "list")')
    parser.add_argument('--file', default=None,
                        help='Use saved cleaned text file')
    parser.add_argument('--source', default=None,
                        help='Source key for artifact naming (with --file)')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number for artifact filename (default: 1)')
    parser.add_argument('--chunk-size', type=int, default=None,
                        help='Override chunk size (default: from config)')
    parser.add_argument('--overlap', type=int, default=None,
                        help='Override overlap chars (default: from config)')
    parser.add_argument('--no-save', action='store_true',
                        help="Don't save chunk artifacts")
    args = parser.parse_args()

    if args.key == 'list':
        u.list_sources()
        return

    if not args.key and not args.file:
        parser.print_help()
        sys.exit(1)

    source_label = args.key or args.source or 'custom'

    run(
        key=args.key,
        source_label=source_label,
        text_file=args.file,
        page_num=args.page,
        chunk_size_override=args.chunk_size,
        overlap_override=args.overlap,
        save=not args.no_save,
    )


if __name__ == '__main__':
    main()
