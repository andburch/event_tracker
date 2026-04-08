# How to Add a New Event Scraper

This guide shows you how to add a new event source to the Phoenix Events Recommender. The entire process involves editing **one file** (`sources.py`) and takes about 10-15 minutes.

## Quick Start

1. Open `sources.py`
2. Add an entry to the `SITES` dict
3. Add an entry to the `TRIM_PATTERNS` dict (directly below `SITES` in the same file)
4. Run `python llm_scraper.py <your_key>` to test
5. Done!

---

## Understanding the Two Configs Per Site

Every scraper requires **two entries** in `sources.py`:

### 1. `SITES` entry -- scraping configuration

```python
'key': (
    'Display Name',              # How it appears in the UI
    'https://example.com',       # Starting URL
    True,                        # use_selenium (True/False)
    5,                           # wait_secs (seconds to wait after page load)
    5,                           # max_pages (safety limit)
    'Optional note',             # Note about quirks/issues
    ('#bg', '#border', '#text'), # Color scheme for calendar chips
    pagination_config,           # Pagination configuration (or None)
),
```

### 2. `TRIM_PATTERNS` entry -- boilerplate removal

```python
'key': "last line of boilerplate text\n",
```

The trim pattern is a string that marks the **end** of the nav/filter boilerplate at the top of each page. Everything up to and including it gets stripped before text reaches the LLM. This reduces token usage and speeds up local models by **1.5-2.6x**.

Set to `None` only if the page opens directly with events (no boilerplate to remove).

---

## Step-by-Step: Adding a New Site

### Step 1: Identify the Events Page

Navigate to the site's events page. This is your `start_url`.

### Step 2: Determine Fetch Method

**Use `use_selenium=False` if** events are visible in raw page source (Ctrl+U in browser) -- no JavaScript needed.

**Use `use_selenium=True` if** events load dynamically, you see "Loading..." spinners, or pagination requires button clicks.

### Step 3: Choose a Pagination Type

Observe what happens as you page through results:

| What you see | Pagination type |
|---|---|
| URL changes with `?page=N` or similar | `url_param` |
| URL stays the same, JS button clicked | `js_button` |
| Monthly calendar, month in URL | `multi_month` or `calendar_grid` |
| "Next" link visible in page text | `None` (LLM default) |

See the **Pagination Types** section below for full config details.

### Step 4: Collect a Cleaned-Text Artifact

Before you can find the trim pattern, you need to see what the cleaned text looks like:

```bash
# Option A: collect for all sites (skips existing artifacts)
python3 _collect_artifacts.py

# Option B: fetch and clean just your new site
python3 debug_fetch.py <key>
python3 debug_clean.py <key>
# Artifact saved to: debug_artifacts/<key>/page_1_cleaned.txt
```

### Step 5: Find the Trim Pattern

Open the artifact and find where boilerplate ends and events begin:

```bash
head -200 debug_artifacts/<key>/page_1_cleaned.txt
```

Look for the last line of nav/filter/UI text before the first real event. Pick a **2-3 line span** that is:

- **UI-specific** -- a label, button, or structural element that won't appear in event titles or venue names
- **Month-independent** -- not a category name or event that could rotate out
- **Stable across pages** -- the same text appears on page 2, 3, etc.
- **Not too short** -- a single common word like "Go" or "All" will eventually false-match

**Verify it appears exactly once:**

```bash
python3 -c "
text = open('debug_artifacts/<key>/page_1_cleaned.txt').read()
pat = 'your chosen pattern here'
print(f'count: {text.count(pat)}')   # must be 1
idx = text.index(pat) + len(pat)
print('First 80 chars after trim:', repr(text[idx:idx+80]))
"
```

**Common pattern types and examples:**

| Situation | Good pattern | Why |
|---|---|---|
| Filter sidebar | Last 2-3 filter items | Specific enough, stable |
| Calendar grid header | Full day row: `\nSu\nMo\nTu\nWe\nTh\nFr\nSa\n` | 7-line sequence, very specific |
| "Reset filters" button | `\nReset all filters\n` | Unique UI label |
| Cookie consent wall | Section heading: `\nUPCOMING EVENTS & EXHIBITS\n` | Marks event section start |
| Minimal boilerplate | Nav items: `Page Title\nNav Link [/url]\n` | Structural, stable |

