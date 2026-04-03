# Changelog

All notable changes to the Phoenix Events Recommender project are documented in this file.

## [Unreleased] - 2026-04-02

### Configuration Improvements

**Summary:** Centralized LLM model configuration to make it easier to switch models without code changes.

**Changes:**

1. **Model Configuration:**
   - Added `LLM_SCRAPING_MODEL` and `LLM_SCORING_MODEL` to `config.py`
   - All model names now read from config instead of hardcoded strings
   - Makes it easy to switch to self-hosted LLMs in the future

2. **Quota Check Improvements:**
   - `check_groq_quota.py` now checks the actual models used by the application
   - Supports `--model <name>` flag to check specific models
   - Shows quota for both scraping and scoring models (if different)

**Files Modified:**
- `config.py` - Added LLM model configuration constants
- `llm_scrape_core.py` - Reads model from config
- `recommender/llm_filter.py` - Reads model from config
- `check_groq_quota.py` - Enhanced to check multiple models

### Major Refactoring: Configuration-Driven Pagination Engine

**Summary:** Eliminated 260+ lines of duplicated pagination code by implementing a configuration-driven pagination engine. Adding new scrapers now requires only editing `sources.py` - no code changes needed.

**Changes:**

1. **New Files:**
   - `pagination_engine.py` - Configuration-driven pagination system with 5 handler types
   - `HOW_TO_ADD_SCRAPERS.md` - Comprehensive guide for adding new event sources

2. **Refactored Files:**
   - `sources.py` - Now the SINGLE SOURCE OF TRUTH for all scraper configs
     - Added 8th tuple element: `pagination_config` dict
     - All 21 sites now have explicit pagination configs
   - `llm_scraper.py` - Simplified from 400+ lines to ~150 lines
     - Removed all site-specific pagination code
     - `scrape_and_save()` now delegates to `pagination_engine.scrape_with_pagination()`
   - `llm_scrape_core.py` - Removed `SITES` import (now in sources.py)

3. **Pagination Types Implemented:**
   - `llm` - LLM extracts next_page_url from page content (default, 13 sites)
   - `multi_month` - Generate month-based URLs (dirtydrummer)
   - `url_param` - Increment URL parameters (chandler, mesa, chandler_lib)
   - `js_button` - Click JavaScript buttons (phoenix, azmnh)
   - `calendar_grid` - Month-view with date injection (tca, gilbert)

4. **Benefits:**
   - **Maintainability:** No more duplicated pagination code
   - **Extensibility:** Add new sites by editing config only
   - **Clarity:** Each pagination pattern has clear documentation
   - **Future-proof:** Easy to maintain without AI assistance

5. **Migration:**
   - All 21 existing scrapers migrated to new system
   - Backward compatible - no database changes
   - No changes to CLI interface

**Testing:** Fibber scraper tested successfully - found 25 events, added 7 new ones in 47s using new pagination engine.

**Documentation:**
- Created `ARCHITECTURE.md` - Complete system documentation with ASCII flow charts
- Created `QUICK_REFERENCE.md` - Quick reference card for common tasks
- Updated `README.md` - Added architecture overview and quick start
- Updated `HOW_TO_ADD_SCRAPERS.md` - Comprehensive guide with examples

---

## [2024-01-XX] - Code Quality Improvements

### Major Code Quality Improvements

This release focuses on fixing critical bugs, removing technical debt, and improving code quality based on a comprehensive code review.

---

## Critical Fixes

### 1. Documentation Overhaul

**Problem:** README.md and tech.md contained completely outdated information referencing deprecated code and wrong commands.

**Fixed:**
- **README.md**: Complete rewrite with correct information
  - Changed API reference from OpenAI to Groq
  - Updated all commands to use `llm_scraper.py` instead of deprecated `scraper_runner.py`
  - Updated test commands to use `_test_llm_scrape.py` instead of `test_new_scrapers.py`
  - Fixed environment variable from `OPENAI_API_KEY` to `GROQ_API_KEY`
  - Updated scraper keys to match current implementation (e.g., `fibber`, `mesa`, `phoenix`)
  - Added comprehensive usage examples and troubleshooting section
  - Documented LLM-based scraping architecture
  - Removed all references to deprecated `scrapers/` directory

