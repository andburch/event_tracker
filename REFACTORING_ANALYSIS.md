# Pagination Refactoring Analysis
## Phoenix Events Recommender - llm_scraper.py

**Date:** 2026-03-31  
**Status:** Planning Phase - NO CODE CHANGES YET  
**Objective:** Eliminate ~300 lines of duplicated pagination code in `scrape_and_save()`

---

## Current State Analysis

### Pagination Patterns Identified

The `scrape_and_save()` function contains 8 special-case pagination handlers:

1. **dirtydrummer** - Multi-month calendar URLs (`?month=MM-YYYY`, 3 months)
2. **chandler_lib** - BiblioCommons pagination (`&page=N`, 1-indexed)
3. **mesa** - Regex URL substitution (`pageindex=N`, 1-indexed)
4. **azmnh** - JavaScript button clicks (CSS selector, style check)
5. **phoenix** - JavaScript button clicks (different selector)
6. **tca/gilbert** - Calendar month URLs (`/-curm-M/-cury-YYYY/`) with date injection
7. **chandler** - Zero-indexed query params (`?page=N`, 0-indexed)
8. **default** - LLM-detected `next_page_url` from page content

### Code Duplication Metrics

- **Total lines in special cases:** ~260 lines
- **Duplicated structure per case:** ~30-40 lines each
- **Common operations:**
  - Loop through pages/months
  - Fetch HTML (selenium or requests)
  - Clean HTML with `clean_html()`
  - Call `ask_llm()` to extract events
  - Collect events into `all_events` list
  - Error handling (try/except, success flags)
  - Sleep between requests (rate limiting)

### Sites Using Each Pattern

| Pattern | Sites | Count |
|---------|-------|-------|
| LLM-detected (default) | fibber, yuccatap, rak, scottsdale, tempe_lib, chandler_center, mesa_arts, scottsdale_arts, asu_kerr, downtown_tempe, dbg, odysea, hale_theatre | 13 |
| Multi-month calendar | dirtydrummer | 1 |
| BiblioCommons | chandler_lib | 1 |
| Regex URL | mesa | 1 |
| JS button (azmnh) | azmnh | 1 |
| JS button (phoenix) | phoenix | 1 |
| Calendar month + injection | tca, gilbert | 2 |
| Zero-indexed query | chandler | 1 |

**Key Insight:** 13 out of 21 sites (62%) use the default LLM-detected pagination successfully!

---

## APPROACH 1: Strategy Pattern with Pagination Handlers

### Core Concept

Use the **Strategy Pattern** to encapsulate each pagination behavior as a separate handler class. Each handler implements a common `PaginationStrategy` interface with a `paginate()` generator method that yields pages.

### Architecture

```python
# pagination_strategies.py

from abc import ABC, abstractmethod
from typing import Iterator
from dataclasses import dataclass

@dataclass
class PageData:
    """Container for a single page's data"""
    html: str
    url: str
    page_number: int
    metadata: dict = None

class PaginationStrategy(ABC):
    """Base interface for all pagination strategies"""
    
    @abstractmethod
    def paginate(self, start_url: str, use_selenium: bool, 
                 wait: int, max_pages: int) -> Iterator[PageData]:
        """Yield PageData objects for each page to scrape"""
        pass

# Concrete Strategies
class QueryParamPagination(PaginationStrategy):
    """Handles ?page=N, &page=N, pageindex=N patterns"""
    def __init__(self, param_name: str, start_index: int = 1, 
                 param_format: str = "append"):
        self.param_name = param_name
        self.start_index = start_index
        self.param_format = param_format

class MonthUrlPagination(PaginationStrategy):
    """Generate URLs for multiple months"""
    def __init__(self, url_template: str, num_months: int = 3):
        self.url_template = url_template
        self.num_months = num_months

class ClickButtonPagination(PaginationStrategy):
    """Click next button for JS-based pagination"""
    def __init__(self, next_button_selector: str, stop_condition_check=None):
        self.selector = next_button_selector
        self.stop_check = stop_condition_check

class CalendarMonthPagination(PaginationStrategy):
    """Month-view calendar with date injection"""
    def __init__(self, base_url: str, url_pattern: str, num_months: int = 3):
        self.base_url = base_url
        self.url_pattern = url_pattern
        self.num_months = num_months

class LLMDetectedPagination(PaginationStrategy):
    """Let LLM find next page URL from content (default)"""
    pass

# Strategy Registry
PAGINATION_STRATEGIES = {
    'chandler_lib': QueryParamPagination('page', 1, 'ampersand'),
    'mesa': QueryParamPagination('pageindex', 1, 'regex'),
    'chandler': QueryParamPagination('page', 0, 'append'),
    'dirtydrummer': MonthUrlPagination('https://...?month={month_year}'),
    'azmnh': ClickButtonPagination('li.nextLink a.page-link', ...),
    'phoenix': ClickButtonPagination('a.cmp-searchCustom__pagination-btn', ...),
    'tca': CalendarMonthPagination('https://...', '/-curm-{month}/-cury-{year}'),
    'gilbert': CalendarMonthPagination('https://...', '/-curm-{month}/-cury-{year}'),
}
```