If there's genuinely no boilerplate (page starts with events), set to `None`.

### Step 6: Pick a Color Scheme

Format: `(background, border, text)` -- CSS hex strings matching the site's branding.

### Step 7: Add Both Entries to `sources.py`

```python
# In SITES dict:
'mykey': (
    'My Site Name',
    'https://mysite.com/events',
    True,   # or False
    5,      # adjust wait time as needed
    5,      # max pages
    '',     # add notes if quirky
    ('#ffffff', '#000000', '#333333'),
    None,   # or your pagination config
),

# In TRIM_PATTERNS dict (directly below SITES in sources.py):
'mykey': "\nLast filter item\nAnother line\n",
```

### Step 8: Test

```bash
python _test_llm_scrape.py mykey
```

Watch the output. Does it find events? Does pagination work?

---

## Pagination Types

### 1. LLM Pagination (Default)

The LLM automatically extracts the next page URL from page content.

**When to use:** Most sites with visible "Next" buttons or numbered page links.

```python
None  # or {'type': 'llm'}
```

**Example sites:** `fibber`, `rak`, `scottsdale`, `tempe_lib`, `chandler_center`

---

### 2. Multi-Month Pagination

Generates URLs for multiple consecutive months.

**When to use:** Calendar sites that show one month per URL.

```python
{
    'type': 'multi_month',
    'months': 3,
    'url_template': 'https://example.com/events?month={month:02d}-{year}'
}
```

**Example sites:** `dirtydrummer`

---

### 3. URL Parameter Pagination

Increments a URL parameter for each page.

**When to use:** Sites with `?page=N`, `&pageindex=N`, etc. in the URL.

```python
{
    'type': 'url_param',
    'param_name': 'page',   # parameter name to increment
    'start_index': 1,        # 0 for zero-indexed sites
}
```

**Example sites:** `chandler` (zero-indexed `?page=0`), `mesa` (`pageindex=1`), `chandler_lib` (`&page=1`)

---

### 4. JavaScript Button Pagination

Clicks a "Next" button in Selenium between pages (no URL change).

**When to use:** Sites where pagination is entirely JavaScript-driven.

```python
{
    'type': 'js_button',
    'button_selector': 'a.next-button',  # CSS selector for next button
    'disabled_check': 'attribute',        # 'attribute', 'style', or 'class'
    'scroll_before_click': True,
    'wait_after_click': 3
}
```

**`disabled_check` options:**
- `'attribute'` -- checks for `disabled` HTML attribute
- `'style'` -- checks parent element for `display:none`
- `'class'` -- checks for a `disabled` CSS class

**Example sites:** `phoenix`, `azmnh`, `az_worm_farm` (Acuity Scheduling widget — scraped via the direct `app.acuityscheduling.com/schedule.php?owner=…` URL, not the embedding page)

---

### 5. Calendar Grid Pagination

Month-view calendar where day numbers appear without month context. Injects full dates so the LLM understands them.

**When to use:** Grid calendars where you see bare numbers (1, 2, 3...) and need the LLM to know what month they belong to.

```python
{
    'type': 'calendar_grid',
    'months': 3,
    'url_template': 'https://example.com/calendar/-curm-{month}/-cury-{year}',
    'inject_dates': True
}
```

**Example sites:** `gilbert`, `tca` (both CivicPlus platform)

---

## Full Examples with Both Configs

### Simple Static Site

```python
# SITES:
'fibber': (
    'Fibber Magees',
    'https://www.fibbermageespub.com/fibber-magees-events',
    False, 3, 5, '',
    ('#fff7ed', '#c2410c', '#7c2d12'),
    None,
),

# TRIM_PATTERNS:
# Nav header is stable; don't key on category names -- they change
'fibber': "Upcoming Events\nCalender View [/menu-1]\n",
```

### Monthly Calendar

```python
# SITES:
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

# TRIM_PATTERNS:
# Full 7-day header row -- far more specific than just Fr/Sa alone
'dirtydrummer': "\nSu\nMo\nTu\nWe\nTh\nFr\nSa\n",
```

