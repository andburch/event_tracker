# Phoenix Valley Events Recommender

A personal event aggregator for the Phoenix Valley, AZ area. Scrapes events from city government sites, local venues, and arts centers using LLM-based extraction, then ranks them by your personal taste with another LLM pass.

## Key Features

- **Configuration-driven scrapers** — add new event sources by editing one file, no code changes
- **LLM-based extraction** — Groq API (primary) or local Ollama (fallback) pulls events from any events page, no brittle CSS selectors
- **5 pagination types** — covers nearly every real-world events page
- **32 event sources** across Phoenix Valley — venues, cities, libraries, museums, arts centers, hobby clubs
- **Preference learning** — thumbs-up/thumbs-down feedback feeds a rolling taste profile
- **Containerized** — `web` / `scraper` / `ollama` split so scraping crashes can't take down the UI
- **Health dashboard** — per-source success rates, recent runs, and LLM token-budget tracking

## Architecture

```
sources.py ──▶ scrape/pagination.py ──▶ scrape/core.py ──▶ Groq (or Ollama)
 (config)        (5 handlers)            (fetch/clean/ask)     (LLM)
```

```
host :5000
   │
   ▼
 ┌──────┐      events_data volume (SQLite, WAL)     ┌──────────────┐
 │ web  │◀──────────────────────┬──────────────────▶│   scraper    │
 └──────┘                       │                   │ (ephemeral)  │
                                │                   └──────┬───────┘
                                │                          │
                                ▼                          ▼
                         (persists scores,            (writes events
                          pins, feedback)             and run history)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full documentation.

## Requirements

- Docker + Docker Compose (recommended), **or** Python 3.10+ with Chromium + ChromeDriver
- A Groq API key — free tier is plenty. Get one at https://console.groq.com

## Setup (Docker)

```bash
# 1. Put your key in .env
cp .env.example .env
# edit .env and set GROQ_API_KEY=...

# 2. Build and start the web UI
docker compose up -d --build
docker compose logs -f web

# 3. First scrape (ephemeral scraper container)
docker compose run --rm scraper python llm_scraper.py

# 4. Score the scraped events against your taste profile
docker compose run --rm scraper python score_events.py

# 5. Open the UI
open http://localhost:5000
```

The SQLite DB lives on a named volume (`events_data`), so it survives `docker compose down`. Scrape artifacts land in `./debug_artifacts/<source>/` on the host — inspect them any time.

### Optional: local Ollama fallback

Groq handles everything by default. If you want a local fallback for when both Groq keys hit the daily limit:

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull gemma3:4b    # one-time
# then set GROQ_FALLBACK_TO_OLLAMA=true in .env and restart web
```