### Refactored Main Loop

```python
def scrape_and_save(key, name, start_url, use_selenium, wait, max_pages, session):
    all_events = []
    strategy = get_pagination_strategy(key)  # Get or default to LLM
    
    try:
        for page_data in strategy.paginate(start_url, use_selenium, wait, max_pages):
            print(f"  Page {page_data.page_number}: {page_data.url[:80]}")
            text = clean_html(page_data.html)
            result = ask_llm(text, current_url=page_data.url, site_hint=name)
            all_events.extend(result.get('events', []))
            
            if not result.get('events') and should_stop_on_empty(strategy):
                break
    except Exception as e:
        # Error handling
        pass
    
    # Save to DB (unchanged)
    return save_events_to_db(session, all_events, key, start_url)
```

### Adding a New Site

```python
# New site with &offset=N pagination
PAGINATION_STRATEGIES['new_site'] = QueryParamPagination(
    param_name='offset',
    start_index=0,
    param_format='ampersand'
)
```

### Pros

- ✅ Clear separation of concerns - pagination logic isolated
- ✅ Easy to test - each strategy independently testable
- ✅ Highly extensible - new pagination = new strategy class
- ✅ Type-safe - clear interfaces with type hints
- ✅ Reusable - `QueryParamPagination` handles 3 different sites
- ✅ No duplication - main loop is ~30 lines total
- ✅ Incremental migration - can migrate one site at a time

### Cons

- ❌ More files - requires new `pagination_strategies.py` module
- ❌ Learning curve - developers need to understand Strategy Pattern
- ❌ Abstraction overhead - simple sites require understanding the system
- ❌ Generator complexity - LLM-detected uses bidirectional generator
- ❌ Selenium lifecycle - click strategies need careful driver management
- ❌ Over-engineering - 6 classes for 6 edge cases when 13 sites work fine with LLM

### Complexity Estimate

- **Lines of code:** ~400 lines total
  - `pagination_strategies.py`: ~350 lines (8 strategy classes + factory)
  - `llm_scraper.py`: ~50 lines (unified scrape_and_save)
  - Net: ~300 → ~400 lines (but much better organized)
- **Files to create/modify:**
  - Create: `pagination_strategies.py`
  - Modify: `llm_scraper.py` (replace scrape_and_save)
- **Migration difficulty:** Medium
  - Test each strategy thoroughly
  - Selenium strategies need careful testing
  - Can migrate one site at a time
- **Risk level:** Medium
  - Bugs are isolated per strategy
  - Main risk is Selenium driver management

---

## APPROACH 2: Configuration-Driven Pipeline with Composable Steps

### Core Concept

Treat pagination as a **declarative configuration** rather than code. Each site defines a JSON-like configuration specifying a sequence of steps (fetch → transform → extract → navigate). The scraper engine interprets these configurations and executes steps in order.

### Architecture

```python
# pagination_config.py

from dataclasses import dataclass, field
from typing import Literal

@dataclass
class PaginationConfig:
    """Declarative configuration for site pagination"""
    
    # URL Generation
    url_generator: Literal['query_param', 'month_range', 'calendar_month', 'static']
    url_params: dict = field(default_factory=dict)
    
    # Fetch Method
    fetch_method: Literal['requests', 'selenium', 'selenium_click']
    fetch_params: dict = field(default_factory=dict)
    
    # HTML Transformation
    transformers: list[dict] = field(default_factory=list)
    
    # Navigation
    navigation: Literal['url_generator', 'click_button', 'llm_detected']
    navigation_params: dict = field(default_factory=dict)
    
    # Stop Conditions
    stop_on_empty: bool = True
    stop_on_duplicate_url: bool = True
    max_pages: int = 10

# Configuration Database
SITE_CONFIGS = {
    'chandler_lib': PaginationConfig(
        url_generator='query_param',
        url_params={'param': 'page', 'start': 1, 'format': '&page={n}'},
        fetch_method='selenium',
        fetch_params={'wait': 5},
        transformers=[{'type': 'clean_html'}],
        navigation='url_generator',
        stop_on_empty=True,
        max_pages=10,
    ),
    
    'azmnh': PaginationConfig(
        url_generator='static',
        fetch_method='selenium_click',
        fetch_params={'wait': 5},
        transformers=[{'type': 'clean_html'}],
        navigation='click_button',
        navigation_params={
            'selector': 'li.nextLink a.page-link',
            'stop_check': 'parent_hidden',
        },
        max_pages=10,
    ),
}
```

