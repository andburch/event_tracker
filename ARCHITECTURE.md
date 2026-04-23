# Phoenix Events Recommender — Architecture

A configuration-driven event aggregator that scrapes 32 Phoenix Valley sources, stores them in SQLite, and ranks them by personal preference with an LLM.

## System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                      USER-FACING SURFACES                          │
├────────────────────────────────────────────────────────────────────┤
│  Web UI (server/app.py)        CLI                                 │
│  ├─ /           event list     ├─ llm_scraper.py                   │
│  ├─ /calendar   month grid     ├─ score_events.py                  │
│  ├─ /profile    taste config   ├─ tools/test_scraper.py            │
│  ├─ /health     run history    └─ tools/tools/check_groq_quota.py        │
│  ├─ /llm-usage  token/TPD                                          │
│  └─ /feedback   👍/👎                                              │
└────────────┬──────────────────────┬────────────────────────────────┘
             │                      │
             ▼                      ▼
┌────────────────────────────────────────────────────────────────────┐
│                      SCRAPING + LLM LAYER                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   sources.py ──▶ scrape/pagination.py ──▶ scrape/core.py           │
│   (SITES +         (5 pagination           (fetch, clean, chunk,   │
│    TRIM_PATTERNS)   handlers)                ask_llm)              │
│                                                     │              │
│                                                     ▼              │
│                                           llm/provider.call_llm()  │
│                                                     │              │
│                             ┌───────────────────────┼───────────┐  │
│                             ▼                                   ▼  │
│                     llm/rate_limiter.py                      Ollama│
│                     (multi-key, per-                      (optional│
│                      model TPM/TPD                        fallback)│
│                      bookkeeping)                                  │
│                             │                                      │
│                             ▼                                      │
│                           Groq API                                 │
│                                                                    │
└───────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                 │
├────────────────────────────────────────────────────────────────────┤
│   SQLite (events.db, WAL mode) — database/models.py                │
│   ├─ Event                    scraped events + score + pinned      │
│   ├─ ScraperRun               per-site run history                 │
│   ├─ LLMCall                  every Groq/Ollama call for /llm-usage│
│   ├─ GroqModelLimit           quota table seeded from Groq docs    │
│   ├─ UserProfile              taste_prompt + rolling summary       │
│   ├─ FeedbackHistory          👍/👎 by event                       │
│   └─ PreferenceProfileHistory taste-summary evolution              │
└────────────────────────────────────────────────────────────────────┘
```

## Containerization

```
                    host :5000
                       │
                 ┌─────▼─────┐
                 │    web    │◀── gunicorn, always up
                 └─────┬─────┘
                       │  events_data volume (SQLite, WAL)
                       ├────────────────────────────┐
                       ▼                            ▼
              ┌────────────────────┐       ┌──────────────┐
              │ scraper            │       │   ollama     │
              │ `compose run`      │─────▶ │  (optional,  │
              │ one-shot,          │  :11434  profile-gated)│
              │ chromium+selenium  │       └──────────────┘
              └─────────┬──────────┘
                        │
        ./debug_artifacts/ ← live scrape artifacts on host
