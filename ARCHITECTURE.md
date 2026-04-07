# Phoenix Events Recommender - Architecture Documentation

## System Overview

Phoenix Events Recommender is a configuration-driven event aggregation system that scrapes events from 21+ Phoenix Valley sources, stores them in SQLite, and uses LLM-based preference learning to recommend relevant events to users.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERACTIONS                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  CLI Commands              Web Interface           Batch Processing  │
│  ├─ llm_scraper.py        ├─ server/app.py        ├─ score_events.py│
│  ├─ list                  ├─ / (event list)       └─ (LLM scoring)  │
│  ├─ scrape <site>         ├─ /calendar                              │
│  └─ scrape all            ├─ /profile                               │
│                           └─ /health                                 │
│                                                                       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CORE SCRAPING ENGINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐      ┌──────────────────┐      ┌───────────────┐ │
│  │  sources.py  │─────▶│ pagination_engine│─────▶│llm_scrape_core│ │
│  │              │      │      .py          │      │     .py       │ │
│  │ SITES dict   │      │                  │      │               │ │
│  │ (21 sites)   │      │ 5 pagination     │      │ fetch_*()     │ │
│  │              │      │ handlers         │      │ clean_html()  │ │
│  │ Config:      │      │                  │      │ ask_llm()     │ │
│  │ - URL        │      │ ├─ llm           │      │               │ │
│  │ - Selenium?  │      │ ├─ multi_month   │      └───────────────┘ │
│  │ - Wait time  │      │ ├─ url_param     │              │         │
│  │ - Max pages  │      │ ├─ js_button     │              │         │
│  │ - Pagination │      │ └─ calendar_grid │              │         │
│  │   config     │      │                  │              │         │
│  └──────────────┘      └──────────────────┘              │         │
│                                                           │         │
│                                                           ▼         │
│                                                  ┌─────────────────┐│
│                                                  │   Groq API      ││
│                                                  │   (LLM)         ││
│                                                  │                 ││
│                                                  │ - Extract events││
│                                                  │ - Find next URL ││
│                                                  │ - Score events  ││
│                                                  └─────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA PERSISTENCE                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SQLite Database (events.db)                │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │                                                               │  │
│  │  Tables:                                                      │  │
│  │  ├─ Event                  (scraped events)                  │  │
│  │  ├─ ScraperRun             (scraping history)                │  │
│  │  ├─ UserProfile            (user preferences)                │  │
│  │  ├─ FeedbackHistory        (user feedback)                   │  │
│  │  └─ PreferenceProfileHistory (preference evolution)          │  │
│  │                                                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Managed by: database/models.py (SQLAlchemy ORM)                    │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Scraping Flow (Detailed)

```
USER RUNS: python llm_scraper.py fibber
│
├─▶ llm_scraper.py main()
│   │
│   ├─ Parse CLI args
│   ├─ Load SITES from sources.py
│   ├─ Create DB session
│   │
│   └─▶ For each site:
│       │
│       ├─ Extract config: (name, url, use_selenium, wait, max_pages, note, color, pagination_config)
│       │
│       └─▶ scrape_and_save(key, name, url, use_selenium, wait, max_pages, pagination_config, session)
│           │
│           ├─▶ pagination_engine.scrape_with_pagination()
│           │   │
│           │   ├─ Determine pagination type from config
│           │   │  ├─ None or 'llm' → LLM extracts next_page_url
│           │   │  ├─ 'multi_month' → Generate month URLs
│           │   │  ├─ 'url_param' → Increment ?page=N
│           │   │  ├─ 'js_button' → Click Next button
│           │   │  └─ 'calendar_grid' → Month grid + date injection
│           │   │
│           │   ├─▶ For each page:
│           │   │   │
│           │   │   ├─▶ fetch_selenium() or fetch_requests()
│           │   │   │   └─ Returns: raw HTML
│           │   │   │
│           │   │   ├─▶ clean_html(html)
│           │   │   │   ├─ Remove scripts, styles, nav, footer
│           │   │   │   ├─ Inline links as "Text [/url]"
│           │   │   │   └─ Returns: clean text
│           │   │   │
│           │   │   ├─▶ apply_trim(text, key)
│           │   │   │   ├─ Looks up TRIM_PATTERNS[key] in sources.py
│           │   │   │   ├─ Strips nav menus, filter sidebars, cookie banners
│           │   │   │   └─ Cuts 15-76% of tokens on most sites
│           │   │   │
│           │   │   ├─▶ ask_llm(text, url, site_hint)
│           │   │   │   ├─ Send to Groq API
│           │   │   │   ├─ Chunk if > 6000 chars
│           │   │   │   ├─ Extract structured JSON
│           │   │   │   └─ Returns: {events: [...], next_page_url: "..."}
│           │   │   │
│           │   │   └─ Collect events
│           │   │
│           │   └─ Returns: all_events list
│           │
│           ├─▶ For each event in all_events:
│           │   │
│           │   ├─ parse_date(date_str, time_str)
│           │   ├─ Check if exists in DB (by title + date)
│           │   ├─ If new:
│           │   │   └─ session.add(Event(...))
│           │   │
│           │   └─ events_added++
│           │
│           ├─ session.commit()
│           │
│           └─ Returns: (events_found, events_added, success, error_message)
│
└─▶ Print summary
    Close driver
    Close session
```

