# How to Add a New Event Scraper

This guide shows you how to add a new event source to the Phoenix Events Recommender. The entire process involves editing ONE file (`sources.py`) and takes about 5-10 minutes.

## Quick Start

1. Open `sources.py`
2. Add a new entry to the `SITES` dict
3. Run `python llm_scraper.py <your_key>` to test
4. Done!

## Understanding the SITES Dict

Every scraper is defined by a single entry in the `SITES` dictionary in `sources.py`:

```python
'key': (
    'Display Name',           # How it appears in the UI
    'https://example.com',    # Starting URL
    True,                     # use_selenium (True/False)
    5,                        # wait_secs (seconds to wait after page load)
    5,                        # max_pages (safety limit)
    'Optional note',          # Note about quirks/issues
    ('#bg', '#border', '#text'),  # Color scheme for calendar
    pagination_config,        # Pagination configuration (or None)
),
```

## Pagination Types

The system supports 5 pagination patterns. Choose the one that matches your site:

### 1. LLM Pagination (Default)

The LLM automatically extracts the "Next" button URL from the page content.

**When to use:** Most sites with standard pagination (numbered pages, "Next" buttons, "Load More" links)

**Config:**
```python
None  # or {'type': 'llm'}
```

**Example sites:** fibber, rak, scottsdale, tempe_lib

**Full example:**
```python
'mysite': (
    'My Event Site',
    'https://mysite.com/events',
    True,  # Needs JavaScript
    5,     # Wait 5 seconds
    5,     # Max 5 pages
    '',
    ('#fff7ed', '#c2410c', '#7c2d12'),
    None,  # Default LLM pagination
),
```

---

### 2. Multi-Month Pagination

Generates URLs for multiple consecutive months.

**When to use:** Calendar sites that show one month per page with month/year in the URL

**Config:**
```python
{
    'type': 'multi_month',
    'months': 3,  # Number of months to scrape
    'url_template': 'https://example.com/events?month={month:02d}-{year}'
}
```

**Example sites:** dirtydrummer

**Full example:**
```python
'dirtydrummer': (
    'Dirty Drummer',
    'https://www.thedirtydrummer.com/events',
    True, 8, 5, 'Squarespace',
    ('#fdf2f8', '#9d174d', '#500724'),
    {
        'type': 'multi_month',
        'months': 3,
        'url_template': 'https://www.thedirtydrummer.com/events?view=calendar&month={month:02d}-{year}'
    },
),
```

---

### 3. URL Parameter Pagination

Increments a URL parameter for each page (?page=1, ?page=2, etc.)

**When to use:** Sites with explicit page numbers in the URL

**Config:**
```python
{
    'type': 'url_param',
    'param_name': 'page',      # Parameter to increment
    'start_index': 1,          # Starting value (0 for zero-indexed)
    'stop_on_empty': True      # Stop if page has no events
}
```

**Example sites:** chandler (zero-indexed), mesa (pageindex=N), chandler_lib (&page=N)

**Full examples:**
```python
# Zero-indexed pagination (?page=0, ?page=1, ...)
'chandler': (
    'City of Chandler',
    'https://www.chandleraz.gov/events-result',
    True, 5, 10, '?page=N zero-indexed pagination',
    ('#fce7f3', '#db2777', '#831843'),
    {
        'type': 'url_param',
        'param_name': 'page',
        'start_index': 0,  # Zero-indexed!
        'stop_on_empty': True
    },
),

# Custom parameter name (pageindex=1, pageindex=2, ...)
'mesa': (
    'City of Mesa',
    'https://www.mesaaz.gov/Events-directory?pageindex=1',
    True, 6, 5, 'pageindex=N pagination',
    ('#ede9fe', '#7c3aed', '#4c1d95'),
    {
        'type': 'url_param',
        'param_name': 'pageindex',
        'start_index': 1,
        'stop_on_empty': True
    },
),
```

---

### 4. JavaScript Button Pagination

Clicks "Next" buttons in JavaScript-heavy sites (no URL change).