### CivicPlus Calendar Grid (City Sites)

```python
# SITES:
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

# TRIM_PATTERNS:
# Full day-of-week header row (appears exactly once, before the calendar grid)
'gilbert': "\nSunday\nMonday\nTuesday\nWednesday\nThursday\nFriday\nSaturday\n",
```

### Large Boilerplate (Cookie Wall)

```python
# SITES:
'dbg': (
    'Desert Botanical Garden',
    'https://www.dbg.org/events/',
    True, 10, 1, 'Single page, no per-event URLs',
    ('#f0fdf4', '#22c55e', '#14532d'),
    None,
),

# TRIM_PATTERNS:
# Cookie consent manager is ~1000 lines; cut at the events section heading
'dbg': "\nUPCOMING EVENTS & EXHIBITS\n",
```

### Zero-Indexed URL Pagination

```python
# SITES:
'chandler': (
    'City of Chandler',
    'https://www.chandleraz.gov/events-result',
    True, 5, 10, '?page=N zero-indexed pagination',
    ('#fce7f3', '#db2777', '#831843'),
    {
        'type': 'url_param',
        'param_name': 'page',
        'start_index': 0,
    },
),

# TRIM_PATTERNS:
# 3-line sequence at end of the location filter list + submit button.
# More robust than just "\nGo\n" (single common word).
'chandler': "\nWindmills West Park\nWinn Park\nGo\n",
```

---

## Troubleshooting

### "Access Denied" or 403

Bot detection (Akamai/Cloudflare). Try:
1. Increase `wait` to 10-15 seconds
2. Add note: `'Akamai bot detection'`

### No Events Found

1. Check if `use_selenium` should be `True`
2. Increase `wait` time
3. Use `debug_clean.py <key>` to see what text the LLM actually receives after trimming
4. Use `debug_llm.py <key> --dry-run` to inspect the full prompt

### Trim Pattern Not Working

1. Check the pattern appears exactly once: `python3 -c "print(open('debug_artifacts/<key>/page_1_cleaned.txt').read().count('your pattern'))"`
2. Watch for encoding issues -- copy the text from the artifact, don't type it manually
3. Check the trim is being applied: `debug_clean.py` shows the post-trim size

### Events Have Wrong Dates

For calendar grid sites (bare day numbers), use `calendar_grid` type with `inject_dates: True`.

### Pagination Not Working

1. Try `debug_pipeline.py <key> --stop-after fetch` to see raw HTML
2. For `js_button`: inspect the button in browser dev tools to get the right CSS selector
3. For `url_param`: confirm whether it's zero-indexed (`start_index: 0`)

---

## Testing Tools

```bash
# Quick test (no DB writes)
python _test_llm_scrape.py <key>
python _test_llm_scrape.py <key> --dump    # also shows cleaned text

# Step-by-step debug pipeline
python3 debug_fetch.py <key>               # Stage 1: fetch HTML
python3 debug_clean.py <key>               # Stage 2: clean + trim
python3 debug_chunk.py <key>               # Stage 3: visualize chunking
python3 debug_llm.py <key>                 # Stage 4+5: LLM call + parse
python3 debug_pipeline.py <key>            # All stages with interactive pauses

# Useful flags
python3 debug_pipeline.py <key> --stop-after clean   # stop before LLM
python3 debug_llm.py <key> --dry-run                  # show prompt, no API call
python3 debug_llm.py <key> --provider both            # compare Groq vs Ollama
```

---

## Summary Checklist

When adding a new scraper, confirm:

- [ ] `SITES` entry added to `sources.py`
- [ ] `TRIM_PATTERNS` entry added to `sources.py` (same file, section below `SITES`)
- [ ] Trim pattern verified: appears exactly once in `debug_artifacts/<key>/page_1_cleaned.txt`
- [ ] Trim pattern is 2+ lines (not a single common word)
- [ ] Trim pattern is not month-specific or event-title-specific
- [ ] `python _test_llm_scrape.py <key>` finds events successfully
- [ ] `note` field documents any quirks for future reference
