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

### Bug fix: Raising Arizona Kids returning only page 1 of events

**Root cause** — RAK has a huge Category/Age/Neighborhood filter sidebar (~230 lines,
~3k chars) that renders **after** the event list and its "Next >" pagination link.
`ask_llm()` only looks for `next_page_url` in the **last chunk** (to avoid the LLM
hallucinating pagination from unrelated context). With the sidebar padding the page,
"Next >" got pushed into an earlier chunk and was never seen, so pagination stopped
at page 1 every time. Used to work before boilerplate trimming was added — the prior
scraper read the whole page at once.

**Fix** — Extended `TRIM_PATTERNS` to accept a `(head, tail)` tuple. `head` strips
pre-event boilerplate as before; `tail` strips everything from its marker to the end.
Updated `pagination_engine.apply_trim()` to handle both forms.

```python
'rak': ("Displaying:\nAll\n", "Calendar\nsearch our Calendar"),
```

Also bumped `rak` `max_pages` from 5 → 10.

**Files changed**
- `pagination_engine.py` — `apply_trim()` now handles str or (str, str) tuple
- `sources.py` — `rak` gets tuple trim pattern; `max_pages` 5 → 10; docstrings updated
- `_test_llm_scrape.py` — now calls `apply_trim()` so it matches production behavior

### 429 audit log (`GroqRateLimitEvent` table)

Before: 429 classifications went only to stdout, so after-the-fact "why did key N get
blocked" questions were unanswerable.

Now: every 429 is persisted to `groq_rate_limit_events` with key label, model,
classification (`daily` vs `tpm`), `retry_after_sec`, and a 500-char error snippet.
Surfaced on `/llm-usage` as "Rate Limit Events (last 50 · 429 audit log)".

- `database/models.py` — new `GroqRateLimitEvent` class
- `groq_rate_limiter.py` — `_log_rate_limit_event()` called from `record_rate_limit()`
- `server/app.py` — `/llm-usage` query and template context
- `server/templates/llm_usage.html` — audit log section with colored classification

### `check_groq_quota.py` — multi-key support

Previously only checked `GROQ_API_KEY`. Now iterates over every configured key and
every model by default. New flags: `--key 1|2`, `--model <name>`.

### Discovery: original two keys were from the same Groq account

Symptom: key2 showed 0 calls on `/llm-usage` but was still getting 429s.

**Diagnosis** — Built a live differential test (`_test_key_sharing.py`, since deleted):
call Groq's rate-limit header endpoint for both keys, burn 5 requests through key1,
re-check both. On the original keys, **both** counters dropped by 7 → same account,
shared quota. "Key rotation" was giving us nothing.

**Fix** — User regenerated both keys from **separate** Groq accounts. Re-ran the
differential test: key1 dropped 6, key2 only its baseline 1 → confirmed isolated.
New keys now in `.env` (gitignored, not committed).

### Debug pipeline lesson

User flagged that I was troubleshooting rak/asu_kerr with ad-hoc Python one-liners
instead of using `debug_fetch.py`, `debug_clean.py`, `debug_chunk.py`, `debug_llm.py`,
`debug_pipeline.py` — which exist **specifically** for this. Going forward, the
debug pipeline is the first tool for any scraper/pagination/chunking investigation.
Start with `python3 debug_chunk.py <key>` and `python3 debug_pipeline.py <key>`.

### Key takeaways for future sessions

- **SITES tuple is 8 elements** now: `(name, url, use_selenium, wait, max_pages, note, color, pagination_config)`. Always use `entry[:6]` slicing or full 8-element unpack; any 7-element unpack is stale.
- **`TRIM_PATTERNS` values can be str, (str, str), or None.** Tuple form is for sites with boilerplate both before AND after events.
- **`ask_llm()` only extracts `next_page_url` from the last chunk.** Keep total cleaned text small enough that pagination markers land in the final chunk — this is why tail trims matter.
- **The debug pipeline tools exist. Use them first.**

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
