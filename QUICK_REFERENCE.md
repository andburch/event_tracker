# Quick Reference Card

## Common Commands

```bash
# Scraping
python llm_scraper.py                    # Scrape all sites
python llm_scraper.py fibber mesa        # Scrape specific sites
python llm_scraper.py list               # List all available sites
python llm_scraper.py --no-purge         # Append without deleting existing events

# Scoring
python score_events.py                   # Score all unscored events

# Web Interface
python server/app.py                     # Start web server (http://localhost:5000)

# Testing
python _test_llm_scrape.py <site>        # Test individual scraper
python _test_llm_scrape.py <site> --dump # Test with HTML dump
python check_groq_quota.py               # Check API quota
```

## File Locations

| File | Purpose |
|------|---------|
| `sources.py` | **EDIT THIS** to add new scrapers |
| `pagination_engine.py` | Pagination logic (rarely edit) |
| `llm_scrape_core.py` | Low-level utilities (rarely edit) |
| `llm_scraper.py` | Main scraper (rarely edit) |
| `HOW_TO_ADD_SCRAPERS.md` | Guide for adding scrapers |
| `ARCHITECTURE.md` | Complete system documentation |
| `.env` | API keys (create from `.env.example`) |
| `events.db` | SQLite database (auto-created) |

## Adding a New Scraper (5 minutes)

1. **Open** `sources.py`
2. **Add** to `SITES` dict:
   ```python
   'mykey': (
       'Display Name',
       'https://example.com/events',
       True,  # Selenium? (True for JS sites, False for static)
       5,     # Wait seconds after page load
       5,     # Max pages to scrape
       '',    # Optional notes
       ('#ffffff', '#000000', '#333333'),  # Colors (bg, border, text)
       None,  # Pagination config (see below)
   ),
   ```
3. **Test**: `python llm_scraper.py mykey`

## Pagination Types

| Type | When to Use | Config Example |
|------|-------------|----------------|
| `None` (LLM) | Most sites with standard pagination | `None` |
| `multi_month` | Monthly calendars | `{'type': 'multi_month', 'months': 3, 'url_template': '...'}` |
| `url_param` | ?page=N in URL | `{'type': 'url_param', 'param_name': 'page', 'start_index': 1}` |
| `js_button` | JavaScript "Next" buttons | `{'type': 'js_button', 'button_selector': 'a.next'}` |
| `calendar_grid` | Month grids needing date context | `{'type': 'calendar_grid', 'months': 3, 'url_template': '...'}` |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Access Denied" / 403 | Increase `wait` to 10-15 seconds |
| No events found | Check if `use_selenium` should be `True` |
| Pagination not working | Try different pagination type |
| API quota exceeded | Wait or upgrade Groq plan |
| Scraper fails | Check `/health` dashboard for details |

## Architecture Flow

```
User runs: python llm_scraper.py fibber
    │
    ├─▶ Load config from sources.py
    ├─▶ pagination_engine.scrape_with_pagination()
    │   ├─▶ fetch_selenium() or fetch_requests()
    │   ├─▶ clean_html()
    │   └─▶ ask_llm() → Groq API
    ├─▶ Save events to database
    └─▶ Print summary
```

## Web Interface Routes

| Route | Purpose |
|-------|---------|
| `/` | Event list (sorted by score) |
| `/calendar` | Monthly calendar view |
| `/profile` | User preferences |
| `/health` | Scraper health dashboard |
| `/feedback` | Submit interested/not interested |
| `/pin` | Toggle event pinned status |

## Database Tables

| Table | Purpose |
|-------|---------|
| `Event` | Scraped events |
| `ScraperRun` | Scraping history |
| `UserProfile` | User preferences |
| `FeedbackHistory` | User feedback |
| `PreferenceProfileHistory` | Preference evolution |

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | API keys (GROQ_API_KEY) |
| `config.py` | App settings (DB path, coordinates, LLM params) |
| `sources.py` | Scraper configurations |

## Key Design Principles

1. **Configuration Over Code** - Add scrapers by editing config, not writing code
2. **LLM-First** - No brittle CSS selectors, resilient to redesigns
3. **Separation of Concerns** - Config → Engine → Utilities → API
4. **Fail-Safe** - Retry logic, graceful degradation, comprehensive logging

## Performance

- Static sites: ~2-5 seconds per page
- JavaScript sites: ~8-15 seconds per page
- LLM extraction: ~5-10 seconds per page
- Single site: 30-60 seconds
- All 23 sites: 15-30 minutes

## Getting Help

1. Check [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md) for detailed examples
2. Check [ARCHITECTURE.md](ARCHITECTURE.md) for system documentation
3. Check `/health` dashboard for scraper status
4. Test individual scrapers: `python _test_llm_scrape.py <key>`
5. Check logs for error messages

## Example: Adding Fibber Magees

```python
# In sources.py SITES dict:
'fibber': (
    'Fibber Magees',                              # Display name
    'https://www.fibbermageespub.com/events',     # URL
    False,                                        # Static HTML (no JS)
    3,                                            # Wait 3 seconds
    5,                                            # Max 5 pages
    '',                                           # No special notes
    ('#fff7ed', '#c2410c', '#7c2d12'),           # Orange theme
    None,                                         # LLM pagination (default)
),
```

Test: `python llm_scraper.py fibber`

Result: ✅ Found 25 events, added 7 new ones in 47s

## Maintenance Checklist

- [ ] Backup `events.db` before major changes
- [ ] Test scrapers after adding new ones
- [ ] Monitor `/health` dashboard for failures
- [ ] Check Groq API quota: `python check_groq_quota.py`
- [ ] Update documentation when adding features
- [ ] Commit changes to git regularly

## Quick Debugging

```bash
# Test a scraper
python llm_scraper.py mysite

# See raw HTML
python _test_llm_scrape.py mysite --dump

# Check health
python server/app.py
# Visit http://localhost:5000/health

# Check API quota
python check_groq_quota.py

# Check database
sqlite3 events.db "SELECT COUNT(*) FROM event;"
```
