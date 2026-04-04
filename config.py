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
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///events.db')

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
# LLM Model Configuration
# ---------------------------------------------------------------------------

# Model used for event extraction during scraping
# llama-3.3-70b-versatile: Better output quality, higher TPM (12k vs 6k),
#   but lower RPD (1k vs 14.4k). Used for all scraping.
# llama-3.1-8b-instant: Faster, higher daily limit (14.4k RPD), lower quality
LLM_SCRAPING_MODEL = 'llama-3.3-70b-versatile'  # Back to better model

# Model used for event scoring/recommendation
# Can be the same or different from scraping model
LLM_SCORING_MODEL = 'llama-3.3-70b-versatile'

# ---------------------------------------------------------------------------
# LLM Scraping Configuration
# ---------------------------------------------------------------------------

# Text chunking parameters for large pages that exceed LLM context limits
LLM_CHUNK_SIZE = 6_000      # Characters per chunk when splitting large pages
LLM_CHUNK_OVERLAP = 300     # Character overlap between chunks to preserve context
LLM_CHUNK_DELAY = 10        # Seconds to wait between chunk requests (rate limiting)

# Retry configuration for LLM API calls
LLM_MAX_RETRIES = 3         # Maximum retry attempts for failed LLM requests
LLM_RETRY_BASE_DELAY = 20   # Base delay in seconds (multiplied by attempt number)

# ---------------------------------------------------------------------------
# Recommendation Engine Configuration
# ---------------------------------------------------------------------------

# Batch scoring parameters
SUMMARY_THRESHOLD = 10      # Minimum feedback items before generating preference summary
SCORING_CHUNK_SIZE = 40     # Events per batch when scoring
SCORING_CHUNK_DELAY = 12    # Seconds between scoring batches (rate limiting)
SCORING_MAX_RETRIES = 3     # Maximum retry attempts for scoring requests
SCORING_RETRY_BASE_DELAY = 5  # Base delay in seconds for scoring retries