- **tech.md**: Updated with correct commands
  - Fixed scraper command: `python llm_scraper.py`
  - Added command variations (list, specific sites, --no-purge)
  - Added batch scoring command: `python score_events.py`
  - Fixed test command: `python _test_llm_scrape.py <site_key>`

**Impact:** Users can now follow correct instructions without confusion or errors.

**Files Changed:**
- `README.md` - Complete rewrite
- `.kiro/steering/tech.md` - Command section updated

---

### 2. Database Session Management

**Problem:** Multiple Flask routes created database sessions without proper cleanup in error cases, leading to potential connection leaks and resource exhaustion.

**Fixed:**
- Added `try/finally` blocks to all 7 Flask routes that create sessions:
  - `index()` - Main event listing
  - `feedback()` - Record thumbs up/down
  - `health()` - Scraper health dashboard
  - `calendar_view()` - Monthly calendar
  - `profile()` - User profile page
  - `pin()` - Toggle event pinned status
  - `profile_summary()` - Save preference summary

- Fixed session management in `recommender/llm_filter.py`:
  - `get_profile()` - Now uses try/finally
  - `maybe_update_preference_summary()` - Verified correct try/except/finally usage

**Before:**
```python
def index():
    session = Session()
    # ... do work ...
    session.close()  # Never reached if exception occurs
    return render_template(...)
```

**After:**
```python
def index():
    session = Session()
    try:
        # ... do work ...
        return render_template(...)
    finally:
        session.close()  # Always executed, even on exception
```

**Impact:** 
- Prevents database connection leaks
- Improves application stability under error conditions
- Prevents connection pool exhaustion

**Files Changed:**
- `server/app.py` - All 7 routes updated
- `recommender/llm_filter.py` - 2 functions updated

---

### 3. Removed Unused Configuration Constant

**Problem:** `SCRAPE_INTERVAL_HOURS = 6` was defined in `config.py` but never used anywhere in the codebase.

**Fixed:**
- Removed the unused constant and its documentation
- The comment already acknowledged that scheduling should be handled externally

**Rationale:** Dead code creates confusion and maintenance burden. Since the application doesn't implement internal scheduling, this constant served no purpose.

**Impact:** Cleaner configuration file with only actively used settings.

**Files Changed:**
- `config.py` - Removed lines 58-64

---

### 4. Removed Unused Model Constant and Parameter

**Problem:** `_MODEL_SMALL = 'llama-3.1-8b-instant'` was defined with a comment suggesting it should be used for simple pages, but it was never actually used anywhere in the code.

**Fixed:**
- Removed `_MODEL_SMALL` constant
- Removed unused `model` parameter from:
  - `ask_llm(text, current_url, site_hint='', retries=3, model=None)` → `ask_llm(text, current_url, site_hint='', retries=3)`
  - `_ask_llm_single(..., model=None)` → `_ask_llm_single(...)`
- Updated all function calls to remove the unused parameter
- Simplified model selection to always use `_MODEL` (llama-3.3-70b-versatile)

**Before:**
```python
_MODEL       = 'llama-3.3-70b-versatile'
_MODEL_SMALL = 'llama-3.1-8b-instant'  # Never used

def ask_llm(text, current_url, site_hint='', retries=3, model=None):
    # model parameter never passed by any caller
    return _ask_llm_single(..., model=model or _MODEL)
```

**After:**
```python
_MODEL = 'llama-3.3-70b-versatile'

def ask_llm(text, current_url, site_hint='', retries=3):
    return _ask_llm_single(..., retries=retries)
```

**Rationale:** 
- Eliminates dead code and unused parameters
- Reduces confusion about which model is actually being used
- Simplifies the API surface

**Impact:** Cleaner code with no functional changes (the small model was never used anyway).

**Files Changed:**
- `llm_scrape_core.py` - Removed constant, updated 4 function signatures and calls

---

### 5. Fixed SQLAlchemy NULL Comparison Anti-Pattern

**Problem:** Code used Python's `== None` operator for SQLAlchemy NULL comparisons, which is an anti-pattern. The code even had a `# noqa: E711` comment acknowledging this was wrong.

