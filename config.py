"""
config.py — Application-wide configuration.

All secrets are loaded from the .env file via python-dotenv.
Non-secret settings (coordinates, intervals, DB path) are hardcoded here
since they don't vary between environments.
"""
import os
from dotenv import load_dotenv

# Load .env into os.environ before reading any values
load_dotenv()

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

# Groq API key — required for LLM scoring and preference summarization.
# Get one free at https://console.groq.com
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# ---------------------------------------------------------------------------
# Proxy settings (optional)
# ---------------------------------------------------------------------------

# Set these in .env if you're behind a corporate firewall that requires a proxy.
# Example: HTTP_PROXY=http://proxy.company.com:8080
HTTP_PROXY  = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# SQLite file stored in the project root. Path is relative to wherever the
# process is launched from (typically the repo root).
DATABASE_URL = 'sqlite:///events.db'

# ---------------------------------------------------------------------------
# Phoenix Valley geographic bounds
# ---------------------------------------------------------------------------

# Center-point coordinates used for any distance-based filtering.
# Currently informational — scrapers target specific venues rather than
# doing radius searches, but these are available if needed.
PHOENIX_LAT = 33.4484
PHOENIX_LON = -112.0740
SEARCH_RADIUS_MILES = 30  # Maximum distance from center to consider "local"

# ---------------------------------------------------------------------------
# Scraping schedule
# ---------------------------------------------------------------------------

# How often scraper_runner.py should be re-run when scheduled automatically.
# Not enforced by the app itself — use cron, Task Scheduler, or a similar
# external scheduler to call `python scraper_runner.py` on this interval.
SCRAPE_INTERVAL_HOURS = 6