## Pagination Type Decision Tree

```
                        ┌─────────────────────┐
                        │  Site Config in     │
                        │    sources.py       │
                        └──────────┬──────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │ pagination_config set?   │
                    └──────────┬───────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
               NO                            YES
                │                             │
                ▼                             ▼
        ┌───────────────┐          ┌──────────────────┐
        │  Use 'llm'    │          │ Check 'type' key │
        │  (default)    │          └────────┬─────────┘
        └───────────────┘                   │
                │                           │
                │         ┌─────────────────┼─────────────────┬─────────────────┐
                │         │                 │                 │                 │
                ▼         ▼                 ▼                 ▼                 ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
        │   llm    │  │multi_month│  │url_param │  │js_button │  │calendar_grid │
        └────┬─────┘  └─────┬─────┘  └─────┬────┘  └─────┬────┘  └──────┬───────┘
             │              │              │             │               │
             ▼              ▼              ▼             ▼               ▼
    ┌────────────┐  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐
    │LLM extracts│  │Generate N  │ │Increment   │ │Click Next│ │Month URLs +  │
    │next_page   │  │month URLs  │ │?page=N     │ │button in │ │date injection│
    │URL from    │  │from        │ │parameter   │ │JavaScript│ │for LLM       │
    │page content│  │template    │ │in URL      │ │          │ │context       │
    └────────────┘  └────────────┘ └────────────┘ └──────────┘ └──────────────┘
```

## Configuration-Driven Design

### Adding a New Scraper (5 minutes)

```
1. Open sources.py
   │
   ├─▶ Find SITES dict
   │
   └─▶ Add new entry:
       
       'mysite': (
           'My Site Name',                    # Display name
           'https://mysite.com/events',       # URL
           True,                              # Use Selenium?
           5,                                 # Wait seconds
           5,                                 # Max pages
           'Optional note',                   # Notes
           ('#fff', '#000', '#333'),          # Colors (bg, border, text)
           None,                              # Pagination config (or dict)
       ),

2. Choose pagination type:
   │
   ├─ None → LLM pagination (works for most sites)
   │
   ├─ {'type': 'multi_month', 'months': 3, 'url_template': '...'}
   │
   ├─ {'type': 'url_param', 'param_name': 'page', 'start_index': 1}
   │
   ├─ {'type': 'js_button', 'button_selector': 'a.next'}
   │
   └─ {'type': 'calendar_grid', 'months': 3, 'url_template': '...'}

3. Test:
   python llm_scraper.py mysite

4. Done!
```

## Data Flow: Event Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EVENT LIFECYCLE                              │
└─────────────────────────────────────────────────────────────────────┘

1. SCRAPING
   │
   ├─▶ HTML fetched from source website
   │   └─ Via requests (static) or Selenium (JavaScript)
   │
   ├─▶ HTML cleaned and sent to LLM
   │   └─ Groq API extracts structured event data
   │
   └─▶ Event saved to database
       └─ Table: Event (title, date, venue, url, source, description)

2. SCORING (batch process)
   │
   ├─▶ python score_events.py
   │
   ├─▶ For each event without a score:
   │   │
   │   ├─ Load user preferences from UserProfile
   │   ├─ Send event + preferences to LLM
   │   └─ LLM returns relevance score (0.0 - 1.0)
   │
   └─▶ Event.score updated in database