**When to use:** Sites where pagination happens entirely in JavaScript without changing the URL

**Config:**
```python
{
    'type': 'js_button',
    'button_selector': 'a.next-button',  # CSS selector for next button
    'disabled_check': 'attribute',       # How to detect last page
    'scroll_before_click': True,         # Scroll before clicking
    'wait_after_click': 3                # Seconds to wait after click
}
```

**disabled_check options:**
- `'attribute'`: Check for `disabled` attribute (default)
- `'style'`: Check for `display:none` in parent element's style
- `'class'`: Check for `disabled` class

**Example sites:** phoenix, azmnh

**Full examples:**
```python
# Standard button with disabled attribute
'phoenix': (
    'City of Phoenix',
    'https://www.phoenix.gov/calendar.html',
    True, 6, 5, '',
    ('#dbeafe', '#2563eb', '#1e3a8a'),
    {
        'type': 'js_button',
        'button_selector': 'a.cmp-searchCustom__pagination-btn',
        'disabled_check': 'attribute',
        'scroll_before_click': True,
        'wait_after_click': 3
    },
),

# Button with display:none check
'azmnh': (
    'AZ Museum of Natural History',
    'https://www.azmnh.org/azmnh-events',
    True, 5, 5, '',
    ('#ecfdf5', '#10b981', '#064e3b'),
    {
        'type': 'js_button',
        'button_selector': 'li.nextLink a.page-link',
        'disabled_check': 'style',  # Checks parent li for display:none
        'scroll_before_click': False,
        'wait_after_click': 3
    },
),
```

---

### 5. Calendar Grid Pagination

Month-view calendar with date injection for LLM context.

**When to use:** Calendar grid layouts where day numbers appear without month context

**Config:**
```python
{
    'type': 'calendar_grid',
    'months': 3,
    'url_template': 'https://example.com/calendar/-curm-{month}/-cury-{year}',
    'inject_dates': True  # Inject full dates into text
}
```

**Example sites:** tca, gilbert

**Full example:**
```python
'gilbert': (
    'City of Gilbert',
    'https://www.gilbertaz.gov/residents/calendar-month-view/',
    True, 15, 5, 'Akamai bot detection',
    ('#ffedd5', '#ea580c', '#7c2d12'),
    {
        'type': 'calendar_grid',
        'months': 3,
        'url_template': 'https://www.gilbertaz.gov/residents/calendar-month-view/-curm-{month}/-cury-{year}',
        'inject_dates': True
    },
),
```

---

## Step-by-Step: Adding a New Site

### Step 1: Find the Events Page

Navigate to the site's events page in your browser. This will be your `start_url`.

### Step 2: Determine if Selenium is Needed

**Use `use_selenium=False` if:**
- Events are visible immediately when you view the page source (Ctrl+U)
- No "Loading..." spinners or dynamic content

**Use `use_selenium=True` if:**
- Events load after the page loads (JavaScript-rendered)
- You see "Loading..." or skeleton screens
- Pagination requires clicking buttons

### Step 3: Choose a Pagination Type

Click through a few pages and observe:
- Does the URL change? → url_param or llm
- Does it stay the same? → js_button
- Is it a monthly calendar? → multi_month or calendar_grid
- Standard "Next" links? → llm (default)

### Step 4: Pick a Color Scheme

Choose colors that match the site's branding. Use a color picker tool to get hex codes.

Format: `(background, border, text)` - all as hex strings

### Step 5: Add to sources.py

Open `sources.py` and add your entry to the `SITES` dict:

```python
'mykey': (
    'My Site Name',
    'https://mysite.com/events',
    True,  # or False
    5,     # adjust wait time if needed
    5,     # max pages
    '',    # add notes if needed
    ('#ffffff', '#000000', '#333333'),  # your colors
    None,  # or your pagination config
),
```

### Step 6: Test

```bash
python llm_scraper.py mykey
```

Watch the output:
- Does it find events?
- Does pagination work?
- Any errors?