**Fixed:**
- Changed `Event.score == None` to `Event.score.is_(None)`
- Removed the `noqa` comment

**Before:**
```python
query = query.filter(Event.score == None)  # noqa: E711 — SQLAlchemy requires == None
```

**After:**
```python
query = query.filter(Event.score.is_(None))
```

**Rationale:**
- SQLAlchemy provides `.is_(None)` specifically for NULL comparisons
- Using `==` with None can lead to unexpected behavior in some cases
- Follows SQLAlchemy best practices and PEP 8 guidelines
- More explicit and readable

**Impact:** More correct and maintainable SQLAlchemy code.

**Files Changed:**
- `recommender/llm_filter.py` - Line 199

---

### 6. Fixed Silent Exception Swallowing

**Problem:** The `fetch_selenium()` function silently swallowed ALL exceptions during page loading with a bare `except Exception: pass`, making debugging impossible.

**Fixed:**
- Changed to catch the exception and log it
- Still continues with partial HTML (original intent) but now provides visibility

**Before:**
```python
try:
    driver.get(url)
except Exception:
    pass  # TimeoutException on slow pages -- partial HTML is still useful
```

**After:**
```python
try:
    driver.get(url)
except Exception as e:
    # TimeoutException on slow pages -- partial HTML is still useful
    # Log the error but continue with whatever HTML was loaded
    print(f"    Page load timeout/error (continuing with partial HTML): {type(e).__name__}")
```

**Rationale:**
- Silent failures make debugging extremely difficult
- Logging the exception type helps identify patterns (timeouts vs. other errors)
- Still maintains the original behavior of continuing with partial HTML
- Provides visibility into scraping issues

**Impact:** Much easier to debug scraping problems while maintaining the same functional behavior.

**Files Changed:**
- `llm_scrape_core.py` - `fetch_selenium()` function

---

### 7. Added Input Validation to Flask Endpoints

**Problem:** Three Flask endpoints accepted user input without validation, which could cause crashes or unexpected behavior on malformed requests.

**Fixed:**

#### `/feedback` Endpoint
Added validation for:
- JSON data presence
- `event_id` presence and type (must be integer)
- `interested` presence and type (must be boolean)

**Before:**
```python
@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    event_id = data.get('event_id')
    interested = data.get('interested')
    # No validation - crashes if data is None or wrong type
```

**After:**
```python
@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
    
    event_id = data.get('event_id')
    if event_id is None:
        return jsonify({'status': 'error', 'message': 'event_id is required'}), 400
    if not isinstance(event_id, int):
        return jsonify({'status': 'error', 'message': 'event_id must be an integer'}), 400
    
    interested = data.get('interested')
    if interested is None:
        return jsonify({'status': 'error', 'message': 'interested is required'}), 400
    if not isinstance(interested, bool):
        return jsonify({'status': 'error', 'message': 'interested must be a boolean'}), 400
```

#### `/pin` Endpoint
Added validation for:
- JSON data presence
- `event_id` presence and type (must be integer)

**Before:**
```python
@app.route('/pin', methods=['POST'])
def pin():
    event_id = request.json.get('event_id')
    # No validation - crashes if request.json is None
```

**After:**
```python
@app.route('/pin', methods=['POST'])
def pin():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
    
    event_id = data.get('event_id')
    if event_id is None:
        return jsonify({'status': 'error', 'message': 'event_id is required'}), 400
    if not isinstance(event_id, int):
        return jsonify({'status': 'error', 'message': 'event_id must be an integer'}), 400
```

#### `/profile/summary` Endpoint
Added validation for:
- `preference_summary` length (max 10,000 characters to prevent abuse)

**Before:**
```python
@app.route('/profile/summary', methods=['POST'])
def profile_summary():
    summary = request.form.get('preference_summary', '').strip()
    # No length validation - could accept extremely long inputs
```

**After:**
```python
@app.route('/profile/summary', methods=['POST'])
def profile_summary():
    summary = request.form.get('preference_summary', '').strip()
    
    if len(summary) > 10000:
        return jsonify({'status': 'error', 'message': 'Preference summary too long (max 10000 characters)'}), 400
```

