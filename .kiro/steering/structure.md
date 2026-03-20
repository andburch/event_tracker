# Project Structure

## Directory Organization

```
/
├── scrapers/           # Event scraper implementations
│   ├── base_scraper.py       # Abstract base class for all scrapers
│   ├── *_scraper.py          # Individual venue/source scrapers
│   └── __init__.py           # Scraper registry (SCRAPERS list)
├── database/           # Database models and configuration
│   ├── models.py             # SQLAlchemy models (Event, UserFeedback)
│   └── __init__.py
├── recommender/        # LLM-based recommendation engine
│   ├── llm_filter.py         # Event scoring logic
│   └── __init__.py
├── server/             # Flask web application
│   ├── app.py                # Flask routes and API endpoints
│   └── templates/
│       └── index.html        # Main web interface
├── config.py           # Application configuration
├── scraper_runner.py   # Orchestrates all scrapers
├── events.db           # SQLite database (generated)
├── requirements.txt    # Python dependencies
└── .env                # Environment variables (not in git)
```

## Key Architectural Patterns

### Scraper Architecture

All scrapers inherit from `BaseScraper` abstract base class:
- Each scraper implements `scrape()` method returning list of event dicts
- `BaseScraper` provides Selenium driver management and helper methods
- Scrapers registered in `scrapers/__init__.py` SCRAPERS list
- Standard event format: `{title, description, venue, date, url, source, category}`

### Database Layer

- SQLAlchemy ORM with declarative base
- Two main models: `Event` and `UserFeedback`
- Session management via `Session()` factory
- Database URL configured in `config.py`

### Web Server

- Flask application with template rendering
- Routes: `/` (event listing), `/feedback` (POST endpoint)
- Source filtering via query parameters
- LLM scoring integrated into event display

## Naming Conventions

- Scraper files: `{venue}_scraper.py` (lowercase, underscores)
- Scraper classes: `{Venue}Scraper` (PascalCase)
- Database models: PascalCase (Event, UserFeedback)
- Functions/methods: snake_case
- Source names: lowercase, no spaces (e.g., 'yuccatap', 'eventbrite')

## Adding New Scrapers

1. Create `scrapers/{venue}_scraper.py` inheriting from `BaseScraper`
2. Implement `scrape()` method
3. Add to `scrapers/__init__.py` SCRAPERS list
4. Use `self.get_driver()` for JavaScript sites, `self.get_page()` for static sites
5. Return normalized events via `self.normalize_event()`

## Configuration Files

- `config.py` - Application settings (database, API keys, coordinates)
- `.env` - Secrets and environment-specific values
- `requirements.txt` - Python package dependencies
