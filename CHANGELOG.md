# Changelog

## 2026-11-26 — Status page cleanup
- `/health`: sources marked `PAUSED` in `sources.py` now appear under **Paused Scrapers** with their reason, instead of showing their last (pre-fix) error forever.
- Deleted 2,240 stale `model_not_found` (retired llama) entries from `groq_rate_limit_events`, all from before the 2026-11-24 fix, so `/llm-usage` "LLM Errors" shows only real, current problems. DB backup taken first: `/data/events.db.bak-20261126` in the `events_data` volume.
- Ran a catch-up scrape of the 13 active sources whose last run was still the pre-fix error.

## 2026-11-24 — Recovery after 3-month silent outage

**What was wrong:** no new events since 2026-08-17. Groq retired both configured models (404 `model_not_found`). Multi-chunk pages reported "success, 0 events", scripts exited 0, and the health check only tested that port 5000 answered, so nothing flagged it.

| # | Fix | Files |
|---|-----|-------|
| 1 | Models → `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` (scoring: the two gpt-oss) | `config.py` |
| 2 | 404 on a model → skip it for the run and fall back to the next model | `llm/provider.py`, `llm/rate_limiter.py` |
| 3 | A page where every chunk failed now raises (run recorded as failed). Partial failures are still salvaged | `scrape/core.py` |
| 3b | `e.body` parsing fixed. Salvaging partial JSON never worked before. Empty `json_validate_failed` responses (gpt-oss quirk) are now retried | `scrape/core.py` |
| 4 | Scraper exits 1 on systemic failure; scorer exits 1 if nothing scored. systemd `OnFailure=` sends an ntfy push alert | `llm_scraper.py`, `score_events.py`, `recommender/llm_filter.py`, `scripts/notify.sh`, `scripts/systemd/*` |
| 5 | `~/check-services.sh` (outside repo) gained: events freshness (≤3 days), disk <90%, Syncthing folder errors | — |
| 6 | Containers run `TZ=America/Phoenix`, so tonight's events no longer disappear after 5pm and scraper date math matches | `docker-compose.yml` |
| 7 | TLS verification re-enabled for Groq API calls (was `verify=False`) | `llm/provider.py`, `tools/check_groq_quota.py` |
| 8 | `/score` keeps a handle on its child (reaped, no zombies) and refuses to start a second run while one is going | `server/app.py`, `server/templates/index.html` |
| 9 | Live artifacts now write to top-level `debug_artifacts/` (where the debug scripts read), not `scrape/debug_artifacts/` | `scrape/artifacts.py` |

**Verified:** test scrapes of fibber, dirtydrummer and tempe_lib all worked. A real fibber scrape added 7 events, and scoring scored 7/7. The 404 fallback was tested with the retired llama model listed first. A test alert was received on ntfy. `check-services.sh` flagged the 99-day gap before the fix and passed after.

**Source investigation (same day):**
- `scottsdale`: **fixed.** The city moved its calendar into a BeWith iframe (`main.withapps.io/event-grid`); the old Localist page has had no events since June. The source now points at the iframe's `view=list` URL, which lists every upcoming event (~550 through March, ~150K chars) on one page. Single page, new trim pattern. Heavy on tokens (~26 chunks), so it gets its first full run in Tuesday's scheduled scrape.
- `farm_south_mtn`: **was never broken.** It returned events weekly until the Aug model outage (fewer over summer); a test scrape on 2026-11-24 found 12 events.
- `downtown_tempe`: **blocked by IP.** Since ~Jul 10, every URL (even `robots.txt`) returns 403 from their AWS load balancer to this server, with or without a browser. Likely a block on cloud/datacenter IPs. Can't be fixed with config. Options: fetch through a home connection (Tailscale exit node), or drop the source.
- `changing_hands`: **blocked by Cloudflare.** Since ~Jul 3, Cloudflare returns a managed challenge (`cf-mitigated: challenge`, 403) to this server. Headless Chrome stays on "Just a moment…" even after 40s. The site also moved from `www.` to the bare domain. Options: same as downtown_tempe, or a stealthier browser (new code/dependency, against the "config only" rule).

**Known still-broken / not done:**
- Sources `downtown_tempe` and `changing_hands` are **paused, not deleted**. Their config stays in `sources.py`, but they're out of the Friday rotation in `scripts/weekly_scrape.sh`. To re-enable, add them back there.
- ~~debug/llm.py and debug/pipeline.py crashed on start (stale `_MODELS` import)~~ fixed 2026-11-24.
- ~~Stale scrape/debug_artifacts/~~ deleted 2026-11-24.
- ~1 in 8 chunks on big pages still fails after retries with gpt-oss.
- 3-month backfill (all sources) not yet run. Mind the Groq daily token budget (`/llm-usage`).
