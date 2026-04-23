# debug_artifacts/

Populated automatically by every scrape run (`llm_scraper.py`) and the debug
pipeline (`debug_*.py`). Per-source subdirectories contain:

- `page_N_raw.html` — raw HTML from fetch
- `page_N_cleaned.txt` — after `clean_html()` + `apply_trim()`
- `page_N_chunk_M.txt` — chunked cleaned text
- `page_N_chunk_M_prompt.txt` — prompt sent to Groq/Ollama
- `page_N_chunk_M_response.json` — raw LLM response
- `run_summary.json` — events_found/added + skip reasons

Useful for:

- Finding/verifying a new site's `TRIM_PATTERN` (see `HOW_TO_ADD_SCRAPERS.md`)
- Post-mortem on a scrape that returned zero events
- Seeing the exact text the LLM saw, without re-fetching or re-billing

In Docker, `.:/app` is bind-mounted, so the directory you're looking at on the
host is the same one the scraper container writes to. No `docker cp` needed.

Gitignored except this README and `.gitkeep`.
