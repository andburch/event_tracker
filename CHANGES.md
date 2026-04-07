# Recent Changes

## Session 2 (2026-04-07)

### Bug fix: ASU Kerr (and any Tribe Events site) events had no titles or URLs

**Root cause** — `clean_html()` in `llm_scrape_core.py` decomposed all `<header>` HTML
tags to strip page navigation. WordPress's "The Events Calendar" (Tribe Events) plugin
wraps each event card's title block in a semantic
`<header class="tribe-events-calendar-list__event-header">`, so the wholesale strip
removed every event title and its clickable URL before the text reached the LLM. The
LLM fell back to using the event description as the title, and stored an empty URL.

**Fix** — Removed `'header'` from the strip list in `clean_html()`. Page-level
navigation headers are already handled by stripping `<nav>`, and per-site
`TRIM_PATTERNS` in `sources.py` handles any remaining boilerplate.

**Files changed**
- `llm_scrape_core.py` — removed `'header'` from tag strip list; added comment explaining why
- `sources.py` — updated ASU Kerr note from "no per-event URLs" to "WordPress + The Events Calendar plugin"
- `_test_llm_scrape.py` — fixed two stale references: `SITES` now imported from `sources`, not `llm_scrape_core`; SITES tuple unpack updated for 8-element tuple (added `pagination_cfg` field)

**DB cleanup** — 13 old broken ASU Kerr records (descriptions stored as titles, empty URL)
deleted manually after re-scrape populated correct records.

---

## Session 1 (2026-04-07)

### Multi-key Groq rate limiter (`groq_rate_limiter.py`)

New module that manages multiple Groq API keys, switches between them on 429 errors,
classifies rate limits as TPM (per-minute, recoverable) vs TPD (daily, block key for
the day), and falls back to Ollama when all keys are exhausted.

- Reads `GROQ_API_KEY` and `GROQ_API_KEY_2` from `.env`
- Per-(key, model) blocking with rolling 24h token usage windows
- Classifies 429 errors by parsing the error message body: mentions of hours/day → TPD,
  short wait times → TPM. Cross-references rolling DB usage against `groq_model_limits`
  table for ambiguous cases.
- Exposes `record_rate_limit()` called by `llm_provider.py` on every 429

### `GroqModelLimit` DB table (`database/models.py`)

New table seeded at startup with free-tier limits for every model in Groq's docs.
Used by the rate limiter to classify 429 errors without hardcoded constants.
Insert-if-not-exists seeding preserves any manual edits for paid tiers.

Removed `GROQ_TPM_LIMIT` and `GROQ_TPD_LIMIT` from `config.py` — replaced by DB table.

### `/llm-usage` dashboard (`server/app.py`, `server/templates/llm_usage.html`)

New page showing:
- Budget cards per (API key, model): rolling 24h token usage vs TPD, with "next tick"
  and "free at" reset-time indicators
- Live Groq rate limit headers via direct `httpx` call (remaining requests/tokens today)
- Hourly chart (last 7 days) with Y-axis as % of daily token limit
- Full `llm_calls` log table
- `groq_model_limits` reference table

Nav link added to all pages (calendar, health, index, profile).

### Scraper health page improvements (`server/templates/health.html`)

- Status classification rewritten: `last_success` is now the primary signal. A scraper
  is Healthy if its most recent run succeeded and found events; only demoted to Flaky
  if success rate drops below 50% over 7 days. Previously, old failures in the window
  dragged success_rate below 80% and marked working scrapers as Warning.
- Removed "LLM Provider Timing" section (moved to `/llm-usage`).

### Bug fix: `name 'retry_after' is not defined` (`llm_provider.py`)

The 429 handler log message referenced `retry_after`, a variable only in scope inside
`record_rate_limit()`. Removed the reference; retry timing is logged inside the rate
limiter instead.

### Removed all "corporate firewall" references

Removed SSL bypass comments and corporate network notes from:
`llm_scrape_core.py`, `recommender/llm_filter.py`, `check_groq_quota.py`,
`sources.py`, `config.py`, `test_recommender.py`, `ARCHITECTURE.md`, `README.md`,
`.kiro/steering/tech.md`, `.env.example`
