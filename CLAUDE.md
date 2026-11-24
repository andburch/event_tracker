# CLAUDE.md -- Phoenix Valley Events Recommender

## What this is

A personal, daily-use tool for finding interesting events in Phoenix Valley, AZ. Pragmatism over polish -- working and low-maintenance beats clever and brittle. It is not built for others or for showcase.

---

## Adding a new scraper

When asked to add a scraper, follow this sequence:

1. **Visit the site** -- fetch or browse it; determine static HTML vs JS-rendered, how pagination works, and what platform it's on (WordPress, Squarespace, Civic Plus, Localist, etc.)
2. **Go slow, be thorough** -- Don't be afraid to increase wait times, add slow scrolls to load more content, see if you can take a screenshot of the page and inspect it. Really take a deep look.
3. **Find a similar existing source** -- check `sources.py` for a site on the same platform or with the same pagination pattern and use it as your template. We don't want to create a lot of code bloat.
4. **Add both entries to `sources.py`** -- the `SITES` tuple AND a `TRIM_PATTERNS` entry (see below). Both are required.
5. **Test**: `python tools/test_scraper.py <key>` -- confirm events are actually found
6. **If it fails**: try 1-2 obvious fixes (wrong `use_selenium` flag, `wait_secs` too short), then **stop and describe exactly what you see** -- the user is the expert at debugging specific sites; don't thrash. Ask for a screenshot if needed.

Full reference: `HOW_TO_ADD_SCRAPERS.md`

### Finding the trim pattern (required for every new site)

Every site must have a `TRIM_PATTERNS` entry in `sources.py`. This strips nav menus, filter sidebars, cookie banners, and calendar grids from the cleaned HTML before it reaches the LLM -- reducing tokens and speeding up local models by 1.5-2.6x.

```bash
# 1. Collect a cleaned-text artifact
python3 debug/collect_artifacts.py     # skips sites that already have artifacts

# 2. Inspect where events start
head -200 debug_artifacts/<key>/page_1_cleaned.txt

# 3. Verify your pattern appears exactly once
python3 -c "
text = open('debug_artifacts/<key>/page_1_cleaned.txt').read()
print(text.count('your pattern here'))   # must be 1
"
```

Good trim patterns:
- **2-3 lines** of context -- not a single common word like "Go" or "All"
- **UI-specific** -- not something that could appear in an event title or venue name
- **Month-independent** -- avoid category names or event titles that rotate
- **Page-consistent** -- appears on page 2 and 3 as well as page 1

Set to `None` if the page opens directly with events (no boilerplate).

---

## Hard-won lessons

- **Try not to invent new pagination patterns.** The 5 types (`None`/LLM, `multi_month`, `url_param`, `js_button`, `calendar_grid`) cover almost everything. Find the closest match before considering anything else.
- **Check for platform patterns first.** Sites on the same backend often share the exact same config. Look at existing sources before starting from scratch.
- **Always set a trim pattern.** Boilerplate before events wastes LLM tokens and can break local models. Even a `None` is better than a missing entry (it means you checked).
- **Groq rate limits are a real constraint.** Default to conservative `max_pages` (3-5) unless we are running local LLMs. Don't add extra LLM calls to an API. Check the `/llm-usage` dashboard before bulk scraping -- it shows rolling 24h daily token (TPD) usage from the DB, which is the limit that actually matters. `tools/check_groq_quota.py` only shows per-minute tokens and daily request counts from Groq's API headers -- Groq does NOT expose daily token usage in headers, so that script can look "fully reset" even when the daily token budget is exhausted.
- **Bot detection is probabilistic.** A scraper failing once doesn't mean the config is wrong -- it might be Akamai/Cloudflare on a bad day. Try a longer `wait_secs` or fresh Selenium session before assuming the config is broken.
- **Config-only is a solved problem.** The whole point is that new scrapers require nearly zero new Python code. If you find yourself writing a custom fetch or parse function, stop and reconsider.
- **Chunk failures: salvage what we can, then continue -- but never silently.** When Groq's JSON-mode validator rejects a response with `json_validate_failed` (400), `scrape/core.py:_recover_partial_json` trims the partial output back to the last complete event so the chunk isn't a total loss. If the failed generation is *empty* (common with gpt-oss models), the chunk is retried up to `LLM_MAX_RETRIES`. Note: the openai SDK already unwraps `{"error": {...}}` into `e.body`, so read `failed_generation`/`code` from `e.body` directly (before 2026-11-24 the code looked one level too deep and salvage never ran). If **every** chunk of a page fails, `ask_llm` raises so the run is recorded as failed instead of "success, 0 events". Errors are logged to `groq_rate_limit_events` and shown under "LLM Errors" on `/llm-usage`.
- **Groq retires models without warning.** In Aug 2026 Groq removed `llama-3.3-70b-versatile` and `llama-4-scout`; every call 404'd and ingestion was dead for 3 months unnoticed. Now a 404 (`openai.NotFoundError`) makes the rate limiter drop that model for the run and try the next one in `LLM_SCRAPING_MODELS`/`LLM_SCORING_MODELS`. If *all* configured models are gone it raises a clear error. Check current models with `client.models.list()` and update `config.py`; add new models' limits to `_GROQ_LIMITS_SEED` in `database/models.py` (unknown models get a conservative 6k TPM / 100k TPD fallback).
- **Failures must be loud.** `llm_scraper.py` exits 1 when every site in the run failed or the run found 0 events total (one flaky site does NOT fail the run). `score_events.py` exits 1 if there were events but none got scored. The systemd units have `OnFailure=events-alert@%n.service`, which runs `scripts/notify.sh` to push an ntfy alert (topic in `~/.config/homeserver-alerts/topic`, outside the repo). `~/check-services.sh` also fails if no scrape has added events in 3+ days.
- **Timezone: containers run `TZ=America/Phoenix`** (set in `docker-compose.yml`). `Event.date` is Phoenix local time, so `datetime.now()` must be Phoenix too or tonight's events vanish after 5pm. DB timestamps (`created_at`, `run_timestamp`, LLM call logs) still use `utcnow()`, which is explicitly UTC and unaffected.
- **Don't set `max_tokens` on Groq calls.** Groq checks `prompt_tokens + max_tokens` against TPM *before* running the request. Since we don't know prompt size upfront, a fixed `max_tokens` will either be too small (truncating JSON output, dropping events) or too large (rejected for exceeding TPM). Let each model use its default and handle the occasional "max completion tokens" 400 error gracefully instead. Ollama is different -- it has no TPM constraint, and its default output (~2K) is too low, so `OLLAMA_MAX_TOKENS` (16384) is set explicitly in config.