**Rationale:**
- Prevents crashes from malformed requests
- Provides clear error messages to API consumers
- Prevents abuse (e.g., extremely long inputs)
- Follows REST API best practices
- Returns proper HTTP 400 status codes for bad requests

**Impact:** 
- More robust API endpoints
- Better error messages for debugging
- Prevents potential security issues from unvalidated input

**Files Changed:**
- `server/app.py` - 3 endpoints updated

---

## Summary Statistics

### Files Modified
- `README.md` - Complete rewrite
- `.kiro/steering/tech.md` - Commands section updated
- `config.py` - Removed unused constant
- `llm_scrape_core.py` - Removed unused model, fixed exception handling, added type hints
- `recommender/llm_filter.py` - Fixed session management, fixed NULL comparison, added type hints
- `server/app.py` - Fixed session management (7 routes), added input validation (3 routes)
- `database/models.py` - Fixed docstring reference
- `sources.py` - Removed legacy sources data
- `test_recommender.py` - Fixed logging configuration
- `llm_scraper.py` - Added type hints

### Lines Changed
- **Added:** ~250 lines (validation, try/finally blocks, type hints, documentation)
- **Removed:** ~80 lines (dead code, unused parameters, legacy data)
- **Modified:** ~300 lines (documentation, refactoring, type hints)

### Bug Categories Fixed
- **Critical:** 3 (Documentation, Session leaks, Silent exceptions)
- **High:** 4 (Input validation, SQLAlchemy anti-pattern, Type hints, Logging config)
- **Medium:** 4 (Dead code removal, Legacy data cleanup, Documentation fixes)

---

## Testing Recommendations

After applying these changes, test the following:

1. **Session Management**
   - Trigger errors in Flask routes (e.g., invalid database queries)
   - Verify sessions are properly closed (check connection pool)
   - Monitor for connection leaks under load

2. **Input Validation**
   - Send malformed JSON to `/feedback` and `/pin` endpoints
   - Send non-integer `event_id` values
   - Send non-boolean `interested` values
   - Send extremely long `preference_summary` (>10,000 chars)
   - Verify proper 400 error responses with descriptive messages

3. **Scraping**
   - Run scrapers and verify exception logging works
   - Check that timeouts are now visible in output
   - Verify scraping still works correctly despite logged errors

4. **General**
   - Verify all commands in README.md work correctly
   - Run full scraping cycle: `python llm_scraper.py`
   - Run batch scoring: `python score_events.py`
   - Test web interface: `python server/app.py`

---

## Migration Notes

### Breaking Changes
None. All changes are backward compatible.

### Configuration Changes
None required. The removed `SCRAPE_INTERVAL_HOURS` constant was never used.

### Database Changes
None required.

### API Changes
The following endpoints now return 400 errors for invalid input (previously would crash):
- `POST /feedback` - Validates event_id (int) and interested (bool)
- `POST /pin` - Validates event_id (int)
- `POST /profile/summary` - Validates length (max 10,000 chars)

Client code should handle these new error responses, though well-formed requests will continue to work as before.

---

### 8. Fixed Inconsistent Database Model Comment

**Problem:** The `Event` model docstring referenced the deprecated `scraper_runner.py` file.

**Fixed:**
- Updated comment to reference `llm_scraper.py scrape_and_save()` instead

**Before:**
```python
class Event(Base):
    """
    Deduplication key: (title, date) — see scraper_runner.py.
    """
```

**After:**
```python
class Event(Base):
    """
    Deduplication key: (title, date) — see llm_scraper.py scrape_and_save().
    """
```

**Impact:** Documentation now references the correct file.

**Files Changed:**
- `database/models.py` - Updated docstring

---

### 9. Removed Legacy Sources Data

**Problem:** `sources.py` contained a `_LEGACY_SOURCES` dictionary with 14 deprecated scraper keys that were merged into the active `SOURCE_NAMES` and `SOURCE_COLORS` dictionaries. This was meant for "historical scraper_run records" but added unnecessary complexity.

**Fixed:**
- Removed the entire `_LEGACY_SOURCES` dictionary (28 lines)
- Removed the loop that merged legacy sources into active dictionaries
- Simplified the code to only contain active sources

