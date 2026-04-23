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

# Optional second Groq API key. When set, the rate limiter switches between
# keys on 429 errors to maximize throughput during bulk scraping.
GROQ_API_KEY_2 = os.getenv('GROQ_API_KEY_2', '')

# When True, fall back to Ollama if both Groq keys are daily-exhausted.
# Requires OLLAMA_URL to be reachable.
GROQ_FALLBACK_TO_OLLAMA = os.getenv('GROQ_FALLBACK_TO_OLLAMA', 'false').lower() == 'true'

# ---------------------------------------------------------------------------
# Proxy settings (optional)
# ---------------------------------------------------------------------------

# Set these in .env if a proxy is required.
# Example: HTTP_PROXY=http://proxy.example.com:8080
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
# LLM Provider
# ---------------------------------------------------------------------------

# Which provider to use by default: 'groq' or 'ollama'
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'groq')

# Ollama settings (used when LLM_PROVIDER='ollama' or provider='ollama' per-call)
OLLAMA_URL            = os.environ.get('OLLAMA_URL', 'http://ollama:11434')
OLLAMA_TIMEOUT        = int(os.environ.get('OLLAMA_TIMEOUT', '300'))  # CPU inference can be slow
OLLAMA_SCRAPING_MODEL = os.environ.get('OLLAMA_SCRAPING_MODEL', 'gemma3:4b')
OLLAMA_SCORING_MODEL  = os.environ.get('OLLAMA_SCORING_MODEL',  'gemma3:4b')
OLLAMA_MAX_TOKENS     = int(os.environ.get('OLLAMA_MAX_TOKENS', '16384'))  # Ollama default num_predict is ~2048, too small for event JSON

# ---------------------------------------------------------------------------
# LLM Model Configuration
# ---------------------------------------------------------------------------

# Ordered list of models to use for event extraction during scraping.
# The rate limiter tries each (key, model) combination in order:
# all keys with model[0] first, then all keys with model[1], etc.
# Add more models here to expand the combinatorial quota space.
# llama-3.3-70b-versatile: Better output quality, 12k TPM, 100k TPD per key
# llama-3.1-8b-instant: Faster, lower quality, 6k TPM, 500k TPD per key
LLM_SCRAPING_MODELS = ['llama-3.3-70b-versatile', 'meta-llama/llama-4-scout-17b-16e-instruct']

# Ordered list of models to use for event scoring/recommendation.
LLM_SCORING_MODELS = ['llama-3.3-70b-versatile']


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
