# Project Structure

## Active Files

**All scraping is done exclusively through:**
- `sources.py` — SINGLE SOURCE OF TRUTH: site definitions with pagination configs
- `pagination_engine.py` — configuration-driven pagination handlers
- `llm_scrape_core.py` — fetch + LLM extraction logic (no site-specific code)
- `llm_scraper.py` — production entry point (DB persistence, CLI)
- `score_events.py` — run LLM batch scoring separately after scraping
- `_test_llm_scrape.py` — test harness for individual sites

**To add a new source:** Add ONE entry to `sources.py` SITES dict. See `HOW_TO_ADD_SCRAPERS.md`.

---

## Directory Organization

```
/
├── sources.py          # ✅ ACTIVE: SINGLE SOURCE OF TRUTH - all site configs
├── pagination_engine.py # ✅ ACTIVE: configuration-driven pagination
├── llm_scrape_core.py  # ✅ ACTIVE: fetch + LLM extraction (no site-specific code)
├── llm_scraper.py      # ✅ ACTIVE: production scraper entry point
├── _test_llm_scrape.py # ✅ ACTIVE: test harness (python _test_llm_scrape.py <key>)
├── score_events.py     # ✅ ACTIVE: LLM batch scoring
├── HOW_TO_ADD_SCRAPERS.md # ✅ GUIDE: how to add new event sources
├── scrapers/           # ❌ DEPRECATED — do not use or modify
├── scraper_runner.py   # ❌ DEPRECATED — do not use
├── database/           # Database models and configuration
│   ├── models.py             # SQLAlchemy models (Event, UserProfile, etc.)
│   └── __init__.py
├── recommender/        # LLM-based recommendation engine
│   ├── llm_filter.py         # Event scoring + preference summary logic
│   └── __init__.py
├── server/             # Flask web application
│   ├── app.py                # Flask routes and API endpoints
│   └── templates/
│       ├── index.html        # Main event list view
│       ├── calendar.html     # Monthly calendar view
│       ├── profile.html      # User preferences page
│       └── health.html       # Scraper health dashboard
├── config.py           # Application configuration
├── check_groq_quota.py # Utility: check remaining Groq API quota
├── events.db           # SQLite database (generated)
├── requirements.txt    # Python dependencies
└── .env                # Environment variables (not in git)
```

## Key Architectural Patterns

### Scraper Architecture (Configuration-Driven)

All scraping uses a configuration-driven pagination engine:
- `sources.py` contains the `SITES` dict: all site configs with pagination settings
- `pagination_engine.py` interprets configs and executes appropriate pagination strategy
- `llm_scrape_core.py` provides fetch/LLM functions (no site-specific code)
- `llm_scraper.py` handles DB persistence and CLI
- **To add a new source:** Add ONE entry to `SITES` in `sources.py` (see `HOW_TO_ADD_SCRAPERS.md`)

Supported pagination types:
1. `llm` - LLM extracts next_page_url (default, works for most sites)
2. `multi_month` - Generate URLs for N consecutive months
3. `url_param` - Increment URL parameter (?page=N, pageindex=N, etc.)
4. `js_button` - Click JavaScript pagination buttons
5. `calendar_grid` - Month-view calendar with date injection

### Database Layer

- SQLAlchemy ORM with declarative base
- Models: `Event`, `FeedbackHistory`, `UserProfile`, `PreferenceProfileHistory`, `ScraperRun`
- Session management via `Session()` factory
- `Event.pinned` boolean — user's short list of events they plan to attend
- `Event.score` float (0.0–1.0) — LLM relevance score, NULL until batch scoring runs

### Web Server

- Flask application with template rendering
- Routes: `/` (list), `/calendar`, `/profile`, `/profile/summary`, `/health`, `/feedback`, `/pin`
- `POST /pin` toggles `Event.pinned` for the short list feature
- LLM scoring reads cached `Event.score` — no live API calls on page load

## Naming Conventions

- Database models: PascalCase (Event, UserProfile)
- Functions/methods: snake_case
- Source keys in SITES: lowercase, no spaces (e.g., `yuccatap`, `fibber`)

## Configuration Files

- `config.py` - Application settings (database, API keys, coordinates)
- `.env` - Secrets and environment-specific values (`GROQ_API_KEY` required)
- `requirements.txt` - Python package dependencies