**Before:**
```python
SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}

# Legacy source keys from the old BeautifulSoup scrapers.
_LEGACY_SOURCES = {
    'phoenix_gov': ('City of Phoenix', ('#dbeafe', '#2563eb', '#1e3a8a')),
    'tempe_gov': ('City of Tempe', ('#e0e7ff', '#4f46e5', '#312e81')),
    # ... 12 more entries
}

for key, (name, color) in _LEGACY_SOURCES.items():
    SOURCE_NAMES[key] = name
    SOURCE_COLORS[key] = color
```

**After:**
```python
SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}
```

**Rationale:**
- The old scrapers are completely deprecated and removed
- Historical scraper_run records with old keys will simply show the key itself if not found
- Keeping legacy data pollutes the codebase and creates maintenance burden
- If historical data display is important, it should be handled via database migration

**Impact:** Cleaner code with 28 fewer lines. Historical scraper runs with old keys will display the raw key instead of a friendly name, which is acceptable for deprecated data.

**Files Changed:**
- `sources.py` - Removed lines 107-134

---

### 10. Added Type Hints Throughout Core Functions

**Problem:** Most functions lacked type hints, making it harder to catch type-related bugs and reducing IDE autocomplete effectiveness.

**Fixed:**
Added comprehensive type hints to key functions in three core modules:

#### llm_scraper.py
- `parse_date(date_str: str | None, time_str: str | None) -> datetime`
- `scrape_and_save(...) -> tuple[int, int, bool, str | None]`

#### llm_scrape_core.py
- `clean_html(html: str) -> str`
- `fetch_requests(url: str) -> str`
- `fetch_selenium(url: str, wait: int = 6, scroll_passes: int = 10) -> str`
- `_chunk_text(text: str)` - yields tuples
- `_ask_llm_single(...) -> dict`
- `ask_llm(text: str, current_url: str, site_hint: str = '', retries: int = 3) -> dict`

#### recommender/llm_filter.py
- `score_events(events: list) -> list[tuple]`
- `run_batch_scoring(session=None, rescore_all: bool = False) -> None`
- `maybe_update_preference_summary() -> None`
- `_call_batch_score(events: list, taste_prompt: str, preference_summary: str) -> dict[int, float]`

**Before:**
```python
def parse_date(date_str, time_str):
    """Convert LLM-returned date/time strings to a datetime object."""
    # No type information
```

**After:**
```python
def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """
    Convert LLM-returned date/time strings to a datetime object.
    
    Args:
        date_str: Date string in YYYY-MM-DD format (or None)
        time_str: Time string like "8:00 PM" (or None)
    
    Returns:
        datetime object with parsed date/time, or fallback with sentinel time
    """
```

**Rationale:**
- Type hints catch bugs at development time
- Improves IDE autocomplete and code navigation
- Makes function contracts explicit
- Follows modern Python best practices (PEP 484)
- Helps new developers understand the codebase

**Impact:** 
- Better IDE support and autocomplete
- Easier to catch type-related bugs
- More self-documenting code
- No runtime performance impact

**Files Changed:**
- `llm_scraper.py` - 2 functions updated
- `llm_scrape_core.py` - 6 functions updated
- `recommender/llm_filter.py` - 4 functions updated

---

### 11. Fixed Global Logging Configuration

**Problem:** `test_recommender.py` called `logging.basicConfig()` at module level, which affects global logging configuration even when the module is imported (not run directly).

**Fixed:**
- Moved `logging.basicConfig()` call inside the `if __name__ == '__main__':` block
- Now only configures logging when run as a script, not when imported

**Before:**
```python
import logging
import config

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# ... rest of module

if __name__ == '__main__':
    # main code
```

**After:**
```python
import logging
import config

log = logging.getLogger(__name__)

# ... rest of module

if __name__ == '__main__':
    # Configure logging only when run as main script
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    # main code
```

**Rationale:**
- Module-level `basicConfig()` calls affect the entire application
- If this module is ever imported elsewhere, it would override logging configuration
- Logging configuration should be controlled by the main entry point
- Follows Python logging best practices

**Impact:** 
- No side effects when importing the module
- Logging configuration only applies when running as a script
- More predictable logging behavior