```python
# pagination_engine.py

class PaginationEngine:
    """Executes pagination based on declarative configuration"""
    
    def __init__(self, config: PaginationConfig):
        self.config = config
    
    def scrape(self, start_url: str, site_name: str) -> list[dict]:
        """Execute the configured pagination pipeline"""
        all_events = []
        
        # Create components from config
        url_gen = self._create_url_generator(start_url)
        fetcher = self._create_fetcher()
        navigator = self._create_navigator()
        
        for page_num, (url, metadata) in enumerate(url_gen, 1):
            if page_num > self.config.max_pages:
                break
            
            # STEP 1: Fetch
            html = fetcher.fetch(url, metadata)
            
            # STEP 2: Transform
            text = self._apply_transformers(html, metadata)
            
            # STEP 3: Extract via LLM
            result = ask_llm(text, current_url=url, site_hint=site_name)
            all_events.extend(result.get('events', []))
            
            # STEP 4: Navigate
            if not navigator.navigate(result):
                break
        
        return all_events
```

### Refactored Main Loop

```python
def scrape_and_save(key, name, start_url, use_selenium, wait, max_pages, session):
    # Get config or use default
    config = SITE_CONFIGS.get(key, SITE_CONFIGS['default'])
    
    # Override with runtime params
    config.max_pages = max_pages
    config.fetch_params['wait'] = wait
    
    # Execute pipeline
    engine = PaginationEngine(config)
    all_events = engine.scrape(start_url, name)
    
    # Save to DB (unchanged)
    return save_events_to_db(session, all_events, key, start_url)
```

### Adding a New Site

```python
# Just add configuration - NO CODE!
SITE_CONFIGS['new_site'] = PaginationConfig(
    url_generator='query_param',
    url_params={'param': 'offset', 'start': 0, 'format': '&offset={n}'},
    fetch_method='requests',
    transformers=[{'type': 'clean_html'}],
    navigation='url_generator',
    stop_on_empty=True,
    max_pages=20,
)
```

### Pros

- ✅ Zero code for new sites - just add configuration
- ✅ Easy to understand - configurations are self-documenting
- ✅ Easy to modify - change behavior without touching code
- ✅ Testable - can validate configs, test engine separately
- ✅ Portable - configs could be JSON/YAML files
- ✅ Visual tools possible - could build GUI config editor
- ✅ Centralized logic - all pagination logic in one engine

### Cons

- ❌ Limited flexibility - hard to handle truly unique pagination
- ❌ Configuration complexity - complex sites have complex configs
- ❌ Debugging harder - errors happen in engine, not site-specific code
- ❌ Learning curve - need to learn configuration schema
- ❌ More abstraction layers - URL gen → fetcher → transformer → navigator
- ❌ Potential over-engineering - simple sites still need full config
- ❌ Redundancy - builds a second interpreter on top of LLM interpreter

### Complexity Estimate

- **Lines of code:** ~600 lines total
  - `pagination_config.py`: ~200 lines (configs for 8 sites)
  - `pagination_engine.py`: ~300 lines (engine + component factories)
  - `url_generators.py`: ~100 lines (generator implementations)
  - `llm_scraper.py`: ~20 lines (simplified scrape_and_save)
  - Net: ~300 → ~600 lines (but most is reusable infrastructure)
- **Files to create/modify:**
  - Create: `pagination_config.py`, `pagination_engine.py`, `url_generators.py`, `fetchers.py`, `navigators.py`
  - Modify: `llm_scraper.py` (replace scrape_and_save)
- **Migration difficulty:** High
  - Need to build entire engine infrastructure first
  - All sites migrate at once (or need compatibility layer)
  - Complex testing required for engine
- **Risk level:** High
  - Big bang migration
  - Engine bugs affect all sites
  - Hard to debug configuration issues

---

## CRITICAL REVIEW: Senior Architect Perspective

### Key Findings

**Both approaches are over-engineered for this problem.**

The real insight: **Your LLM already handles pagination detection beautifully for 13 out of 21 sites (62%)**. You only need explicit pagination logic for edge cases where the LLM can't see controls:

1. **JavaScript buttons** (azmnh, phoenix) - LLM can't see onclick handlers
2. **Explicit URL patterns** (chandler, chandler_lib, mesa) - LLM can't infer zero-indexing or regex patterns
3. **Calendar navigation** (dirtydrummer, tca, gilbert) - LLM needs help with month iteration and date injection

### Architecture Concerns

**Approach 1 (Strategy Pattern):**
- ❌ Fights against your LLM's pagination detection capability
- ❌ Creates 6 classes for 6 edge cases (over-engineering)
- ❌ Rigid with hybrid pagination (what if a site uses LLM + explicit URLs?)
- ✅ Incremental migration possible
- ✅ Bugs are isolated

**Approach 2 (Config-Driven):**
- ❌ Builds a second interpreter on top of your LLM interpreter (redundant)
- ❌ DSL creep - configurations become mini-programs
- ❌ Debugging hell - errors in engine affect all sites
- ❌ Big bang migration required
- ✅ Zero code for new sites (if they fit the patterns)

### Real-World Scenarios

**What if a site needs custom HTML preprocessing?**
- Approach 1: Add preprocessing to strategy class (flexible)
- Approach 2: Add transformer to config (limited to predefined transformers)
- **Winner:** Approach 1

**What if pagination logic changes mid-scrape?**
- Approach 1: Hard to handle (strategy is fixed at start)
- Approach 2: Hard to handle (config is fixed at start)
- **Winner:** Neither (both fail this scenario)

**What if we need authentication?**
- Approach 1: Add auth to strategy or fetcher
- Approach 2: Add auth to fetch_params config
- **Winner:** Tie (both can handle it)

**What if we need rate limiting per site?**
- Approach 1: Add rate limiter to strategy
- Approach 2: Add rate_limit to config
- **Winner:** Tie (both can handle it)

### Hidden Risks

**Neither approach addresses your real risks:**
1. **Akamai evolution** - Bot detection gets smarter, breaks Selenium
2. **LLM cost spikes** - Groq rate limits or pricing changes
3. **Authentication** - Sites add login requirements
4. **Dynamic content** - Sites move to React/Vue with client-side rendering

---

## RECOMMENDED APPROACH: Hybrid Minimal Refactoring

### Core Concept

Extract only the 3 edge cases that need explicit handling into simple generator functions. Keep LLM-based pagination as the default. Add an optional `pagination_override` field to the `SITES` dict.

### Architecture

```python
# pagination_helpers.py (NEW FILE - ~100 lines)

def generate_month_urls(base_url: str, num_months: int = 3):
    """Generate URLs for multi-month calendar scraping"""
    base_date = datetime.now()
    for i in range(num_months):
        month_date = base_date + timedelta(days=30*i)
        month_str = month_date.strftime('%m-%Y')
        yield f"{base_url}?month={month_str}", {'month': month_date}

def generate_query_param_urls(base_url: str, param: str, start: int, max_pages: int):
    """Generate URLs with query parameter pagination"""
    for i in range(start, start + max_pages):
        if '?' in base_url:
            yield f"{base_url}&{param}={i}", {'page': i}
        else:
            yield f"{base_url}?{param}={i}", {'page': i}

def click_pagination(driver, selector: str, max_pages: int, stop_check=None):
    """Handle JavaScript button click pagination"""
    for page_num in range(1, max_pages + 1):
        yield driver.page_source, {'page': page_num}
        
        # Try to click next
        try:
            if stop_check and stop_check(driver):
                break
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(3)
        except:
            break
```

```python
# sources.py (MODIFY - add pagination_override field)

SITES = {
    'dirtydrummer': (
        'Dirty Drummer',
        'https://www.thedirtydrummer.com/events',
        True, 8, 5, 'Squarespace',
        ('#fdf2f8', '#9d174d', '#500724'),
        {'type': 'month_urls', 'num_months': 3},  # NEW: pagination override
    ),
    'chandler': (
        'City of Chandler',
        'https://www.chandleraz.gov/events-result',
        True, 5, 10, '?page=N zero-indexed pagination',
        ('#fce7f3', '#db2777', '#831843'),
        {'type': 'query_param', 'param': 'page', 'start': 0},  # NEW
    ),
    'azmnh': (
        'AZ Museum of Natural History',
        'https://www.azmnh.org/azmnh-events',
        True, 5, 5, '',
        ('#ecfdf5', '#10b981', '#064e3b'),
        {'type': 'click', 'selector': 'li.nextLink a.page-link'},  # NEW
    ),
    # ... other sites have None for pagination_override (use LLM default)
}
```