3. USER INTERACTION (web interface)
   │
   ├─▶ User views events at http://localhost:5000
   │   └─ Events sorted by score (highest first)
   │
   ├─▶ User provides feedback (interested/not interested)
   │   ├─ Saved to FeedbackHistory table
   │   └─ UserProfile updated with new preferences
   │
   └─▶ User pins events to short list
       └─ Event.pinned = True

4. PREFERENCE LEARNING
   │
   └─▶ As user provides feedback:
       │
       ├─ LLM analyzes feedback patterns
       ├─ Generates preference summary
       ├─ Updates UserProfile
       └─ Future scores reflect learned preferences
```

## Component Responsibilities

### sources.py
**Role:** Single source of truth for all scraper configurations

**Contains:**
- `SITES` dict with all 23 site configurations
- Each entry: (name, url, use_selenium, wait, max_pages, note, color, pagination_config)
- `TRIM_PATTERNS` dict -- one entry per site, strips nav/filter boilerplate before LLM
- `SOURCE_NAMES` and `SOURCE_COLORS` derived dicts for UI

**Used by:** llm_scraper.py, server/app.py, pagination_engine.py

---

### pagination_engine.py
**Role:** Configuration-driven pagination execution

**Contains:**
- 5 pagination handlers (generators that yield page data)
- `_HANDLERS` registry mapping type names to functions
- `scrape_with_pagination()` main entry point

**Handlers:**
1. `_paginate_multi_month()` - Generate month-based URLs
2. `_paginate_url_param()` - Increment URL parameters
3. `_paginate_js_button()` - Click JavaScript buttons
4. `_paginate_calendar_grid()` - Month grids with date injection
5. LLM pagination (inline in main function)

**Used by:** llm_scraper.py

---

### llm_scrape_core.py
**Role:** Low-level scraping utilities (no site-specific logic)

**Contains:**
- `fetch_requests()` - Fetch static HTML
- `fetch_selenium()` - Fetch JavaScript-rendered pages
- `clean_html()` - Strip HTML to clean text
- `apply_trim()` - Strip site-specific boilerplate using TRIM_PATTERNS from sources.py
- `ask_llm()` - Send text to Groq, get structured events
- `get_driver()` / `close_driver()` - Selenium management

**Used by:** pagination_engine.py

---

### llm_scraper.py
**Role:** Production scraper entry point with DB persistence

**Contains:**
- `parse_date()` - Convert LLM date strings to datetime
- `scrape_and_save()` - Thin wrapper around pagination engine + DB save
- `main()` - CLI argument parsing and orchestration

**Usage:**
```bash
python llm_scraper.py              # Scrape all sites
python llm_scraper.py fibber mesa  # Scrape specific sites
python llm_scraper.py list         # List all sites
python llm_scraper.py --no-purge   # Append without deleting
```

---

### database/models.py
**Role:** SQLAlchemy ORM models

**Tables:**
- `Event` - Scraped events (title, date, venue, url, source, score, pinned)
- `ScraperRun` - Scraping history (source, timestamp, events_found, success)
- `UserProfile` - User preferences (summary text)
- `FeedbackHistory` - User feedback (event_id, interested, timestamp)
- `PreferenceProfileHistory` - Preference evolution over time

---

### recommender/llm_filter.py
**Role:** LLM-based event scoring and preference learning

**Contains:**
- `score_events()` - Batch score all unscored events
- `generate_preference_summary()` - Analyze feedback, update preferences
- Groq API integration for scoring

**Usage:**
```bash
python score_events.py  # Run after scraping
```

---

### server/app.py
**Role:** Flask web interface

**Routes:**
- `/` - Event list (sorted by score)
- `/calendar` - Monthly calendar view
- `/profile` - User preferences page
- `/profile/summary` - Generate preference summary
- `/health` - Scraper health dashboard
- `/feedback` - Submit interested/not interested
- `/pin` - Toggle event pinned status

**Usage:**
```bash
python server/app.py
# Visit http://localhost:5000
```

## Technology Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TECHNOLOGY LAYERS                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    PRESENTATION LAYER                        │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  Flask 3.0+ (Web Framework)                                 │   │
│  │  Jinja2 Templates (HTML rendering)                          │   │
│  │  Bootstrap/CSS (UI styling)                                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    APPLICATION LAYER                         │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  Python 3.x                                                  │   │
│  │  Configuration-driven pagination engine                     │   │
│  │  LLM-based event extraction & scoring                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    SCRAPING LAYER                            │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  Selenium 4.15+ (JavaScript-heavy sites)                    │   │
│  │  Requests (Static HTML sites)                               │   │
│  │  BeautifulSoup4 (HTML parsing)                              │   │
│  │  ChromeDriver (Headless browser)                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    AI/LLM LAYER                              │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  Groq API (llama-3.3-70b-versatile)                         │   │
│  │  - Event extraction from HTML                               │   │
│  │  - Pagination URL detection                                 │   │
│  │  - Event relevance scoring                                  │   │
│  │  - Preference learning                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    DATA LAYER                                │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  SQLite (Database)                                           │   │
│  │  SQLAlchemy 2.0+ (ORM)                                       │   │
│  │  python-dotenv (Environment config)                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Configuration Over Code
- Add new scrapers by editing config, not writing code
- Pagination behavior defined declaratively
- Easy to maintain without AI assistance

### 2. Separation of Concerns
- `sources.py` - Configuration
- `pagination_engine.py` - Pagination logic
- `llm_scrape_core.py` - Low-level utilities
- `llm_scraper.py` - Orchestration + persistence

### 3. LLM-First Approach
- LLM extracts events from any HTML structure
- No brittle CSS selectors
- Resilient to website redesigns

### 4. Fail-Safe Design
- Retry logic for API failures
- Graceful degradation on errors
- Comprehensive error logging

### 5. User Privacy
- All data stored locally (SQLite)
- No external tracking
- User controls all preferences

## Performance Characteristics

### Scraping Speed
- Static sites (requests): ~2-5 seconds per page
- JavaScript sites (Selenium): ~8-15 seconds per page
- LLM extraction: ~5-10 seconds per page (with chunking)

### Typical Scrape Times
- Single site: 30-60 seconds
- All 21 sites: 15-30 minutes
- Depends on: page count, Selenium usage, LLM API speed

### API Usage
- Groq API: ~1-3 calls per page (with chunking)
- Rate limits: Handled with retry + backoff
- Quota monitoring: `python check_groq_quota.py`

## Security Considerations

### Bot Detection Mitigation
- User-agent spoofing via CDP
- Fresh Selenium sessions per site
- Configurable wait times
- SSL verification disabled (corporate firewall)

### Data Security
- API keys in `.env` (not in git)
- Local SQLite database
- No external data transmission (except Groq API)

### Input Validation
- URL validation before scraping
- Date parsing with fallbacks
- SQL injection prevention (SQLAlchemy ORM)

## Maintenance Guide

### Adding a New Site
1. Edit `sources.py`
2. Add entry to `SITES` dict (name, url, selenium, wait, max_pages, note, color, pagination_config)
3. Collect artifact: `python3 _collect_artifacts.py`
4. Inspect `debug_artifacts/<key>/page_1_cleaned.txt` to find trim pattern
5. Add entry to `TRIM_PATTERNS` dict in same file (or `None` if no boilerplate)
6. Test: `python llm_scraper.py <key>`

See `HOW_TO_ADD_SCRAPERS.md` for full details.

### Debugging a Scraper
1. Test individually: `python llm_scraper.py <key>`
2. Check raw HTML: `python _test_llm_scrape.py <key> --dump`
3. Adjust wait time or pagination config
4. Check health dashboard: http://localhost:5000/health

### Updating Pagination Logic
1. Edit handler in `pagination_engine.py`
2. Test affected sites
3. Update documentation

### Database Migrations
- SQLAlchemy handles schema automatically
- Backup `events.db` before major changes
- No migration framework needed (simple schema)

## Future Enhancements

### Potential Improvements
- [ ] Add more pagination types as needed
- [ ] Implement caching for frequently scraped pages
- [ ] Add email notifications for new events
- [ ] Export events to calendar formats (iCal)
- [ ] Mobile-responsive web interface
- [ ] Multi-user support
- [ ] Event deduplication across sources

### Scalability Considerations
- Current design: Single-user, local deployment
- For multi-user: Add authentication, user isolation
- For scale: Consider PostgreSQL, Redis caching, async scraping
