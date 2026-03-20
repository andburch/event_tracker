# Phoenix Valley Events Recommender

A personal event aggregator for the Phoenix Valley, AZ area. Scrapes events from city government sites, local venues, and arts centers, then uses an LLM to rank them by your personal preferences.

## Requirements

- Python 3.10+
- Google Chrome or Chromium (for Selenium-based scrapers)
- An OpenAI API key (optional — used for preference-based ranking)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your key:
   ```bash
   cp .env.example .env
   ```
   ```
   OPENAI_API_KEY=your_key_here
   ```

3. Run the scrapers to populate the database:
   ```bash
   python scraper_runner.py
   ```
   This takes 10–20 minutes. You can run a single scraper to test:
   ```bash
   python scraper_runner.py mesa_gov
   ```

4. Start the web server:
   ```bash
   python server/app.py
   ```

5. Open http://localhost:5000

## Web Interface

Two views are available:

- **List view** (`/`) — events sorted by date or relevance score, filterable by source and date range
- **Calendar view** (`/calendar`) — monthly grid with color-coded events by source, click any event for details
- **Health dashboard** (`/health`) — scraper run history and event counts per source

## Event Sources

| Source | Type |
|---|---|
| City of Phoenix | Government |
| City of Tempe | Government |
| City of Mesa | Government |
| City of Chandler | Government |
| City of Scottsdale | Government |
| City of Gilbert | Government |
| Chandler Public Library | Library |
| Tempe Public Library | Library |
| Chandler Center for the Arts | Arts |
| Mesa Arts Center | Arts |
| Scottsdale Arts | Arts |
| Tempe Center for the Arts | Arts |
| ASU Kerr Cultural Center | Arts |
| AZ Museum of Natural History | Museum |
| Fibber Magee's Pub | Music venue |
| Yucca Tap Room | Music venue |
| Dirty Drummer | Music venue |
| Raising Arizona Kids | Family |

## Preference Learning

Click 👍 or 👎 on any event to record feedback. Once you have a few feedbacks, the LLM will start scoring events by how well they match your taste. Events are ranked by this score when you sort by "Relevance Score."

If no OpenAI key is configured, all events default to a 0.5 score and sorting by date is used instead.

## Running Scrapers on a Schedule

The scraper runner supports being called from any scheduler (Task Scheduler on Windows, cron on Linux/Mac):

```bash
# Run all scrapers
python scraper_runner.py

# Run a specific scraper
python scraper_runner.py fibbermagees
```

Available scraper names: `phoenix_gov`, `tempe_gov`, `mesa_gov`, `chandler_gov`, `scottsdale_gov`, `gilbert_gov`, `chandler_library`, `tempe_library`, `chandler_center`, `mesa_arts`, `scottsdale_arts`, `tca`, `asu_kerr`, `azmnh`, `fibbermagees`, `yuccatap`, `dirtydrummer`, `raisingarizonakids`

## Porting to Another Machine

1. Copy the entire project folder (including `events.db` if you want existing data)
2. Install Chrome/Chromium on the new machine
3. Run `pip install -r requirements.txt`
4. Recreate `.env` (it's gitignored)
5. Start the server

ChromeDriver is auto-downloaded by `webdriver-manager` if the bundled `chromedriver.exe` doesn't match your Chrome version.

## Corporate Firewall Notes

- SSL verification is disabled on all HTTP requests and the OpenAI client
- Set `HTTP_PROXY` / `HTTPS_PROXY` in `.env` if needed
- Some scrapers (Desert Botanical Garden, OdySea) may be blocked — they're disabled by default and can be re-enabled in `scrapers/__init__.py`

## Adding a New Scraper

1. Create `scrapers/{venue}_scraper.py` inheriting from `BaseScraper`
2. Implement `scrape()` returning a list of normalized event dicts
3. Use `self.get_page(url)` for static sites or `self.get_page_selenium(url)` for JS-heavy ones
4. Add to the `SCRAPERS` list in `scrapers/__init__.py`

Standard event dict keys: `title`, `description`, `venue`, `date`, `url`, `category`