## Setup (bare Python)

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit and set GROQ_API_KEY
python llm_scraper.py       # scrape
python score_events.py      # score
python server/app.py        # serve at http://localhost:5000
```

Scoring is **manual** in both setups — `llm_scraper.py` doesn't trigger it, and editing your taste profile doesn't retroactively re-score. Run `score_events.py` yourself (use `--all` after a profile change to re-score everything).

## Web Interface

- `/` — event list, sortable by date or relevance, filterable by source
- `/calendar` — monthly grid with color-coded events per source
- `/profile` — taste profile + feedback history
- `/health` — per-source scraper run history
- `/llm-usage` — rolling 24h Groq token and request usage (authoritative for daily-limit watching)

## Event Sources

31 sources covering music venues, cities, libraries, museums, arts centers, and assorted hobby clubs around Phoenix:

`fibber`, `dirtydrummer`, `yuccatap`, `rak`, `chandler`, `scottsdale`, `gilbert`, `phoenix`, `mesa`, `chandler_lib`, `tempe_lib`, `azmnh`, `chandler_center`, `mesa_arts`, `scottsdale_arts`, `asu_kerr`, `tca`, `downtown_tempe`, `dbg`, `odysea`, `az_mushroom`, `az_worm_farm`, `backcountry_hunters`, `changing_hands`, `farm_south_mtn`, `summerwinds`, `valley_bar`, `sleepy_whale`, `sweet_basil`, `evac`, `az_flycasters`

Run `python llm_scraper.py list` (or `docker compose run --rm scraper python llm_scraper.py list`) for the full table with URLs and pagination flags.

## Preference Learning

1. Write a short "About Me" blurb on `/profile`
2. Browse events and thumbs-up / thumbs-down anything you care about
3. After 10 feedbacks, the rolling preference summary is regenerated (summary only — doesn't re-score)
4. Run `python score_events.py --all` whenever you want existing events re-scored against the updated profile

Sort by "Relevance Score" on the main page to see your personalized ranking. If no Groq key is configured, events default to 0.5 and the UI falls back to date sorting.

## Adding a New Event Source

1. Open `sources.py`
2. Add an entry to `SITES`:
   ```python
   'mysite': (
       'My Site Display Name',
       'https://mysite.com/events',
       True,                                  # use Selenium?
       5,                                     # wait seconds after load
       5,                                     # max pages
       '',                                    # note
       ('#fff7ed', '#c2410c', '#7c2d12'),     # calendar colors (bg, border, text)
       None,                                  # pagination config (or dict)
   ),
   ```
3. Add a `TRIM_PATTERNS` entry in the same file to strip site boilerplate
4. Test: `python tools/test_scraper.py mysite` (or `docker compose run --rm scraper ...`)

Full walkthrough with trim-pattern research in [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md). No custom Python for typical sites.

## Running on a Schedule

```bash
# Host cron (bare Python)
0 6 * * * cd /path/to/event_tracker && python llm_scraper.py

# Host cron (Docker)
0 6 * * * cd /path/to/event_tracker && docker compose run --rm scraper python llm_scraper.py
```

Append without purging: `python llm_scraper.py --no-purge`.

## Project Structure

```
sources.py              # SINGLE SOURCE OF TRUTH: SITES + TRIM_PATTERNS
scrape/pagination.py    # 5 pagination handlers
scrape/core.py          # fetch / clean / ask-the-LLM utilities
scrape/artifacts.py     # debug_artifacts/ writer
llm_scraper.py          # production entry point + DB persistence
score_events.py         # batch event scoring
llm/provider.py         # unified Groq / Ollama call path
llm/rate_limiter.py     # multi-key TPM/TPD-aware rate limiting
debug/                  # step-by-step pipeline tools (fetch/clean/chunk/llm/pipeline/source)
tools/                  # test_scraper.py, tools/check_groq_quota.py
database/models.py      # SQLAlchemy models + WAL bootstrap
server/app.py           # Flask UI
docker-compose.yml      # web / scraper / ollama
debug_artifacts/        # live scrape artifacts (bind-mounted in Docker)
```

## Troubleshooting

**Scraper returns 0 events** — run `tools/test_scraper.py <key> --dump` to see the cleaned text the LLM saw. Try raising `wait` in `sources.py` if JS-heavy.

**Akamai / bot detection** — Gilbert and Scottsdale Arts use Akamai; occasional failure is probabilistic. Longer `wait_secs` and fresh Selenium sessions help.

**Rate limit errors (429)** — Groq free tier has per-minute (TPM) and per-day (TPD) token limits. Per-minute info is in `tools/check_groq_quota.py`, but daily token usage is only visible on `/llm-usage` (Groq doesn't expose daily tokens in API headers). Add a second Groq key as `GROQ_API_KEY_2` in `.env` to double the combined quota.

**Scoring seems frozen** — scoring is manual. After scraping, run `score_events.py`. After changing your profile, run `score_events.py --all`.

**Database locked** — only happens outside the containerized setup. The Docker setup enables SQLite WAL, which lets the web and scraper containers read/write concurrently without conflict.

## How the LLM Scraper Works

Traditional scrapers use CSS selectors that break every time a site redesigns. This one:

1. Fetches the page (requests or Selenium depending on JS-ness)
2. Strips HTML to clean text and trims site-specific boilerplate
3. Sends the text to the LLM with a JSON schema asking for events + next-page URL
4. Follows pagination until no more pages or `max_pages` hits

Because the LLM reads plain text, it survives redesigns as long as the events are still visible on the page.

## License

Personal project. Use at your own risk.
