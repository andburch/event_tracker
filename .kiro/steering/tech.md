# Technology Stack

## Core Technologies

- **Language**: Python 3.x
- **Web Framework**: Flask 3.0+
- **Database**: SQLite with SQLAlchemy 2.0+ ORM
- **Web Scraping**: Selenium 4.15+ with BeautifulSoup4
- **LLM Integration**: Groq API
- **Environment Management**: python-dotenv

## Key Libraries

- `selenium` - Browser automation for JavaScript-heavy sites
- `webdriver-manager` - Automatic ChromeDriver management
- `beautifulsoup4` - HTML parsing
- `sqlalchemy` - Database ORM
- `flask` - Web server
- `groq` - LLM-based event scoring
- `requests` - HTTP client (fallback for simple sites)
- `schedule` - Periodic scraper execution

## Environment Configuration

Required environment variables in `.env`:
- `GROQ_API_KEY` - Groq API key for LLM recommendations
- `HTTP_PROXY` (optional) - Corporate firewall proxy
- `HTTPS_PROXY` (optional) - Corporate firewall proxy

## Common Commands

### Setup
```bash
pip install -r requirements.txt
```

### Run Scrapers
```bash
python llm_scraper.py              # scrape all sites
python llm_scraper.py fibber mesa  # scrape specific sites
python llm_scraper.py list         # show all available sites
python llm_scraper.py --no-purge   # append without purging DB
```

### Run Batch Scoring
```bash
python score_events.py
```

### Start Web Server
```bash
python server/app.py
```
Server runs on http://localhost:5000

### Test Individual Scrapers
```bash
python _test_llm_scrape.py <site_key>     # test one site
python _test_llm_scrape.py <key> --dump   # test with raw HTML dump
python _test_llm_scrape.py list           # show all sites
```

### Database Inspection
Visit http://localhost:5000/health for the scraper health dashboard.

## Build System

No build step required - pure Python application. Dependencies managed via `requirements.txt`.

## Deployment Notes

- Requires Chrome/Chromium installed for Selenium
- ChromeDriver auto-downloaded by webdriver-manager or can be placed locally
- SSL verification disabled for corporate firewall compatibility
- Headless Chrome used for scraping (no GUI required)