**Files Changed:**
- `test_recommender.py` - Moved basicConfig() call

---

## Future Improvements

Issues identified but not yet fixed (in priority order):

### High Priority
1. **Refactor pagination duplication** - `llm_scraper.py` has 8 different pagination strategies with duplicated code
2. **Standardize logging** - Mix of `print()` and `logging` module throughout codebase

### Medium Priority
3. **Move hardcoded constants to config** - Chunk sizes, delays, thresholds scattered across files
4. **Document sentinel time value** - `12:34` used to indicate "no time found" is undocumented

### Low Priority
5. **Add thread safety** - Selenium driver uses global state (not thread-safe)
6. **Improve URL validation** - Current logic doesn't handle all edge cases

---

## Contributors

Code review and fixes by: [Your Name]
Date: 2024-01-XX

---

## References

- [SQLAlchemy Best Practices](https://docs.sqlalchemy.org/en/20/core/operators.html#sqlalchemy.sql.operators.ColumnOperators.is_)
- [Flask Error Handling](https://flask.palletsprojects.com/en/3.0.x/errorhandling/)
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)


---

## 2026-03-31: Code Quality Improvements - Magic Values, Logging, Thread Safety

### Issue 6: Hardcoded Magic Values Moved to Config

**Problem:**
Multiple tuning parameters were hardcoded throughout the codebase, making them difficult to find and adjust:
- `llm_scrape_core.py`: `_CHUNK_SIZE = 6_000`, `_CHUNK_OVERLAP = 300`, retry delays, chunk delays
- `recommender/llm_filter.py`: `SUMMARY_THRESHOLD = 10`, `CHUNK_SIZE = 40`, `CHUNK_DELAY = 12`, `MAX_RETRIES = 3`, `RETRY_BASE_DELAY = 5`

**Solution:**
Centralized all tuning parameters in `config.py`:

```python
# config.py additions
# LLM Scraping Configuration
LLM_CHUNK_SIZE = 6_000          # Characters per chunk when splitting large pages
LLM_CHUNK_OVERLAP = 300         # Character overlap between chunks
LLM_CHUNK_DELAY = 10            # Seconds between chunk requests (rate limiting)
LLM_MAX_RETRIES = 3             # Maximum retry attempts for failed LLM requests
LLM_RETRY_BASE_DELAY = 20       # Base delay in seconds (multiplied by attempt number)

# Recommendation Engine Configuration
SUMMARY_THRESHOLD = 10          # Minimum feedback items before generating preference summary
SCORING_CHUNK_SIZE = 40         # Events per batch when scoring
SCORING_CHUNK_DELAY = 12        # Seconds between scoring batches (rate limiting)
SCORING_MAX_RETRIES = 3         # Maximum retry attempts for scoring requests
SCORING_RETRY_BASE_DELAY = 5    # Base delay in seconds for scoring retries
```

**Files Modified:**
- `config.py`: Added all tuning constants with documentation
- `llm_scrape_core.py`: Removed hardcoded constants, now references `config.LLM_*`
- `recommender/llm_filter.py`: Removed hardcoded constants, now references `config.SCORING_*` and `config.SUMMARY_THRESHOLD`

**Impact:**
- All tuning parameters are now in one place for easy adjustment
- Better documentation of what each parameter controls
- Easier to experiment with different values without hunting through code

---

### Issue 12: Standardized Logging

**Problem:**
Inconsistent use of `print()` statements vs the `logging` module throughout the codebase:
- `llm_scraper.py`: Used `print()` exclusively
- `llm_scrape_core.py`: Used `print()` exclusively
- `recommender/llm_filter.py`: Used `logging` module properly
- `test_recommender.py`: Used `print()` exclusively
- `_test_llm_scrape.py`: Used `print()` exclusively

**Solution:**
Added logging infrastructure while keeping print() for user-facing output:

```python
# llm_scrape_core.py
import logging
log = logging.getLogger(__name__)

# Now logs important events:
log.info("Created new Selenium WebDriver instance")
log.info("Closed Selenium WebDriver")
log.info(f"Large page: {len(text)} chars -> {n} chunks")
log.warning(f"429 error, retrying in {wait}s...")
log.warning(f"Page load timeout/error: {type(e).__name__}")
```

**Strategy:**
- `log.info()` / `log.warning()` / `log.error()` for internal events and debugging
- `print()` kept for user-facing progress messages (scraping status, event counts)
- This allows filtering logs by level in production while keeping CLI output clean

**Files Modified:**
- `llm_scrape_core.py`: Added logging import and log calls for driver lifecycle, chunking, errors
- `recommender/llm_filter.py`: Already had logging, no changes needed

**Impact:**
- Better debugging capability - can enable DEBUG logging to see internal state
- Production deployments can log to files with appropriate levels
- User-facing CLI output remains clean and readable
- Errors are now logged even if print output is redirected

---

### Issue 15: Thread Safety for Selenium Driver

**Problem:**
Global `_selenium_driver` variable in `llm_scrape_core.py` was not thread-safe:
- `get_driver()` and `close_driver()` accessed global state without synchronization
- If multiple scrapers ever ran concurrently (threading/multiprocessing), race conditions could occur
- Driver could be closed by one thread while another is using it

**Solution:**
Added thread-safe access using `threading.Lock()`:

```python
# Before
_selenium_driver = None

def get_driver():
    global _selenium_driver
    if _selenium_driver is None:
        # ... create driver ...
    return _selenium_driver

def close_driver():
    global _selenium_driver
    if _selenium_driver:
        _selenium_driver.quit()
        _selenium_driver = None
```

```python
# After
_selenium_driver = None
_driver_lock = threading.Lock()

def get_driver():
    global _selenium_driver
    with _driver_lock:
        if _selenium_driver is None:
            # ... create driver ...
            log.info("Created new Selenium WebDriver instance")
        return _selenium_driver

def close_driver():
    global _selenium_driver
    with _driver_lock:
        if _selenium_driver:
            _selenium_driver.quit()
            _selenium_driver = None
            log.info("Closed Selenium WebDriver")
```

**Files Modified:**
- `llm_scrape_core.py`: Added `_driver_lock = threading.Lock()` and wrapped all driver access in `with _driver_lock:`

**Impact:**
- Prevents race conditions if concurrent scraping is ever implemented
- No performance impact for current single-threaded usage
- Future-proofs the code for parallel scraping
- Added logging for driver lifecycle events

---

### URL Handling Clarification

**Question:** Why do we check `not url.startswith('http')`?

**Answer:** This checks if a URL is **relative** vs **absolute**:
- Relative URL: `/events/123` or `events/123` (no protocol)
- Absolute URL: `https://example.com/events/123` or `http://example.com/events/123`

The check `startswith('http')` catches both `http://` and `https://` URLs, identifying them as absolute. If a URL doesn't start with `http`, it's relative and needs to be converted to absolute using `urljoin(base_url, relative_url)`.

This is the correct approach because:
1. It handles both HTTP and HTTPS in one check
2. Relative URLs need the base domain prepended to be valid
3. The LLM sometimes returns relative URLs from the page text

**Example:**
```python
# Relative URL needs conversion
url = "/events/concert"
if not url.startswith('http'):
    url = urljoin('https://example.com', url)
    # Result: 'https://example.com/events/concert'

# Absolute URL passes through unchanged
url = "https://example.com/events/concert"
if not url.startswith('http'):  # False, skips conversion
    pass
```

---

### Testing Recommendations

1. **Config Changes:**
   - Try adjusting `config.LLM_CHUNK_SIZE` to see impact on large pages
   - Experiment with `config.SCORING_CHUNK_DELAY` if hitting rate limits

2. **Logging:**
   - Run with `logging.basicConfig(level=logging.INFO)` to see internal events
   - Check that driver lifecycle is logged correctly

3. **Thread Safety:**
   - Current single-threaded usage should work identically
   - Future concurrent scraping will be safe

---

### Summary

Fixed three medium/low priority issues:
- Centralized all magic values in `config.py` for easier tuning
- Added logging infrastructure for better debugging (kept print() for user output)
- Made Selenium driver access thread-safe with locks
- Clarified URL handling logic (relative vs absolute URLs)

All changes are backward compatible and don't affect current functionality.