### Step 7: Adjust if Needed

Common adjustments:
- Increase `wait` if events don't load (try 8-10 for slow sites)
- Increase `max_pages` if you want more results
- Add `'scroll_passes': 15` to pagination config for infinite scroll sites
- Change pagination type if it's not working

---

## Troubleshooting

### "Access Denied" or "403 Forbidden"

The site has bot detection (Akamai/Cloudflare). Try:
1. Increase `wait` to 10-15 seconds
2. Add note: `'Akamai bot detection'`
3. The system already uses user-agent spoofing, so this should work

### No Events Found

1. Check if `use_selenium` should be True
2. Increase `wait` time
3. Check if the URL is correct
4. Look at the raw HTML output to see what the LLM is seeing

### Pagination Not Working

1. Try a different pagination type
2. For js_button: inspect the button in browser dev tools to get the correct selector
3. For url_param: check if it's zero-indexed (start_index=0)
4. For multi_month/calendar_grid: verify the URL template format

### Events Have Wrong Dates

For calendar grids, use `calendar_grid` type with `inject_dates: True` to add month context.

### Too Many API Errors

Reduce `max_pages` or add delays between pages (the system already has 2-3 second delays).

---

## Real-World Examples

### Simple Static Site
```python
'fibber': (
    'Fibber Magees',
    'https://www.fibbermageespub.com/fibber-magees-events',
    False,  # Static HTML, no JavaScript needed
    3,
    5,
    '',
    ('#fff7ed', '#c2410c', '#7c2d12'),
    None,  # LLM handles pagination automatically
),
```

### JavaScript-Heavy Site with Button Pagination
```python
'phoenix': (
    'City of Phoenix',
    'https://www.phoenix.gov/calendar.html',
    True,  # Needs JavaScript
    6,
    5,
    '',
    ('#dbeafe', '#2563eb', '#1e3a8a'),
    {
        'type': 'js_button',
        'button_selector': 'a.cmp-searchCustom__pagination-btn',
        'disabled_check': 'attribute',
        'scroll_before_click': True,
        'wait_after_click': 3
    },
),
```

### Monthly Calendar with URL Parameters
```python
'dirtydrummer': (
    'Dirty Drummer',
    'https://www.thedirtydrummer.com/events',
    True,
    8,
    5,
    'Squarespace',
    ('#fdf2f8', '#9d174d', '#500724'),
    {
        'type': 'multi_month',
        'months': 3,
        'url_template': 'https://www.thedirtydrummer.com/events?view=calendar&month={month:02d}-{year}'
    },
),
```

### Zero-Indexed Page Numbers
```python
'chandler': (
    'City of Chandler',
    'https://www.chandleraz.gov/events-result',
    True,
    5,
    10,
    '?page=N zero-indexed pagination',
    ('#fce7f3', '#db2777', '#831843'),
    {
        'type': 'url_param',
        'param_name': 'page',
        'start_index': 0,  # Starts at ?page=0
        'stop_on_empty': True
    },
),
```

---

## Testing Individual Scrapers

Use the test harness to debug without affecting the database:

```bash
# Test a scraper
python _test_llm_scrape.py mykey

# Test with raw HTML dump (for debugging)
python _test_llm_scrape.py mykey --dump

# List all available scrapers
python _test_llm_scrape.py list
```

---

## Best Practices

1. **Start Simple**: Try `None` (LLM pagination) first - it works for most sites
2. **Test Incrementally**: Add the site, test it, then adjust
3. **Document Quirks**: Use the `note` field to document issues for future reference
4. **Be Conservative**: Start with low `max_pages` (3-5) to avoid API quota issues
5. **Check the Health Dashboard**: Visit http://localhost:5000/health after scraping to see success rates

---

## Summary

Adding a new scraper is a 3-step process:

1. **Identify** the pagination pattern
2. **Add** one entry to `sources.py`
3. **Test** with `python llm_scraper.py <key>`

No code changes needed - just configuration!