```

Three services, one shared image:

- **web** — Flask + gunicorn, always up. Serves UI and subprocess-forks `score_events.py` for the Score button.
- **scraper** — ephemeral, profile-gated, invoked with `docker compose run --rm scraper <cmd>`. Has chromium + selenium for JS-heavy sites.
- **ollama** — optional, profile-gated. Only needed when Groq is exhausted and `GROQ_FALLBACK_TO_OLLAMA=true`.

web and scraper share `.:/app` (live code edits + artifacts visible on host) and `events_data:/data` (SQLite file). SQLite WAL is enabled at engine creation so both can safely read/write concurrently.

## Scraping Flow

```
python llm_scraper.py fibber
│
├─▶ main()
│   ├─ Parse CLI args, resolve {today}/{plus90} in base URL
│   ├─ Purge existing events (preserves pinned)
│   └─▶ for each key:
│       │
│       └─▶ scrape_and_save(key, ...)
│           │
│           ├─▶ scrape.pagination.scrape_with_pagination()
│           │   │
│           │   ├─ Dispatch on pagination type:
│           │   │   ├─ None / 'llm'      LLM finds next_page_url
│           │   │   ├─ 'multi_month'     generate month URLs
│           │   │   ├─ 'url_param'       increment ?page=N
│           │   │   ├─ 'js_button'       Selenium clicks Next
│           │   │   └─ 'calendar_grid'   month grid + date injection
│           │   │
│           │   └─▶ for each page:
│           │       ├─ fetch_requests() or fetch_selenium()
│           │       ├─ clean_html()          strip <script>/<nav>/etc.
│           │       ├─ apply_trim()          strip site-specific boilerplate
│           │       ├─ scrape.artifacts.save() live debug_artifacts write
│           │       ├─ chunk if >6000 chars
│           │       └─ ask_llm() → call_llm() → Groq (→ Ollama on 429/exhaustion)
│           │
│           ├─ parse_date() per event (YYYY-MM-DD + sentinel 12:34 fallback)
│           ├─ Skip past events (except ongoing date ranges)
│           ├─ Dedup by (title, date)
│           └─ Commit Event rows + append ScraperRun
│
└─▶ print summary, close driver
```

Scoring is a **separate path**, not called from `scrape_and_save`. That's deliberate (see Intentional Decisions below).

## Pagination Types

| Type | Sites that use it | What it does |
|---|---|---|
| `None` (LLM) | `fibber`, `rak`, `scottsdale`, `tempe_lib`, `chandler_center`, many others | LLM extracts next_page_url from page text |
| `multi_month` | `dirtydrummer`, `sweet_basil` | Generate N month URLs from a template |
| `url_param` | `chandler` (0-indexed), `chandler_lib`, `mesa` | Increment `?page=N` in URL |
| `js_button` | `phoenix`, `azmnh`, `az_worm_farm` | Selenium clicks Next between pages |
| `calendar_grid` | `gilbert`, `tca` | Month-view grid with injected full dates for LLM context |

## LLM Layer

Everything that calls an LLM — scraping, scoring, preference summaries — goes through **`llm/provider.call_llm()`**. It selects between Groq and Ollama based on `config.LLM_PROVIDER` and per-call overrides, records every call in the `llm_calls` table, and delegates rate limit bookkeeping to `llm/rate_limiter.py`.

**llm/rate_limiter.py** tracks per-(key, model) state:
- TPM (per-minute tokens) and TPD (per-day tokens) budgets read from `GroqModelLimit` table
- Multiple keys rotate combinatorially: tries all keys with model[0] first, then all keys with model[1], etc.
- On a 429, parses the error body, cross-references with our local `llm_calls` history to classify TPM vs TPD exhaustion, and blocks that specific (key, model) pair for the right duration.
- When all (key, model) combinations are exhausted AND `GROQ_FALLBACK_TO_OLLAMA=true`, falls through to Ollama.

This is why scraping and scoring share the rate limiter — a quota burn in one path correctly blocks the other.

## Scoring Path

```
python score_events.py [--all]
│
└─▶ recommender.llm_filter.run_batch_scoring(rescore_all)
    │
    ├─ Load UserProfile (taste_prompt + preference_summary)
    ├─ Query Event rows (score IS NULL, or all future with --all)
    ├─ Chunk into batches of SCORING_CHUNK_SIZE
    │
    └─▶ for each batch:
        ├─ Build prompt: profile + events JSON + 0.0–1.0 scoring rubric
        ├─ llm.provider.call_llm(call_type='scoring')
        ├─ Parse JSON array, update Event.score in place
        └─ Commit per batch (failures don't lose the whole run)
```

`/profile` feedback updates `UserProfile.preference_summary` automatically after every 10 thumbs-up/down (`SUMMARY_THRESHOLD`), but **does not trigger rescoring**. Run `score_events.py --all` yourself when you want the new summary to reshape scores.

## Component Responsibilities

| File | Role |
|---|---|
| `sources.py` | Single source of truth: `SITES` dict + `TRIM_PATTERNS` dict. Add a scraper by editing this file only. |
| `scrape/pagination.py` | 5 pagination handlers + `scrape_with_pagination()` entry point. Dispatches by `pagination_config['type']`. |
| `scrape/core.py` | `fetch_requests()`, `fetch_selenium()`, `clean_html()`, `apply_trim()`, `ask_llm()`, driver lifecycle. |
| `scrape/artifacts.py` | Writes raw HTML + cleaned text to `debug_artifacts/<key>/` on every scrape. |
| `llm_scraper.py` | CLI entry point, date parsing, dedup, DB persistence, ScraperRun logging. |
| `llm/provider.py` | `call_llm()` — unified Groq/Ollama entry point, records to `llm_calls`. |
| `llm/rate_limiter.py` | Per-(key, model) TPM/TPD bookkeeping, 429 classification, fallback logic. |
| `debug/` | Step-by-step pipeline tools: `fetch.py`, `clean.py`, `chunk.py`, `llm.py`, `pipeline.py`, `source.py`, `collect_artifacts.py`, `utils.py`. |
| `tools/` | CLI utilities: `test_scraper.py` (no-DB scrape test), `tools/check_groq_quota.py` (per-minute quota). |
| `database/models.py` | SQLAlchemy models + engine setup + WAL bootstrap + seed data. |
| `recommender/llm_filter.py` | `run_batch_scoring()`, `score_events()` (read-only for UI), `maybe_update_preference_summary()`. |
| `server/app.py` | Flask routes: event list, calendar, profile, health, llm-usage, feedback, pin, score subprocess. |
| `wsgi.py` | gunicorn entry point (`app` export). |
| `config.py` | Env-driven config: API keys, DB URL, Ollama URL, chunking params, retry/backoff. |

## Intentional Decisions

- **Scoring is manual.** `llm_scraper.py` doesn't call `run_batch_scoring()`, and profile edits don't retroactively rescore. Keeps scrape-path and scoring-path rate-limit issues from cascading.
- **No `max_tokens` on Groq calls.** Groq validates `prompt + max_tokens ≤ TPM` before running. We can't know prompt size upfront, so any fixed value risks truncation (too low) or TPM rejection (too high). Ollama is exempt — it has no TPM and needs `OLLAMA_MAX_TOKENS=16384` explicitly because its default is too small.
- **Sentinel time `12:34`** marks events with no specified time. Used throughout date logic; no real event would ever land on exactly this minute.
- **All scraper config in `sources.py`** (both `SITES` and `TRIM_PATTERNS`). Avoids custom-code sprawl per-site; keeps per-site config reviewable at a glance.
- **SQLite, not Postgres.** Single-user tool. WAL + one writer + multiple readers handles the web/scraper split cleanly. Switching would add a service + migrations + backup story for zero real benefit.
- **Groq first, Ollama optional.** Groq is fast and the free tier covers normal usage. Ollama is only needed when both Groq keys are daily-exhausted, so it lives behind a compose profile.
- **`.:/app` bind mount.** Lets code edits apply without rebuilding, and makes every scrape's `debug_artifacts/` live on the host filesystem automatically.

## Data Flow Summary

```
1. SCRAPE   → HTML → clean text → LLM extraction → Event row (score=NULL)
2. SCORE    → Event rows + profile → LLM batch → Event.score updated
3. DISPLAY  → UI reads Event rows sorted by score
4. FEEDBACK → 👍/👎 → FeedbackHistory row → after 10, regenerate preference_summary
5. PROFILE EDIT → UserProfile updated → you run score_events.py --all to propagate
```

## Adding a New Source (summary)

1. Add `SITES[<key>]` tuple and `TRIM_PATTERNS[<key>]` in `sources.py`.
2. `docker compose run --rm scraper python debug/collect_artifacts.py` (or bare-Python equivalent).
3. Inspect `debug_artifacts/<key>/page_1_cleaned.txt` to verify trim pattern.
4. `docker compose run --rm scraper python llm_scraper.py <key>`.

Full walkthrough with trim-pattern research in `HOW_TO_ADD_SCRAPERS.md`.

## Debugging

Step-by-step pipeline tools, each stopping at a different stage:

```bash
python3 debug/fetch.py <key>       # raw HTML, bot-block checks
python3 debug/clean.py <key>       # cleaned text, tag stats, trim impact
python3 debug/chunk.py <key>       # chunk visualization
python3 debug/llm.py <key>         # LLM call (or --dry-run)
python3 debug/pipeline.py <key>    # full pipeline with interactive pauses
python3 debug/source.py <key>      # config inspection (no fetch)
```

All of these use `debug/utils.py` and write to the same `debug_artifacts/<key>/` as production scrapes.

## Observability

- **`/health`** — per-source run success, last-run timestamp, event counts, recent failures.
- **`/llm-usage`** — rolling 24h token usage per (key, model), budget cards with TPD %, Chart.js usage graph, recent call log, recent 429/error log. Authoritative for "is my daily token budget exhausted?" since Groq doesn't expose TPD in API headers.
- **`tools/tools/check_groq_quota.py`** — per-minute TPM and daily RPD from Groq's API headers only. Does NOT show daily tokens. Useful for per-minute state but misleading for daily-budget debugging.
- **console logs** — chunk failures (400s, "max completion tokens") are logged here but NOT written to the DB, so they're invisible on `/llm-usage`. A scrape that "succeeded" may have silently lost a chunk. Watch for `chunk X/Y failed`.