---

## Intentional decisions -- do not "fix" these

| Thing | Why it exists |
|---|---|
| Sentinel time `12:34` | Marks events with no specified time; used throughout date logic. No event would REALLY have this as its time. |
| All scraper config in `sources.py` | Avoids custom scraper code sprawl -- both `SITES` and `TRIM_PATTERNS` live here |
| Groq + LLM model names | Set in `config.py`; don't hardcode model names elsewhere |
| `TRIM_PATTERNS` in `sources.py` not a separate file | Keeps all per-site config in one place; easier to review when adding a site |
| **Scoring is manual, not auto-triggered** | `llm_scraper.py` does NOT call `run_batch_scoring()`, and editing the taste profile does NOT rescore events. You must run `python score_events.py` (or `score_events.py --all` after a profile change) yourself. This keeps the scrape path and the scoring path independent so rate-limit/quota issues in one don't cascade into the other. Both paths share the multi-key Groq rate limiter via `llm.provider.call_llm()`. |
| **No `max_tokens` on Groq calls** | Groq validates `prompt + max_tokens <= TPM` upfront. We can't know prompt size before sending, so any fixed value risks either truncation (too low) or TPM rejection (too high). Ollama has `OLLAMA_MAX_TOKENS=16384` because its default (~2K) is too small and there's no TPM constraint. |
| **Frontend JS libs vendored in `server/static/`, not loaded from CDN** | The dashboard is accessed from phones over LAN/VPN to `homeserver-vm:5000`. CDN requests (jsdelivr, etc.) hang indefinitely on some mobile networks/blockers, leaving the page stuck loading with a blank chart area. Drop new JS deps into `server/static/` and reference via `url_for('static', filename=...)`. |

---

## Key commands

```bash
python llm_scraper.py <key>              # Scrape one site
python score_events.py                   # Score unscored events (manual, not automatic)
python score_events.py --all             # Re-score all future events (after profile edits)
python tools/test_scraper.py <key>       # Test without DB writes
python tools/test_scraper.py <key> --dump # See raw HTML the LLM receives
python tools/check_groq_quota.py         # Check per-minute tokens & daily requests (NOT daily tokens -- see /llm-usage for that)

# Debug pipeline (step-by-step inspection)
python3 debug/fetch.py <key>             # Fetch raw HTML, check for bot-blocks
python3 debug/clean.py <key>             # Clean HTML, show tag stats
python3 debug/chunk.py <key>             # Visualize chunking
python3 debug/llm.py <key>               # Send to LLM, show raw response + parse
python3 debug/pipeline.py <key>          # Full pipeline with interactive pauses

# Artifact collection (for trim pattern research)
python3 debug/collect_artifacts.py       # Fetch + clean page 1 for all sites
```

See `QUICK_REFERENCE.md` for the full command list.
