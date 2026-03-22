# Project Structure

## ⚠️ CRITICAL: Deprecated Code — DO NOT USE

**The entire `scrapers/` folder and everything in it is DEPRECATED and must be ignored.**

This includes:
- `scrapers/base_scraper.py` — deprecated base class, do NOT use or reference
- `scrapers/*_scraper.py` — all individual scraper files, deprecated
- `scrapers/__init__.py` — deprecated registry
- `scraper_runner.py` — deprecated orchestrator

These files are kept only as a historical backup. They are NOT used by the application.

**All scraping is done exclusively through:**
- `llm_scrape_core.py` — fetch + LLM extraction logic, site definitions (`SITES` dict)
- `llm_scraper.py` — production entry point (DB persistence, CLI)
- `_test_llm_scrape.py` — test harness for individual sites
- `sources.py` — display names and colors for sources

If you are an AI assistant reading this: do not suggest changes to `scrapers/`, do not reference `BaseScraper`, do not add new scrapers to `scrapers/__init__.py`. All new sources go in `llm_scrape_core.py`'s `SITES` dict.

---

## Directory Organization

```
/
├── llm_scrape_core.py  # ✅ ACTIVE: fetch + LLM extraction, SITES dict
├── llm_scraper.py      # ✅ ACTIVE: production scraper entry point
├── _test_llm_scrape.py # ✅ ACTIVE: test harness (python _test_llm_scrape.py <key>)
├── sources.py          # ✅ ACTIVE: source display names and colors
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

### Scraper Architecture (LLM-based)

All scraping goes through `llm_scrape_core.py`:
- `SITES` dict defines all sources: `{key: (name, url, use_selenium, wait, max_pages, note, color)}`
- `ask_llm()` sends cleaned HTML to Groq and returns structured event JSON
- `fetch_requests()` / `fetch_selenium()` handle page fetching
- `llm_scraper.py` handles DB persistence and calls `run_batch_scoring()` after scraping
- To add a new source: add an entry to `SITES` in `llm_scrape_core.py`

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