```python
# llm_scraper.py (MODIFY - simplified scrape_and_save)

def scrape_and_save(key, name, start_url, use_selenium, wait, max_pages, session):
    all_events = []
    site_config = SITES[key]
    pagination_override = site_config[7] if len(site_config) > 7 else None
    
    # Use pagination override if specified, otherwise use LLM default
    if pagination_override:
        page_generator = get_pagination_generator(
            pagination_override, start_url, use_selenium, wait, max_pages
        )
    else:
        # Default: LLM-detected pagination (existing code)
        page_generator = llm_pagination_generator(
            start_url, use_selenium, wait, max_pages
        )
    
    # Unified scraping loop
    for page_num, (html, url, metadata) in enumerate(page_generator, 1):
        print(f"  Page {page_num}: {url[:80]}")
        text = clean_html(html)
        
        # Apply any special transformers (e.g., date injection for calendars)
        if metadata and 'transform' in metadata:
            text = apply_transform(text, metadata['transform'])
        
        result = ask_llm(text, current_url=url, site_hint=name)
        all_events.extend(result.get('events', []))
        
        if not result.get('events') and pagination_override:
            break  # Stop on empty for explicit pagination
    
    # Save to DB (unchanged)
    return save_events_to_db(session, all_events, key, start_url)
```

### Migration Path

**Phase 1: Extract helpers (1 hour)**
- Create `pagination_helpers.py` with 3 generator functions
- Test each generator independently

**Phase 2: Add override field (30 minutes)**
- Modify `SITES` dict to add 8th field (pagination_override)
- Set to `None` for all sites initially (no behavior change)

**Phase 3: Migrate edge cases (1 hour)**
- Add overrides for dirtydrummer, chandler, chandler_lib, mesa, azmnh, phoenix, tca, gilbert
- Test each site individually
- Keep old code as fallback during testing

**Phase 4: Cleanup (30 minutes)**
- Remove old special-case code blocks
- Update documentation

**Total effort: 3 hours**

### Pros

- ✅ Minimal code changes (~100 new lines, ~200 deleted lines)
- ✅ Incremental migration - one site at a time
- ✅ Easy rollback - just remove override field
- ✅ Preserves LLM pagination for 13 sites that work fine
- ✅ Simple to understand - just 3 helper functions
- ✅ Low risk - changes are isolated
- ✅ No new abstractions to learn

### Cons

- ❌ Still some duplication in generator functions
- ❌ Not as "clean" as Strategy Pattern
- ❌ Pagination logic split between helpers and main loop

### Complexity Estimate

- **Lines of code:** ~100 new, ~200 deleted = net -100 lines
- **Files to create/modify:**
  - Create: `pagination_helpers.py` (~100 lines)
  - Modify: `sources.py` (add 8th field to SITES)
  - Modify: `llm_scraper.py` (simplify scrape_and_save to ~80 lines)
- **Migration difficulty:** Low
  - Can test each site individually
  - Easy to rollback
  - No big bang migration
- **Risk level:** Low
  - Changes are isolated
  - Existing LLM pagination unchanged
  - Fallback to old code during testing

---

## Final Recommendation

**For this codebase, I recommend the HYBRID MINIMAL REFACTORING approach** because:

1. **Right-sized solution** - Addresses the actual problem (3 edge cases) without over-engineering
2. **Preserves what works** - Keeps LLM pagination for 13 sites that work fine
3. **Low risk** - Incremental migration, easy rollback, isolated changes
4. **Quick implementation** - 3 hours vs 2-3 days for Strategy Pattern
5. **Easy to understand** - No new patterns to learn, just helper functions
6. **Future-proof** - Can always upgrade to Strategy Pattern later if needed

### When to Consider Strategy Pattern

Upgrade to Approach 1 (Strategy Pattern) if:
- You add 10+ new sites with unique pagination patterns
- You need to unit test pagination logic extensively
- Multiple developers are working on the scraper
- You're building a scraping framework for others to use

### When to Consider Config-Driven

Upgrade to Approach 2 (Config-Driven) if:
- Non-developers need to add new sites
- You're storing site configs in a database
- You want to build a visual configuration tool
- You're adding 20+ sites per month

For a personal project with 21 sites and occasional additions, the hybrid approach provides the best balance of simplicity, maintainability, and effort.

---

## Next Steps

1. **Review this analysis** with the user
2. **Get approval** on the chosen approach
3. **Create a spec** for the refactoring work
4. **Implement in phases** with testing at each step
5. **Document** the new pagination system

**DO NOT PROCEED WITH CODE CHANGES UNTIL USER APPROVES THE APPROACH.**
