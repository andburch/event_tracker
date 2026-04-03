# Phoenix Valley Events Recommender

A personal event aggregator for the Phoenix Valley, AZ area. Scrapes events from city government sites, local venues, and arts centers using LLM-based extraction, then uses AI to rank them by your personal preferences.

## Key Features

- **Configuration-Driven**: Add new event sources by editing config only - no code changes needed
- **LLM-Based Extraction**: Uses Groq API to extract events from any website (no brittle CSS selectors)
- **5 Pagination Types**: Handles any pagination pattern automatically
- **23 Event Sources**: Venues, government sites, libraries, museums across Phoenix Valley
- **Preference Learning**: Learns your interests and ranks events by relevance
- **Web Interface**: Browse, filter, and manage your event short list
- **Health Dashboard**: Monitor scraper success rates

## Architecture

```
sources.py → pagination_engine.py → llm_scrape_core.py → Groq API
(config)     (5 handlers)           (fetch/clean/ask)     (LLM)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation and flow charts.

## Requirements

- Python 3.10+
- Google Chrome or Chromium (for Selenium-based scrapers)
- A Groq API key (free tier available — used for LLM-based scraping and preference-based ranking)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your Groq API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```
   Get a free API key at https://console.groq.com

3. Run the scrapers to populate the database:
   ```bash
   python llm_scraper.py
   ```
   This takes 10–20 minutes depending on how many sites you scrape. You can run specific sites only:
   ```bash
   python llm_scraper.py fibber yuccatap
   ```
   Or see all available sites:
   ```bash
   python llm_scraper.py list
   ```

4. (Optional) Run batch scoring to rank events by your preferences:
   ```bash
   python score_events.py
   ```
   Note: You need to set up your taste profile first (see Preference Learning below).

5. Start the web server:
   ```bash
   python server/app.py
   ```

6. Open http://localhost:5000

## Web Interface

Three main views are available:

- **List view** (`/`) — events sorted by date or relevance score, filterable by source and date range
- **Calendar view** (`/calendar`) — monthly grid with color-coded events by source, click any event for details
- **Profile page** (`/profile`) — set your taste preferences and view feedback history
- **Health dashboard** (`/health`) — scraper run history and event counts per source

## Event Sources

The scraper uses LLM-based extraction to pull events from these sources:

| Source | Type | Key |
|---|---|---|
| Fibber Magee's Pub | Music venue | `fibber` |
| Dirty Drummer | Music venue | `dirtydrummer` |
| Yucca Tap Room | Music venue | `yuccatap` |
| Raising Arizona Kids | Family | `rak` |
| City of Chandler | Government | `chandler` |
| City of Scottsdale | Government | `scottsdale` |
| City of Gilbert | Government | `gilbert` |
| City of Phoenix | Government | `phoenix` |
| City of Mesa | Government | `mesa` |
| Chandler Public Library | Library | `chandler_lib` |
| Tempe Public Library | Library | `tempe_lib` |
| AZ Museum of Natural History | Museum | `azmnh` |
| Chandler Center for the Arts | Arts | `chandler_center` |
| Mesa Arts Center | Arts | `mesa_arts` |
| Scottsdale Arts | Arts | `scottsdale_arts` |
| ASU Kerr Cultural Center | Arts | `asu_kerr` |
| Tempe Center for the Arts | Arts | `tca` |
| Downtown Tempe | Community | `downtown_tempe` |
| Desert Botanical Garden | Garden | `dbg` |
| OdySea Aquarium | Aquarium | `odysea` |
| Hale Theatre Arizona | Theatre | `hale_theatre` |
| Arizona Mushroom Society | Community | `az_mushroom` |
| Backcountry Hunters & Anglers AZ | Outdoor | `backcountry_hunters` |

## Preference Learning

1. Go to `/profile` and write a short description of your interests in the "About Me" section
2. Browse events and click 👍 or 👎 on any event to record feedback
3. After 10 feedbacks, the AI will automatically generate a preference summary
4. Run `python score_events.py` to score all events based on your profile
5. Sort by "Relevance Score" on the main page to see your personalized recommendations

If no Groq key is configured, all events default to a 0.5 score and sorting by date is used instead.

## Running Scrapers on a Schedule

The scraper supports being called from any scheduler (Task Scheduler on Windows, cron on Linux/Mac):

```bash
# Run all scrapers
python llm_scraper.py

# Run specific scrapers
python llm_scraper.py phoenix mesa chandler

# Append to existing events (don't purge database first)
python llm_scraper.py --no-purge
```

Example cron entry (daily at 6 AM):
```
0 6 * * * cd /path/to/event_tracker && python llm_scraper.py
```

Example Windows Task Scheduler command:
```
C:\Python310\python.exe C:\path\to\event_tracker\llm_scraper.py
```

## Testing Individual Scrapers

Use the test harness to debug scraping issues without writing to the database:

```bash
# Test one site
python _test_llm_scrape.py fibber

# Test multiple sites
python _test_llm_scrape.py phoenix mesa

# Test with raw HTML dump (for debugging)
python _test_llm_scrape.py chandler --dump

# List all available sites
python _test_llm_scrape.py list
```

## Porting to Another Machine

1. Copy the entire project folder (including `events.db` if you want existing data)
2. Install Chrome/Chromium on the new machine
3. Run `pip install -r requirements.txt`
4. Recreate `.env` (it's gitignored)
5. Start the server

ChromeDriver is bundled as `chromedriver.exe` in the project root. If it doesn't match your Chrome version, download the correct version from https://chromedriver.chromium.org/

## Corporate Firewall Notes

- SSL verification is disabled on all HTTP requests and the Groq client
- Set `HTTP_PROXY` / `HTTPS_PROXY` in `.env` if needed
- Some sites (Gilbert, Scottsdale Arts, TCA) use Akamai bot detection and may occasionally fail

## How the LLM Scraper Works

Traditional web scrapers use CSS selectors that break whenever a site redesigns. This project uses a different approach:

1. Fetch the page HTML (via requests or Selenium for JS-heavy sites)
2. Strip HTML down to clean readable text
3. Send that text to Groq's LLM with a structured JSON schema
4. The LLM extracts events AND finds the next page URL
5. Follow pagination until no more pages

Because the LLM reads plain text rather than HTML structure, it works on virtually any events page regardless of how it's built.

## Adding a New Event Source

1. Open `sources.py`
2. Add an entry to the `SITES` dictionary:
   ```python
   'mysite': (
       'My Site Display Name',
       'https://example.com/events',
       True,  # use_selenium (True for JS-heavy sites, False for static HTML)
       5,     # wait_secs (seconds to wait after page load)
       5,     # max_pages (pagination depth limit)
       '',    # note (optional quirks/notes)
       ('#fff7ed', '#c2410c', '#7c2d12'),  # color (bg, border, text) for calendar
   ),
   ```
3. Test it: `python _test_llm_scrape.py mysite`
4. Run it: `python llm_scraper.py mysite`

That's it! No custom parsing code needed.

## Adding a New Event Source

Adding a new scraper takes 5-10 minutes and requires editing only ONE file:

1. Open `sources.py`
2. Add entry to `SITES` dict:
   ```python
   'mysite': (
       'My Site Name',
       'https://mysite.com/events',
       True,  # Use Selenium?
       5,     # Wait seconds
       5,     # Max pages
       '',    # Notes
       ('#fff', '#000', '#333'),  # Colors
       None,  # Pagination config (or dict)
   ),
   ```
3. Test: `python llm_scraper.py mysite`

See [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md) for detailed guide with examples.

## Project Structure

```
sources.py              # SINGLE SOURCE OF TRUTH - all site configs
pagination_engine.py    # Configuration-driven pagination (5 types)
llm_scrape_core.py      # Low-level scraping utilities
llm_scraper.py          # Production entry point + DB persistence
score_events.py         # Batch event scoring
server/app.py           # Flask web interface
database/models.py      # SQLAlchemy ORM models
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete documentation.

```
/
├── llm_scrape_core.py  # Core LLM extraction logic
├── llm_scraper.py      # Production scraper (saves to DB)
├── score_events.py     # Batch scoring script
├── _test_llm_scrape.py # Test harness (no DB writes)
├── sources.py          # Site definitions and display config
├── config.py           # Application configuration
├── database/
│   └── models.py       # SQLAlchemy ORM models
├── recommender/
│   └── llm_filter.py   # Event scoring and preference learning
├── server/
│   ├── app.py          # Flask web application
│   └── templates/      # HTML templates
├── events.db           # SQLite database (generated)
└── .env                # Environment variables (not in git)
```

## Troubleshooting

**Scraper returns 0 events:**
- Run with `--dump` flag to see the raw text: `python _test_llm_scrape.py sitename --dump`
- Check if the site is blocking headless browsers (try increasing `wait_secs` in `sources.py`)
- Check Groq API quota: `python check_groq_quota.py`

**"Access Denied" or bot detection:**
- Some sites (Gilbert, Scottsdale Arts) use Akamai bot detection
- The scraper uses user-agent spoofing and fresh sessions to mitigate this
- If it persists, try running at different times of day

**Scoring not working:**
- Make sure `GROQ_API_KEY` is set in `.env`
- Set up your taste profile at `/profile`
- Run `python score_events.py` after scraping

**Database locked errors:**
- SQLite doesn't handle concurrent writes well
- Don't run multiple scrapers simultaneously
- Don't run the web server and scraper at the same time

**Rate limit errors (429):**
- Groq free tier has daily token limits (100k tokens/day for llama-3.3-70b-versatile)
- Check quota: `python check_groq_quota.py`
- Wait for limits to reset or switch models in `config.py`
- Use `wait_and_scrape.py` to schedule scraping after rate limit resets

## License

This is a personal project. Use at your own risk.
