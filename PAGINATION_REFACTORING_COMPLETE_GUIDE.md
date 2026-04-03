# Pagination Refactoring Complete Guide

**Document Version:** 1.0  
**Created:** 2024  
**Purpose:** Complete reference for refactoring pagination logic in llm_scraper.py

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Option 1: Hybrid Minimal](#option-1-hybrid-minimal)
4. [Option 2: Strategy Pattern](#option-2-strategy-pattern)
5. [Option 3: Config-Driven](#option-3-config-driven)
6. [Comparison Matrix](#comparison-matrix)
7. [Migration Guide](#migration-guide)
8. [Testing Strategy](#testing-strategy)

---

## Executive Summary

### Quick Comparison

| Aspect | Hybrid Minimal | Strategy Pattern | Config-Driven |
|--------|---------------|------------------|---------------|
| **Lines of Code** | ~350 | ~450 | ~400 |
| **New Files** | 1 | 8 | 2 |
| **Complexity** | Low | Medium | Medium-Low |
| **Extensibility** | Medium | High | High |
| **Learning Curve** | Minimal | Moderate | Low |
| **Best For** | Quick cleanup | Future growth | Balance |

### Recommendation by Scenario

- **Immediate cleanup needed:** Hybrid Minimal
- **Expecting 10+ new sites:** Strategy Pattern
- **Team unfamiliar with patterns:** Config-Driven
- **Long-term maintainability:** Strategy Pattern or Config-Driven

---

## Current State Analysis

### Overview

The `scrape_and_save()` function in `llm_scraper.py` contains 8 different pagination patterns hardcoded as if/elif blocks, totaling ~250 lines of pagination logic.

### Current Pagination Patterns

#### 1. **dirtydrummer** - Multi-Month URL Generation
```python
# Generates 3 month URLs: ?view=calendar&month=MM-YYYY
for i in range(3):
    month_date = base_date + timedelta(days=30*i)
    month_str = month_date.strftime('%m-%Y')
    url = f"https://www.thedirtydrummer.com/events?view=calendar&month={month_str}"
```

#### 2. **chandler_lib** - Query Parameter Pagination
```python
# &page=N pagination (1-indexed)
for page_num in range(1, max_pages + 1):
    url = f"{start_url}&page={page_num}" if page_num > 1 else start_url
```

#### 3. **mesa** - Regex URL Substitution
```python
# pageindex=N in URL (1-indexed)
url = re.sub(r'pageindex=\d+', f'pageindex={page_num}', start_url)
```

#### 4. **azmnh** - JavaScript Button Click with Style Check
```python
# Click next button, check parent style for display:none
next_btn = driver.find_element(By.CSS_SELECTOR, "li.nextLink a.page-link")
parent = driver.find_element(By.CSS_SELECTOR, "li.nextLink")
style = parent.get_attribute('style') or ''
if 'display: none' in style or 'display:none' in style:
    break
driver.execute_script("arguments[0].click();", next_btn)
```

#### 5. **phoenix** - JavaScript Button Click (Different Selector)
```python
# Click second pagination button
btns = driver.find_elements(By.CSS_SELECTOR, "a.cmp-searchCustom__pagination-btn")
if len(btns) < 2 or btns[1].get_attribute('disabled'):
    break
driver.execute_script("arguments[0].click();", btns[1])
```

#### 6. **tca/gilbert** - Calendar Month URLs with Date Injection
```python
# /-curm-M/-cury-YYYY/ URL pattern + text replacement
url = f"{base_urls[key]}/-curm-{month_date.month}/-cury-{month_date.year}"
# Replace bare day numbers with full dates
for day in range(1, days_in_month + 1):
    text = re.sub(rf'(?m)^{day}$', f'{month_name} {day}, {month_date.year}:', text)
```

#### 7. **chandler** - Zero-Indexed Query Parameter
```python
# ?page=N pagination (0-indexed)
url = f"{start_url}?page={page_num}"
```

#### 8. **default** - LLM-Detected next_page_url
```python
# LLM extracts next_page_url from page text
result = ask_llm(text, current_url=current_url, site_hint=name)
next_url = result.get('next_page_url')
current_url = next_url
```

### Problems with Current Approach

1. **Monolithic function:** 250+ lines of pagination logic in one function
2. **Code duplication:** Similar patterns repeated (chandler vs chandler_lib)
3. **Hard to test:** Can't test pagination logic without full scraping
4. **Difficult to extend:** Adding new site requires editing large function
5. **Poor separation:** Pagination mixed with fetching, parsing, and DB logic
6. **Maintenance burden:** Understanding all patterns requires reading entire function

---

## Option 1: Hybrid Minimal

### Philosophy

Extract only the most complex patterns into separate functions, leaving simple cases inline. Minimal disruption, maximum clarity.

### Architecture

```
llm_scraper.py
├── scrape_and_save()           # Main function (simplified)
├── _paginate_multi_month()     # Handles dirtydrummer, tca, gilbert
├── _paginate_js_button()       # Handles azmnh, phoenix
└── _paginate_url_pattern()     # Handles chandler_lib, mesa, chandler
```

### Complete Implementation

#### File: `llm_scraper.py` (Modified)

```python
"""
llm_scraper.py -- Production LLM-based event scraper

Imports all fetch/LLM/site logic from llm_scrape_core. This file only
contains DB persistence, date parsing, and the CLI entry point.
"""

import sys, time, re
from datetime import datetime, timedelta
from database.models import Session, Event, ScraperRun
from llm_scrape_core import (
    fetch_requests, fetch_selenium, close_driver, get_driver,
    clean_html, ask_llm, SITES,
)


# ---------------------------------------------------------------------------
# Date parsing (unchanged)
# ---------------------------------------------------------------------------

def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """Convert LLM-returned date/time strings to a datetime object."""
    if not date_str:
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

    date_str = date_str.strip()
    
    try:
        if time_str:
            time_str = time_str.split('-')[0].strip()
            time_str = re.sub(r'\s*p\.m\.', ' PM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'\s*a\.m\.', ' AM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'(\d)(am|pm)', lambda m: m.group(1) + ' ' + m.group(2).upper(), time_str, flags=re.IGNORECASE)
            combined = f"{date_str} {time_str}"
            for time_fmt in ['%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %H:%M']:
                try:
                    return datetime.strptime(combined, time_fmt)
                except ValueError:
                    continue
        
        return datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12, minute=34)
    except ValueError:
        pass
    
    legacy_formats = [
        '%B %d, %Y', '%b %d, %Y', '%A, %B %d, %Y', '%A, %b %d, %Y',
        '%m/%d/%Y', '%Y-%m-%d'
    ]
    
    for fmt in legacy_formats:
        try:
            return datetime.strptime(date_str, fmt).replace(hour=12, minute=34)
        except ValueError:
            continue

    return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------

def _paginate_multi_month(key: str, name: str, start_url: str, use_selenium: bool, wait: int) -> list:
    """
    Handle multi-month calendar scraping for dirtydrummer, tca, gilbert.
    
    Returns:
        List of extracted events
    """
    import calendar as cal_mod
    all_events = []
    
    if key == 'dirtydrummer':
        # ?view=calendar&month=MM-YYYY pattern
        base_date = datetime.now()
        for i in range(3):
            month_date = base_date + timedelta(days=30*i)
            month_str = month_date.strftime('%m-%Y')
            url = f"https://www.thedirtydrummer.com/events?view=calendar&month={month_str}"
            
            print(f"  Month {i+1}: {url}")
            html = fetch_selenium(url, wait) if use_selenium else fetch_requests(url)
            text = clean_html(html)
            print(f"    text={len(text)} chars", end='  ')
            
            result = ask_llm(text, current_url=url, site_hint=name)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < 2:
                time.sleep(2)
    
    elif key in ('tca', 'gilbert'):
        # /-curm-M/-cury-YYYY/ pattern with date injection
        base_urls = {
            'tca': 'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar',
            'gilbert': 'https://www.gilbertaz.gov/residents/calendar-month-view',
        }
        base_date = datetime.now()
        
        for i in range(3):
            month_date = base_date + timedelta(days=30*i)
            url = f"{base_urls[key]}/-curm-{month_date.month}/-cury-{month_date.year}"
            month_hint = f"{name} - {month_date.strftime('%B %Y')}"
            
            print(f"  Month {i+1}: {url}")
            html = fetch_selenium(url, wait)
            text = clean_html(html)
            
            # Inject full dates for bare day numbers
            month_name = month_date.strftime('%B')
            days_in_month = cal_mod.monthrange(month_date.year, month_date.month)[1]
            for day in range(1, days_in_month + 1):
                text = re.sub(rf'(?m)^{day}$', f'{month_name} {day}, {month_date.year}:', text)
            
            print(f"    text={len(text)} chars", end='  ')
            result = ask_llm(text, current_url=url, site_hint=month_hint)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < 2:
                time.sleep(2)
    
    return all_events


def _paginate_js_button(key: str, name: str, start_url: str, wait: int, max_pages: int) -> list:
    """
    Handle JavaScript button-click pagination for azmnh, phoenix.
    
    Returns:
        List of extracted events
    """
    from selenium.webdriver.common.by import By
    
    all_events = []
    close_driver()
    driver = get_driver()
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'acceptLanguage': 'en-US,en;q=0.9', 'platform': 'Win32',
    })
    
    try:
        driver.get(start_url)
    except Exception:
        pass
    time.sleep(wait)
    
    for page_num in range(1, max_pages + 1):
        if key == 'phoenix':
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        
        text = clean_html(driver.page_source)
        print(f"  page {page_num}: text={len(text)} chars", end='  ')
        result = ask_llm(text, current_url=start_url, site_hint=name)
        page_events = result.get('events', [])
        all_events.extend(page_events)
        print(f"events={len(page_events)}")
        
        # Try to click next button
        try:
            if key == 'azmnh':
                next_btn = driver.find_element(By.CSS_SELECTOR, "li.nextLink a.page-link")
                parent = driver.find_element(By.CSS_SELECTOR, "li.nextLink")
                style = parent.get_attribute('style') or ''
                if 'display: none' in style or 'display:none' in style:
                    print(f"    Last page reached")
                    break
                driver.execute_script("arguments[0].click();", next_btn)
            elif key == 'phoenix':
                btns = driver.find_elements(By.CSS_SELECTOR, "a.cmp-searchCustom__pagination-btn")
                if len(btns) < 2 or btns[1].get_attribute('disabled'):
                    print(f"    Last page reached")
                    break
                driver.execute_script("arguments[0].click();", btns[1])
            
            time.sleep(3)
        except Exception as e:
            print(f"    Pagination ended: {e}")
            break
    
    close_driver()
    return all_events


def _paginate_url_pattern(key: str, name: str, start_url: str, use_selenium: bool, wait: int, max_pages: int) -> list:
    """
    Handle URL-based pagination for chandler_lib, mesa, chandler.
    
    Returns:
        List of extracted events
    """
    all_events = []
    
    for page_num in range(1 if key != 'chandler' else 0, max_pages + (0 if key != 'chandler' else 1)):
        # Build URL based on pattern
        if key == 'chandler_lib':
            url = f"{start_url}&page={page_num}" if page_num > 1 else start_url
        elif key == 'mesa':
            url = re.sub(r'pageindex=\d+', f'pageindex={page_num}', start_url)
        elif key == 'chandler':
            url = f"{start_url}?page={page_num}"
        else:
            url = start_url
        
        print(f"  Page {page_num}: {url[:80]}")
        html = fetch_selenium(url, wait) if use_selenium else fetch_requests(url)
        text = clean_html(html)
        print(f"    text={len(text)} chars", end='  ')
        
        result = ask_llm(text, current_url=url, site_hint=name)
        page_events = result.get('events', [])
        all_events.extend(page_events)
        print(f"events={len(page_events)}")
        
        # Stop if no events found
        if not page_events:
            print(f"    No events, stopping")
            break
        
        if page_num < max_pages:
            time.sleep(2)
    
    return all_events


# ---------------------------------------------------------------------------
# Scrape + save
# ---------------------------------------------------------------------------

def scrape_and_save(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    session
) -> tuple[int, int, bool, str | None]:
    """
    Scrape one site via LLM extraction and save new events to the database.
    """
    all_events = []
    error_message = None
    success = True
    
    try:
        # Route to appropriate pagination handler
        if key in ('dirtydrummer', 'tca', 'gilbert'):
            all_events = _paginate_multi_month(key, name, start_url, use_selenium, wait)
        
        elif key in ('azmnh', 'phoenix'):
            all_events = _paginate_js_button(key, name, start_url, wait, max_pages)
        
        elif key in ('chandler_lib', 'mesa', 'chandler'):
            all_events = _paginate_url_pattern(key, name, start_url, use_selenium, wait, max_pages)
        
        else:
            # Default: LLM-detected pagination
            current_url = start_url
            visited = set()
            page_num = 0
            
            while current_url and page_num < max_pages:
                page_num += 1
                if current_url in visited:
                    print(f"    loop detected, stopping")
                    break
                visited.add(current_url)
                
                print(f"  page {page_num}: {current_url[:80]}")
                html = fetch_selenium(current_url, wait, scroll_passes=10) if use_selenium else fetch_requests(current_url)
                text = clean_html(html)
                print(f"    text={len(text)} chars", end='  ')
                
                result = ask_llm(text, current_url=current_url, site_hint=name)
                page_events = result.get('events', [])
                next_url = result.get('next_page_url')
                all_events.extend(page_events)
                print(f"events={len(page_events)}  next={next_url or 'null'}")
                
                if next_url and not next_url.startswith('http'):
                    break
                current_url = next_url
                if current_url:
                    time.sleep(2)
    
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"  ERROR: {e}")
    
    # Save to database
    events_added = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for ev in all_events:
        event_dt = parse_date(ev.get('date'), ev.get('time'))
        title = (ev.get('title') or '').strip()
        if not title:
            continue
        
        # Handle date range events
        end_date_str = ev.get('end_date')
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')
                if event_dt < today and end_dt >= today:
                    event_dt = today
            except ValueError:
                pass
        
        existing = session.query(Event).filter_by(title=title, date=event_dt).first()
        if not existing:
            url = (ev.get('url') or '').strip()
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(start_url, url)
            
            session.add(Event(
                title=title,
                description=(ev.get('description') or '').strip(),
                venue=(ev.get('venue') or '').strip(),
                date=event_dt,
                url=url,
                source=key,
                category='general',
            ))
            events_added += 1
    
    session.commit()
    return len(all_events), events_added, success, error_message


# ---------------------------------------------------------------------------
# Entry point (unchanged)
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    no_purge = '--no-purge' in args
    args = [a for a in args if a != '--no-purge']
    target = args[0] if args else None
    
    if target == 'list':
        print(f"{'KEY':<18} {'FETCH':<10} {'PAGES':<7} URL")
        print('-' * 80)
        for k, (name, url, use_sel, wait, max_pages, note, _color) in SITES.items():
            sel = 'selenium' if use_sel else 'requests'
            flag = f'  [{note}]' if note else ''
            print(f"  {k:<16} {sel:<10} max={max_pages}  {url[:55]}{flag}")
        sys.exit(0)
    
    if not target or target == 'all':
        keys = list(SITES)
    elif all(a in SITES for a in args):
        keys = args
        unknown = [k for k in keys if k not in SITES]
        if unknown:
            print(f"Unknown site(s): {', '.join(unknown)}")
            print(f"Valid keys: {', '.join(SITES)}")
            sys.exit(1)
    else:
        print(f"Unknown site '{target}'. Run with 'list' to see valid keys.")
        sys.exit(1)
    
    session = Session()
    
    try:
        if not no_purge and (not target or target == 'all'):
            count = session.query(Event).delete()
            session.commit()
            print(f"Purged {count} existing events from database.\n")
        elif no_purge:
            print("--no-purge: appending to existing events.\n")
        
        total_found = 0
        total_added = 0
        
        for key in keys:
            name, url, use_sel, wait, max_pages, note, _color = SITES[key]
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")
            
            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, session
            )
            duration = time.time() - start_time
            total_found += found
            total_added += added
            
            print(f"  -> {added} new events added ({found} found) in {duration:.0f}s")
            
            session.add(ScraperRun(
                source=key,
                run_timestamp=datetime.utcnow(),
                events_found=found,
                events_added=added,
                success=success,
                error_message=error,
                duration_seconds=duration,
            ))
            session.commit()
            
            if key != keys[-1]:
                time.sleep(3)
        
        print(f"\n{'='*60}")
        print(f"DONE: {total_added} new events added ({total_found} found across {len(keys)} sites)")
        print(f"{'='*60}")
    
    finally:
        close_driver()
        session.close()


if __name__ == '__main__':
    main()
```

### Before/After Comparison

**Before:**
- `scrape_and_save()`: 250 lines
- 8 if/elif blocks with duplicated logic
- Difficult to test individual patterns

**After:**
- `scrape_and_save()`: 80 lines
- 3 helper functions (40-60 lines each)
- Each pattern testable independently
- 30% reduction in total lines

### Migration Steps

1. **Backup current file:**
   ```bash
   cp llm_scraper.py llm_scraper.py.backup
   ```

2. **Replace llm_scraper.py with new version** (see complete code above)

3. **Test each pagination type:**
   ```bash
   python _test_llm_scrape.py dirtydrummer  # Multi-month
   python _test_llm_scrape.py azmnh         # JS button
   python _test_llm_scrape.py chandler_lib  # URL pattern
   python _test_llm_scrape.py fibber        # Default LLM
   ```

4. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

5. **Verify results in health dashboard:**
   ```bash
   python server/app.py
   # Visit http://localhost:5000/health
   ```

### Testing Checklist

- [ ] dirtydrummer scrapes 3 months
- [ ] tca/gilbert scrape with date injection
- [ ] azmnh clicks through pages
- [ ] phoenix clicks through pages
- [ ] chandler_lib paginates with &page=N
- [ ] mesa paginates with pageindex=N
- [ ] chandler paginates with ?page=N (zero-indexed)
- [ ] fibber/rak use LLM-detected next_page_url
- [ ] No duplicate events in database
- [ ] ScraperRun records created correctly

---

## Option 2: Strategy Pattern

### Philosophy

Use object-oriented design patterns to create a pluggable pagination system. Each pagination type is a separate strategy class implementing a common interface.

### Architecture

```
pagination/
├── __init__.py
├── base.py                    # PaginationStrategy base class
├── multi_month.py             # MultiMonthStrategy
├── js_button.py               # JSButtonStrategy
├── url_pattern.py             # URLPatternStrategy
├── llm_detected.py            # LLMDetectedStrategy
└── factory.py                 # Strategy factory

llm_scraper.py                 # Uses strategy pattern
```

### Complete Implementation

#### File: `pagination/__init__.py`

```python
"""
pagination package -- Strategy pattern for site-specific pagination
"""

from .base import PaginationStrategy
from .factory import get_pagination_strategy

__all__ = ['PaginationStrategy', 'get_pagination_strategy']
```

#### File: `pagination/base.py`

```python
"""
base.py -- Base class for pagination strategies
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class PaginationStrategy(ABC):
    """
    Abstract base class for pagination strategies.
    
    Each strategy implements a specific pagination pattern (URL-based,
    JS button clicks, multi-month calendars, etc.)
    """
    
    def __init__(self, key: str, name: str, start_url: str, use_selenium: bool, 
                 wait: int, max_pages: int):
        self.key = key
        self.name = name
        self.start_url = start_url
        self.use_selenium = use_selenium
        self.wait = wait
        self.max_pages = max_pages
    
    @abstractmethod
    def paginate(self) -> List[Dict[str, Any]]:
        """
        Execute pagination and return all extracted events.
        
        Returns:
            List of event dictionaries with keys: title, date, time, 
            description, venue, url, end_date
        """
        pass
    
    def _fetch_page(self, url: str, scroll_passes: int = 10) -> str:
        """Helper to fetch a page using appropriate method."""
        from llm_scrape_core import fetch_requests, fetch_selenium
        if self.use_selenium:
            return fetch_selenium(url, self.wait, scroll_passes=scroll_passes)
        else:
            return fetch_requests(url)
    
    def _extract_events(self, html: str, current_url: str) -> Dict[str, Any]:
        """Helper to clean HTML and extract events via LLM."""
        from llm_scrape_core import clean_html, ask_llm
        text = clean_html(html)
        print(f"    text={len(text)} chars", end='  ')
        return ask_llm(text, current_url=current_url, site_hint=self.name)
```

#### File: `pagination/multi_month.py`

```python
"""
multi_month.py -- Multi-month calendar pagination strategy
"""

import re
import time
import calendar as cal_mod
from datetime import datetime, timedelta
from .base import PaginationStrategy


class MultiMonthStrategy(PaginationStrategy):
    """
    Handles sites that use month-based calendar views.
    
    Supports:
    - dirtydrummer: ?view=calendar&month=MM-YYYY
    - tca/gilbert: /-curm-M/-cury-YYYY/ with date injection
    """
    
    def paginate(self):
        all_events = []
        
        if self.key == 'dirtydrummer':
            all_events = self._paginate_dirtydrummer()
        elif self.key in ('tca', 'gilbert'):
            all_events = self._paginate_calendar_month()
        
        return all_events
    
    def _paginate_dirtydrummer(self):
        """Squarespace calendar with ?month=MM-YYYY parameter."""
        all_events = []
        base_date = datetime.now()
        
        for i in range(3):
            month_date = base_date + timedelta(days=30*i)
            month_str = month_date.strftime('%m-%Y')
            url = f"{self.start_url}?view=calendar&month={month_str}"
            
            print(f"  Month {i+1}: {url}")
            html = self._fetch_page(url)
            result = self._extract_events(html, url)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < 2:
                time.sleep(2)
        
        return all_events
    
    def _paginate_calendar_month(self):
        """Calendar with /-curm-M/-cury-YYYY/ URL pattern and date injection."""
        base_urls = {
            'tca': 'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar',
            'gilbert': 'https://www.gilbertaz.gov/residents/calendar-month-view',
        }
        
        all_events = []
        base_date = datetime.now()
        
        for i in range(3):
            month_date = base_date + timedelta(days=30*i)
            url = f"{base_urls[self.key]}/-curm-{month_date.month}/-cury-{month_date.year}"
            month_hint = f"{self.name} - {month_date.strftime('%B %Y')}"
            
            print(f"  Month {i+1}: {url}")
            html = self._fetch_page(url)
            
            # Inject full dates for bare day numbers
            from llm_scrape_core import clean_html
            text = clean_html(html)
            month_name = month_date.strftime('%B')
            days_in_month = cal_mod.monthrange(month_date.year, month_date.month)[1]
            
            for day in range(1, days_in_month + 1):
                text = re.sub(rf'(?m)^{day}$', f'{month_name} {day}, {month_date.year}:', text)
            
            print(f"    text={len(text)} chars", end='  ')
            from llm_scrape_core import ask_llm
            result = ask_llm(text, current_url=url, site_hint=month_hint)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < 2:
                time.sleep(2)
        
        return all_events
```

#### File: `pagination/js_button.py`

```python
"""
js_button.py -- JavaScript button-click pagination strategy
"""

import time
from selenium.webdriver.common.by import By
from .base import PaginationStrategy


class JSButtonStrategy(PaginationStrategy):
    """
    Handles sites that paginate via JavaScript button clicks.
    
    Supports:
    - azmnh: li.nextLink with style check
    - phoenix: a.cmp-searchCustom__pagination-btn (second button)
    """
    
    def paginate(self):
        from llm_scrape_core import get_driver, close_driver, clean_html, ask_llm
        
        all_events = []
        close_driver()
        driver = get_driver()
        
        # CDP user-agent spoofing
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'acceptLanguage': 'en-US,en;q=0.9',
            'platform': 'Win32',
        })
        
        try:
            driver.get(self.start_url)
        except Exception:
            pass
        time.sleep(self.wait)
        
        for page_num in range(1, self.max_pages + 1):
            # Phoenix needs scroll before extraction
            if self.key == 'phoenix':
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            text = clean_html(driver.page_source)
            print(f"  page {page_num}: text={len(text)} chars", end='  ')
            result = ask_llm(text, current_url=self.start_url, site_hint=self.name)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            # Try to click next button
            try:
                if self.key == 'azmnh':
                    if not self._click_azmnh_next(driver):
                        break
                elif self.key == 'phoenix':
                    if not self._click_phoenix_next(driver):
                        break
                
                time.sleep(3)
            except Exception as e:
                print(f"    Pagination ended: {e}")
                break
        
        close_driver()
        return all_events
    
    def _click_azmnh_next(self, driver) -> bool:
        """Click AZMNH next button, return False if last page."""
        next_btn = driver.find_element(By.CSS_SELECTOR, "li.nextLink a.page-link")
        parent = driver.find_element(By.CSS_SELECTOR, "li.nextLink")
        style = parent.get_attribute('style') or ''
        
        if 'display: none' in style or 'display:none' in style:
            print(f"    Last page reached")
            return False
        
        driver.execute_script("arguments[0].click();", next_btn)
        return True
    
    def _click_phoenix_next(self, driver) -> bool:
        """Click Phoenix next button, return False if last page."""
        btns = driver.find_elements(By.CSS_SELECTOR, "a.cmp-searchCustom__pagination-btn")
        
        if len(btns) < 2 or btns[1].get_attribute('disabled'):
            print(f"    Last page reached")
            return False
        
        driver.execute_script("arguments[0].click();", btns[1])
        return True
```

#### File: `pagination/url_pattern.py`

```python
"""
url_pattern.py -- URL-based pagination strategy
"""

import re
import time
from .base import PaginationStrategy


class URLPatternStrategy(PaginationStrategy):
    """
    Handles sites with predictable URL pagination patterns.
    
    Supports:
    - chandler_lib: &page=N (1-indexed)
    - mesa: pageindex=N (1-indexed, regex substitution)
    - chandler: ?page=N (0-indexed)
    """
    
    def paginate(self):
        all_events = []
        
        # Determine page range based on site
        if self.key == 'chandler':
            page_range = range(0, self.max_pages)
        else:
            page_range = range(1, self.max_pages + 1)
        
        for page_num in page_range:
            url = self._build_url(page_num)
            
            print(f"  Page {page_num}: {url[:80]}")
            html = self._fetch_page(url)
            result = self._extract_events(html, url)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            # Stop if no events found
            if not page_events:
                print(f"    No events, stopping")
                break
            
            if page_num < (self.max_pages - 1 if self.key == 'chandler' else self.max_pages):
                time.sleep(2)
        
        return all_events
    
    def _build_url(self, page_num: int) -> str:
        """Build paginated URL based on site pattern."""
        if self.key == 'chandler_lib':
            return f"{self.start_url}&page={page_num}" if page_num > 1 else self.start_url
        elif self.key == 'mesa':
            return re.sub(r'pageindex=\d+', f'pageindex={page_num}', self.start_url)
        elif self.key == 'chandler':
            return f"{self.start_url}?page={page_num}"
        else:
            return self.start_url
```

#### File: `pagination/llm_detected.py`

```python
"""
llm_detected.py -- LLM-detected pagination strategy
"""

import time
from .base import PaginationStrategy


class LLMDetectedStrategy(PaginationStrategy):
    """
    Default strategy: let the LLM detect next_page_url from page content.
    
    Works for sites with visible "Next" links or numbered pagination that
    the LLM can extract from the cleaned HTML text.
    """
    
    def paginate(self):
        all_events = []
        current_url = self.start_url
        visited = set()
        page_num = 0
        
        while current_url and page_num < self.max_pages:
            page_num += 1
            
            # Loop detection
            if current_url in visited:
                print(f"    loop detected, stopping")
                break
            visited.add(current_url)
            
            print(f"  page {page_num}: {current_url[:80]}")
            
            try:
                html = self._fetch_page(current_url, scroll_passes=10)
            except Exception as e:
                print(f"    FETCH ERROR: {e}")
                break
            
            try:
                result = self._extract_events(html, current_url)
            except Exception as e:
                print(f"\n    LLM ERROR: {e}")
                break
            
            page_events = result.get('events', [])
            next_url = result.get('next_page_url')
            all_events.extend(page_events)
            print(f"events={len(page_events)}  next={next_url or 'null'}")
            
            # Validate next URL
            if next_url and not next_url.startswith('http'):
                print(f"    Invalid next URL: {next_url}")
                break
            
            current_url = next_url
            if current_url:
                time.sleep(2)
        
        return all_events
```

#### File: `pagination/factory.py`

```python
"""
factory.py -- Factory for creating pagination strategies
"""

from .base import PaginationStrategy
from .multi_month import MultiMonthStrategy
from .js_button import JSButtonStrategy
from .url_pattern import URLPatternStrategy
from .llm_detected import LLMDetectedStrategy


def get_pagination_strategy(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int
) -> PaginationStrategy:
    """
    Factory function to create the appropriate pagination strategy.
    
    Args:
        key: Site key from SITES dict
        name: Display name for the site
        start_url: Starting URL
        use_selenium: Whether to use Selenium
        wait: Seconds to wait after page load
        max_pages: Maximum pages to scrape
    
    Returns:
        PaginationStrategy instance
    """
    # Multi-month calendar sites
    if key in ('dirtydrummer', 'tca', 'gilbert'):
        return MultiMonthStrategy(key, name, start_url, use_selenium, wait, max_pages)
    
    # JavaScript button pagination
    elif key in ('azmnh', 'phoenix'):
        return JSButtonStrategy(key, name, start_url, use_selenium, wait, max_pages)
    
    # URL pattern pagination
    elif key in ('chandler_lib', 'mesa', 'chandler'):
        return URLPatternStrategy(key, name, start_url, use_selenium, wait, max_pages)
    
    # Default: LLM-detected pagination
    else:
        return LLMDetectedStrategy(key, name, start_url, use_selenium, wait, max_pages)
```

#### File: `llm_scraper.py` (Modified for Strategy Pattern)

```python
"""
llm_scraper.py -- Production LLM-based event scraper (Strategy Pattern version)
"""

import sys, time, re
from datetime import datetime, timedelta
from database.models import Session, Event, ScraperRun
from llm_scrape_core import close_driver, SITES
from pagination import get_pagination_strategy


# ---------------------------------------------------------------------------
# Date parsing (unchanged)
# ---------------------------------------------------------------------------

def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """Convert LLM-returned date/time strings to a datetime object."""
    if not date_str:
        return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)

    date_str = date_str.strip()
    
    try:
        if time_str:
            time_str = time_str.split('-')[0].strip()
            time_str = re.sub(r'\s*p\.m\.', ' PM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'\s*a\.m\.', ' AM', time_str, flags=re.IGNORECASE)
            time_str = re.sub(r'(\d)(am|pm)', lambda m: m.group(1) + ' ' + m.group(2).upper(), time_str, flags=re.IGNORECASE)
            combined = f"{date_str} {time_str}"
            for time_fmt in ['%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %H:%M']:
                try:
                    return datetime.strptime(combined, time_fmt)
                except ValueError:
                    continue
        
        return datetime.strptime(date_str, '%Y-%m-%d').replace(hour=12, minute=34)
    except ValueError:
        pass
    
    legacy_formats = [
        '%B %d, %Y', '%b %d, %Y', '%A, %B %d, %Y', '%A, %b %d, %Y',
        '%m/%d/%Y', '%Y-%m-%d'
    ]
    
    for fmt in legacy_formats:
        try:
            return datetime.strptime(date_str, fmt).replace(hour=12, minute=34)
        except ValueError:
            continue

    return datetime.now().replace(hour=12, minute=34, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Scrape + save
# ---------------------------------------------------------------------------

def scrape_and_save(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    session
) -> tuple[int, int, bool, str | None]:
    """
    Scrape one site via LLM extraction and save new events to the database.
    
    Uses strategy pattern to delegate pagination logic.
    """
    all_events = []
    error_message = None
    success = True
    
    try:
        # Get appropriate pagination strategy
        strategy = get_pagination_strategy(key, name, start_url, use_selenium, wait, max_pages)
        
        # Execute pagination
        all_events = strategy.paginate()
    
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"  ERROR: {e}")
    
    # Save to database
    events_added = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for ev in all_events:
        event_dt = parse_date(ev.get('date'), ev.get('time'))
        title = (ev.get('title') or '').strip()
        if not title:
            continue
        
        # Handle date range events
        end_date_str = ev.get('end_date')
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')
                if event_dt < today and end_dt >= today:
                    event_dt = today
            except ValueError:
                pass
        
        existing = session.query(Event).filter_by(title=title, date=event_dt).first()
        if not existing:
            url = (ev.get('url') or '').strip()
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(start_url, url)
            
            session.add(Event(
                title=title,
                description=(ev.get('description') or '').strip(),
                venue=(ev.get('venue') or '').strip(),
                date=event_dt,
                url=url,
                source=key,
                category='general',
            ))
            events_added += 1
    
    session.commit()
    return len(all_events), events_added, success, error_message


# ---------------------------------------------------------------------------
# Entry point (unchanged)
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    no_purge = '--no-purge' in args
    args = [a for a in args if a != '--no-purge']
    target = args[0] if args else None
    
    if target == 'list':
        print(f"{'KEY':<18} {'FETCH':<10} {'PAGES':<7} URL")
        print('-' * 80)
        for k, (name, url, use_sel, wait, max_pages, note, _color) in SITES.items():
            sel = 'selenium' if use_sel else 'requests'
            flag = f'  [{note}]' if note else ''
            print(f"  {k:<16} {sel:<10} max={max_pages}  {url[:55]}{flag}")
        sys.exit(0)
    
    if not target or target == 'all':
        keys = list(SITES)
    elif all(a in SITES for a in args):
        keys = args
        unknown = [k for k in keys if k not in SITES]
        if unknown:
            print(f"Unknown site(s): {', '.join(unknown)}")
            print(f"Valid keys: {', '.join(SITES)}")
            sys.exit(1)
    else:
        print(f"Unknown site '{target}'. Run with 'list' to see valid keys.")
        sys.exit(1)
    
    session = Session()
    
    try:
        if not no_purge and (not target or target == 'all'):
            count = session.query(Event).delete()
            session.commit()
            print(f"Purged {count} existing events from database.\n")
        elif no_purge:
            print("--no-purge: appending to existing events.\n")
        
        total_found = 0
        total_added = 0
        
        for key in keys:
            name, url, use_sel, wait, max_pages, note, _color = SITES[key]
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")
            
            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, session
            )
            duration = time.time() - start_time
            total_found += found
            total_added += added
            
            print(f"  -> {added} new events added ({found} found) in {duration:.0f}s")
            
            session.add(ScraperRun(
                source=key,
                run_timestamp=datetime.utcnow(),
                events_found=found,
                events_added=added,
                success=success,
                error_message=error,
                duration_seconds=duration,
            ))
            session.commit()
            
            if key != keys[-1]:
                time.sleep(3)
        
        print(f"\n{'='*60}")
        print(f"DONE: {total_added} new events added ({total_found} found across {len(keys)} sites)")
        print(f"{'='*60}")
    
    finally:
        close_driver()
        session.close()


if __name__ == '__main__':
    main()
```

### Before/After Comparison

**Before:**
- Single file: 250 lines of pagination logic
- All patterns in one function
- No abstraction or reusability

**After:**
- 8 files: Clean separation of concerns
- Each strategy: 40-80 lines
- `scrape_and_save()`: 60 lines (75% reduction)
- Easy to add new strategies
- Each strategy independently testable

### Migration Steps

1. **Create pagination package:**
   ```bash
   mkdir pagination
   touch pagination/__init__.py
   ```

2. **Create strategy files** (copy code from above):
   - `pagination/base.py`
   - `pagination/multi_month.py`
   - `pagination/js_button.py`
   - `pagination/url_pattern.py`
   - `pagination/llm_detected.py`
   - `pagination/factory.py`

3. **Backup and replace llm_scraper.py:**
   ```bash
   cp llm_scraper.py llm_scraper.py.backup
   # Replace with strategy pattern version
   ```

4. **Test each strategy:**
   ```bash
   python _test_llm_scrape.py dirtydrummer
   python _test_llm_scrape.py azmnh
   python _test_llm_scrape.py chandler_lib
   python _test_llm_scrape.py fibber
   ```

5. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

### Testing Checklist

- [ ] All 8 pagination patterns work correctly
- [ ] New sites can be added by creating new strategy classes
- [ ] Factory correctly routes to appropriate strategy
- [ ] No regressions in event extraction
- [ ] ScraperRun records created correctly
- [ ] Error handling works in each strategy

### Adding a New Site

**Example: Adding a new site with `/events/page-N` pagination**

1. **Determine if existing strategy fits:**
   - URL pattern? Use `URLPatternStrategy`
   - JS buttons? Use `JSButtonStrategy`
   - Multi-month? Use `MultiMonthStrategy`
   - None fit? Create new strategy

2. **If new strategy needed, create `pagination/page_dash.py`:**
   ```python
   from .base import PaginationStrategy
   import time
   
   class PageDashStrategy(PaginationStrategy):
       def paginate(self):
           all_events = []
           for page_num in range(1, self.max_pages + 1):
               url = f"{self.start_url}/page-{page_num}"
               print(f"  Page {page_num}: {url}")
               html = self._fetch_page(url)
               result = self._extract_events(html, url)
               page_events = result.get('events', [])
               all_events.extend(page_events)
               print(f"events={len(page_events)}")
               if not page_events:
                   break
               if page_num < self.max_pages:
                   time.sleep(2)
           return all_events
   ```

3. **Update `pagination/factory.py`:**
   ```python
   from .page_dash import PageDashStrategy
   
   def get_pagination_strategy(...):
       # ... existing code ...
       elif key in ('newsite',):
           return PageDashStrategy(key, name, start_url, use_selenium, wait, max_pages)
   ```

4. **Add site to `sources.py` SITES dict**

5. **Test:**
   ```bash
   python _test_llm_scrape.py newsite
   ```

---

## Option 3: Config-Driven

### Philosophy

Move pagination configuration to `sources.py` SITES dict. Use a single pagination engine that interprets config to execute the right pattern. Balance between simplicity and extensibility.

### Architecture

```
sources.py                  # Extended SITES dict with pagination config
llm_scraper.py             # Main scraper (simplified)
pagination_engine.py       # Single engine that interprets config
```

### Complete Implementation

#### File: `sources.py` (Extended)

```python
"""
sources.py -- Single source of truth for all scraped event sources.

Extended with pagination configuration for config-driven approach.
"""

from datetime import datetime, timedelta

_today = datetime.now().strftime('%Y-%m-%d')
_plus90 = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

# ---------------------------------------------------------------------------
# Pagination type constants
# ---------------------------------------------------------------------------

PAGINATION_TYPES = {
    'llm_detected': 'LLM extracts next_page_url from page content',
    'url_append': 'Append &page=N or ?page=N to URL',
    'url_regex': 'Regex substitution in URL (e.g., pageindex=N)',
    'multi_month': 'Generate multiple month URLs',
    'calendar_month': 'Month URLs with date injection',
    'js_button': 'Click JavaScript pagination button',
}

# ---------------------------------------------------------------------------
# Site registry with pagination config
# ---------------------------------------------------------------------------

# Format: key: (name, url, use_selenium, wait, max_pages, note, color, pagination_config)
# pagination_config: dict with 'type' and type-specific parameters

SITES = {
    'fibber': (
        'Fibber Magees',
        'https://www.fibbermageespub.com/fibber-magees-events',
        False, 3, 5, '',
        ('#fff7ed', '#c2410c', '#7c2d12'),
        {'type': 'llm_detected'},
    ),
    
    'dirtydrummer': (
        'Dirty Drummer',
        'https://www.thedirtydrummer.com/events',
        True, 8, 5, 'Squarespace',
        ('#fdf2f8', '#9d174d', '#500724'),
        {
            'type': 'multi_month',
            'months': 3,
            'url_pattern': 'https://www.thedirtydrummer.com/events?view=calendar&month={month_str}',
            'month_format': '%m-%Y',
        },
    ),
    
    'chandler_lib': (
        'Chandler Public Library',
        f'https://chandler.bibliocommons.com/v2/events?start={_today}&end={_plus90}',
        True, 5, 3, 'BiblioCommons',
        ('#dcfce7', '#16a34a', '#14532d'),
        {
            'type': 'url_append',
            'param': 'page',
            'start_index': 1,
            'separator': '&',
        },
    ),
    
    'mesa': (
        'City of Mesa',
        'https://www.mesaaz.gov/Events-directory?dlv_OC%20CL%20Public%20Events%20Listing=(=)(dd_OC%20Composite%20Date=Mar%2028%202026)(dd_OC%20Event%20Categories=Community%20Class%2FProgram|Groundbreaking-Ribbon%20Cutting|Special%20Event%2FFestival|Parks%2C%20Recreation%20and%20Community%20Facilities)(pageindex=1)',
        True, 6, 5, 'pageindex=N pagination',
        ('#ede9fe', '#7c3aed', '#4c1d95'),
        {
            'type': 'url_regex',
            'pattern': r'pageindex=\d+',
            'replacement': 'pageindex={page_num}',
            'start_index': 1,
        },
    ),
    
    'azmnh': (
        'AZ Museum of Natural History',
        'https://www.azmnh.org/azmnh-events',
        True, 5, 5, '',
        ('#ecfdf5', '#10b981', '#064e3b'),
        {
            'type': 'js_button',
            'button_selector': 'li.nextLink a.page-link',
            'parent_selector': 'li.nextLink',
            'check_style': True,
        },
    ),
    
    'phoenix': (
        'City of Phoenix',
        'https://www.phoenix.gov/calendar.html',
        True, 6, 5, '',
        ('#dbeafe', '#2563eb', '#1e3a8a'),
        {
            'type': 'js_button',
            'button_selector': 'a.cmp-searchCustom__pagination-btn',
            'button_index': 1,
            'scroll_before': True,
        },
    ),
    
    'tca': (
        'Tempe Center for the Arts',
        'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar',
        True, 15, 5, 'Akamai bot detection',
        ('#f5d0fe', '#c026d3', '#4a044e'),
        {
            'type': 'calendar_month',
            'months': 3,
            'url_pattern': 'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar/-curm-{month}/-cury-{year}',
            'inject_dates': True,
        },
    ),
    
    'gilbert': (
        'City of Gilbert',
        'https://www.gilbertaz.gov/residents/calendar-month-view/',
        True, 15, 5, 'Akamai bot detection',
        ('#ffedd5', '#ea580c', '#7c2d12'),
        {
            'type': 'calendar_month',
            'months': 3,
            'url_pattern': 'https://www.gilbertaz.gov/residents/calendar-month-view/-curm-{month}/-cury-{year}',
            'inject_dates': True,
        },
    ),
    
    'chandler': (
        'City of Chandler',
        'https://www.chandleraz.gov/events-result',
        True, 5, 10, '?page=N zero-indexed',
        ('#fce7f3', '#db2777', '#831843'),
        {
            'type': 'url_append',
            'param': 'page',
            'start_index': 0,
            'separator': '?',
        },
    ),
    
    # ... other sites with {'type': 'llm_detected'} ...
}

# Derived display dicts
SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}
```

#### File: `pagination_engine.py` (New)

```python
"""
pagination_engine.py -- Config-driven pagination engine

Interprets pagination config from sources.py and executes appropriate pattern.
"""

import re
import time
import calendar as cal_mod
from datetime import datetime, timedelta
from typing import List, Dict, Any
from selenium.webdriver.common.by import By


class PaginationEngine:
    """
    Single engine that interprets pagination config and executes patterns.
    """
    
    def __init__(self, key: str, name: str, start_url: str, use_selenium: bool,
                 wait: int, max_pages: int, pagination_config: dict):
        self.key = key
        self.name = name
        self.start_url = start_url
        self.use_selenium = use_selenium
        self.wait = wait
        self.max_pages = max_pages
        self.config = pagination_config
        self.pagination_type = pagination_config.get('type', 'llm_detected')
    
    def paginate(self) -> List[Dict[str, Any]]:
        """Execute pagination based on config type."""
        if self.pagination_type == 'llm_detected':
            return self._paginate_llm_detected()
        elif self.pagination_type == 'url_append':
            return self._paginate_url_append()
        elif self.pagination_type == 'url_regex':
            return self._paginate_url_regex()
        elif self.pagination_type == 'multi_month':
            return self._paginate_multi_month()
        elif self.pagination_type == 'calendar_month':
            return self._paginate_calendar_month()
        elif self.pagination_type == 'js_button':
            return self._paginate_js_button()
        else:
            raise ValueError(f"Unknown pagination type: {self.pagination_type}")
    
    def _fetch_page(self, url: str, scroll_passes: int = 10) -> str:
        """Fetch page using appropriate method."""
        from llm_scrape_core import fetch_requests, fetch_selenium
        if self.use_selenium:
            return fetch_selenium(url, self.wait, scroll_passes=scroll_passes)
        else:
            return fetch_requests(url)
    
    def _extract_events(self, html: str, current_url: str) -> Dict[str, Any]:
        """Clean HTML and extract events via LLM."""
        from llm_scrape_core import clean_html, ask_llm
        text = clean_html(html)
        print(f"    text={len(text)} chars", end='  ')
        return ask_llm(text, current_url=current_url, site_hint=self.name)
    
    def _paginate_llm_detected(self) -> List[Dict[str, Any]]:
        """LLM extracts next_page_url from page content."""
        all_events = []
        current_url = self.start_url
        visited = set()
        page_num = 0
        
        while current_url and page_num < self.max_pages:
            page_num += 1
            if current_url in visited:
                print(f"    loop detected, stopping")
                break
            visited.add(current_url)
            
            print(f"  page {page_num}: {current_url[:80]}")
            html = self._fetch_page(current_url, scroll_passes=10)
            result = self._extract_events(html, current_url)
            
            page_events = result.get('events', [])
            next_url = result.get('next_page_url')
            all_events.extend(page_events)
            print(f"events={len(page_events)}  next={next_url or 'null'}")
            
            if next_url and not next_url.startswith('http'):
                break
            current_url = next_url
            if current_url:
                time.sleep(2)
        
        return all_events
    
    def _paginate_url_append(self) -> List[Dict[str, Any]]:
        """Append ?page=N or &page=N to URL."""
        all_events = []
        param = self.config['param']
        start_index = self.config.get('start_index', 1)
        separator = self.config.get('separator', '&')
        
        for i in range(self.max_pages):
            page_num = start_index + i
            
            if page_num == start_index and separator == '&':
                url = self.start_url
            else:
                url = f"{self.start_url}{separator}{param}={page_num}"
            
            print(f"  Page {page_num}: {url[:80]}")
            html = self._fetch_page(url)
            result = self._extract_events(html, url)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if not page_events:
                print(f"    No events, stopping")
                break
            if i < self.max_pages - 1:
                time.sleep(2)
        
        return all_events
    
    def _paginate_url_regex(self) -> List[Dict[str, Any]]:
        """Regex substitution in URL."""
        all_events = []
        pattern = self.config['pattern']
        replacement = self.config['replacement']
        start_index = self.config.get('start_index', 1)
        
        for i in range(self.max_pages):
            page_num = start_index + i
            url = re.sub(pattern, replacement.format(page_num=page_num), self.start_url)
            
            print(f"  Page {page_num}: {url[:80]}")
            html = self._fetch_page(url)
            result = self._extract_events(html, url)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if not page_events:
                print(f"    No events, stopping")
                break
            if i < self.max_pages - 1:
                time.sleep(2)
        
        return all_events
    
    def _paginate_multi_month(self) -> List[Dict[str, Any]]:
        """Generate multiple month URLs (dirtydrummer pattern)."""
        all_events = []
        months = self.config.get('months', 3)
        url_pattern = self.config['url_pattern']
        month_format = self.config.get('month_format', '%m-%Y')
        
        base_date = datetime.now()
        for i in range(months):
            month_date = base_date + timedelta(days=30*i)
            month_str = month_date.strftime(month_format)
            url = url_pattern.format(month_str=month_str)
            
            print(f"  Month {i+1}: {url}")
            html = self._fetch_page(url)
            result = self._extract_events(html, url)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < months - 1:
                time.sleep(2)
        
        return all_events
    
    def _paginate_calendar_month(self) -> List[Dict[str, Any]]:
        """Calendar month URLs with date injection (tca/gilbert pattern)."""
        all_events = []
        months = self.config.get('months', 3)
        url_pattern = self.config['url_pattern']
        inject_dates = self.config.get('inject_dates', False)
        
        base_date = datetime.now()
        for i in range(months):
            month_date = base_date + timedelta(days=30*i)
            url = url_pattern.format(month=month_date.month, year=month_date.year)
            month_hint = f"{self.name} - {month_date.strftime('%B %Y')}"
            
            print(f"  Month {i+1}: {url}")
            html = self._fetch_page(url)
            
            if inject_dates:
                from llm_scrape_core import clean_html, ask_llm
                text = clean_html(html)
                month_name = month_date.strftime('%B')
                days_in_month = cal_mod.monthrange(month_date.year, month_date.month)[1]
                
                for day in range(1, days_in_month + 1):
                    text = re.sub(rf'(?m)^{day}$', f'{month_name} {day}, {month_date.year}:', text)
                
                print(f"    text={len(text)} chars", end='  ')
                result = ask_llm(text, current_url=url, site_hint=month_hint)
            else:
                result = self._extract_events(html, url)
            
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if i < months - 1:
                time.sleep(2)
        
        return all_events
    
    def _paginate_js_button(self) -> List[Dict[str, Any]]:
        """Click JavaScript pagination button."""
        from llm_scrape_core import get_driver, close_driver, clean_html, ask_llm
        
        all_events = []
        close_driver()
        driver = get_driver()
        
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'acceptLanguage': 'en-US,en;q=0.9',
            'platform': 'Win32',
        })
        
        try:
            driver.get(self.start_url)
        except Exception:
            pass
        time.sleep(self.wait)
        
        for page_num in range(1, self.max_pages + 1):
            if self.config.get('scroll_before'):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            text = clean_html(driver.page_source)
            print(f"  page {page_num}: text={len(text)} chars", end='  ')
            result = ask_llm(text, current_url=self.start_url, site_hint=self.name)
            page_events = result.get('events', [])
            all_events.extend(page_events)
            print(f"events={len(page_events)}")
            
            if not self._click_next_button(driver):
                break
            time.sleep(3)
        
        close_driver()
        return all_events
    
    def _click_next_button(self, driver) -> bool:
        """Click next button based on config, return False if last page."""
        try:
            button_selector = self.config['button_selector']
            
            if self.config.get('check_style'):
                # azmnh pattern: check parent style
                next_btn = driver.find_element(By.CSS_SELECTOR, button_selector)
                parent = driver.find_element(By.CSS_SELECTOR, self.config['parent_selector'])
                style = parent.get_attribute('style') or ''
                if 'display: none' in style or 'display:none' in style:
                    print(f"    Last page reached")
                    return False
                driver.execute_script("arguments[0].click();", next_btn)
            
            elif 'button_index' in self.config:
                # phoenix pattern: click Nth button
                btns = driver.find_elements(By.CSS_SELECTOR, button_selector)
                idx = self.config['button_index']
                if len(btns) <= idx or btns[idx].get_attribute('disabled'):
                    print(f"    Last page reached")
                    return False
                driver.execute_script("arguments[0].click();", btns[idx])
            
            else:
                # Simple click
                next_btn = driver.find_element(By.CSS_SELECTOR, button_selector)
                driver.execute_script("arguments[0].click();", next_btn)
            
            return True
        
        except Exception as e:
            print(f"    Pagination ended: {e}")
            return False
```

#### File: `llm_scraper.py` (Modified for Config-Driven)

```python
"""
llm_scraper.py -- Production LLM-based event scraper (Config-Driven version)
"""

import sys, time, re
from datetime import datetime, timedelta
from database.models import Session, Event, ScraperRun
from llm_scrape_core import close_driver, SITES
from pagination_engine import PaginationEngine


# Date parsing function (unchanged from previous versions)
def parse_date(date_str: str | None, time_str: str | None) -> datetime:
    """Convert LLM-returned date/time strings to a datetime object."""
    # ... same implementation as before ...
    pass


def scrape_and_save(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    pagination_config: dict,
    session
) -> tuple[int, int, bool, str | None]:
    """
    Scrape one site via LLM extraction and save new events to the database.
    
    Uses config-driven pagination engine.
    """
    all_events = []
    error_message = None
    success = True
    
    try:
        # Create pagination engine with config
        engine = PaginationEngine(
            key, name, start_url, use_selenium, wait, max_pages, pagination_config
        )
        
        # Execute pagination
        all_events = engine.paginate()
    
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"  ERROR: {e}")
    
    # Save to database (same as before)
    events_added = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for ev in all_events:
        event_dt = parse_date(ev.get('date'), ev.get('time'))
        title = (ev.get('title') or '').strip()
        if not title:
            continue
        
        end_date_str = ev.get('end_date')
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')
                if event_dt < today and end_dt >= today:
                    event_dt = today
            except ValueError:
                pass
        
        existing = session.query(Event).filter_by(title=title, date=event_dt).first()
        if not existing:
            url = (ev.get('url') or '').strip()
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(start_url, url)
            
            session.add(Event(
                title=title,
                description=(ev.get('description') or '').strip(),
                venue=(ev.get('venue') or '').strip(),
                date=event_dt,
                url=url,
                source=key,
                category='general',
            ))
            events_added += 1
    
    session.commit()
    return len(all_events), events_added, success, error_message


def main():
    # ... same CLI handling as before ...
    
    session = Session()
    
    try:
        # ... same purge logic ...
        
        for key in keys:
            name, url, use_sel, wait, max_pages, note, _color, pagination_config = SITES[key]
            print(f"\n{'='*60}")
            print(f"SCRAPING: {name}")
            if note:
                print(f"NOTE: {note}")
            print(f"{'='*60}")
            
            start_time = time.time()
            found, added, success, error = scrape_and_save(
                key, name, url, use_sel, wait, max_pages, pagination_config, session
            )
            duration = time.time() - start_time
            
            # ... same ScraperRun logging ...
    
    finally:
        close_driver()
        session.close()


if __name__ == '__main__':
    main()
```

### Before/After Comparison

**Before:**
- 250 lines of pagination logic in scrape_and_save()
- Hardcoded if/elif blocks
- Adding new site requires code changes

**After:**
- `scrape_and_save()`: 60 lines
- `pagination_engine.py`: 200 lines (reusable)
- `sources.py`: Extended with config dicts
- Adding new site: just add config to SITES dict

### Migration Steps

1. **Backup files:**
   ```bash
   cp llm_scraper.py llm_scraper.py.backup
   cp sources.py sources.py.backup
   ```

2. **Create pagination_engine.py** (copy code from above)

3. **Update sources.py** with pagination configs (see extended SITES dict above)

4. **Update llm_scraper.py** to use PaginationEngine

5. **Test each pagination type:**
   ```bash
   python _test_llm_scrape.py dirtydrummer
   python _test_llm_scrape.py azmnh
   python _test_llm_scrape.py chandler_lib
   ```

6. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

### Testing Checklist

- [ ] All 8 pagination patterns work correctly
- [ ] Config validation catches invalid configs
- [ ] New sites can be added via config only
- [ ] No regressions in event extraction
- [ ] ScraperRun records created correctly

### Adding a New Site

**Example: Adding a site with `/events/page-N` pagination**

1. **Add to sources.py SITES dict:**
   ```python
   'newsite': (
       'New Site Name',
       'https://example.com/events',
       True, 5, 5, '',
       ('#e0f2fe', '#0284c7', '#0c4a6e'),
       {
           'type': 'url_regex',
           'pattern': r'/events',
           'replacement': '/events/page-{page_num}',
           'start_index': 1,
       },
   ),
   ```

2. **Test:**
   ```bash
   python _test_llm_scrape.py newsite
   ```

3. **Done!** No code changes needed.

---

## Comparison Matrix

### Detailed Feature Comparison

| Feature | Hybrid Minimal | Strategy Pattern | Config-Driven |
|---------|---------------|------------------|---------------|
| **Code Organization** |
| Total Lines | ~350 | ~450 | ~400 |
| Files Modified | 1 | 1 | 2 |
| Files Created | 0 | 7 | 1 |
| Main Function Size | 80 lines | 60 lines | 60 lines |
| **Maintainability** |
| Code Duplication | Low | None | None |
| Separation of Concerns | Good | Excellent | Excellent |
| Testability | Good | Excellent | Good |
| Documentation Needs | Low | Medium | Low |
| **Extensibility** |
| Add New Pattern | New function | New class | New engine method |
| Add New Site (existing pattern) | Edit if/elif | Edit factory | Add config |
| Modify Pattern | Edit function | Edit class | Edit engine |
| **Learning Curve** |
| Python Knowledge | Basic | Intermediate | Basic |
| Pattern Knowledge | None | OOP patterns | Config structures |
| Time to Understand | 30 min | 2 hours | 1 hour |
| **Performance** |
| Runtime Overhead | None | Minimal | Minimal |
| Memory Usage | Low | Low | Low |
| **Risk** |
| Migration Complexity | Low | Medium | Medium |
| Breaking Changes | Low | Medium | Low |
| Rollback Difficulty | Easy | Medium | Easy |

### Code Size Breakdown

#### Hybrid Minimal
```
llm_scraper.py:
  - parse_date(): 30 lines
  - _paginate_multi_month(): 50 lines
  - _paginate_js_button(): 60 lines
  - _paginate_url_pattern(): 40 lines
  - scrape_and_save(): 80 lines
  - main(): 60 lines
  Total: ~320 lines
```

#### Strategy Pattern
```
pagination/__init__.py: 5 lines
pagination/base.py: 40 lines
pagination/multi_month.py: 80 lines
pagination/js_button.py: 70 lines
pagination/url_pattern.py: 60 lines
pagination/llm_detected.py: 50 lines
pagination/factory.py: 30 lines
llm_scraper.py: 120 lines
Total: ~455 lines
```

#### Config-Driven
```
sources.py (extended): +100 lines
pagination_engine.py: 200 lines
llm_scraper.py: 120 lines
Total: ~420 lines
```

### Pros and Cons

#### Hybrid Minimal

**Pros:**
- Minimal disruption to existing code
- Easy to understand and review
- Quick to implement (1-2 hours)
- Low risk of introducing bugs
- No new dependencies or patterns

**Cons:**
- Still some code duplication
- Helper functions in same file
- Adding new pattern requires code changes
- Less formal structure

**Best For:**
- Quick wins and immediate cleanup
- Small teams or solo developers
- Projects with stable pagination patterns
- When time is limited

#### Strategy Pattern

**Pros:**
- Clean OOP design
- Each strategy fully isolated
- Easy to unit test each pattern
- Follows SOLID principles
- Scales well to many patterns
- Clear extension points

**Cons:**
- More files to navigate
- Requires OOP knowledge
- Higher initial complexity
- Longer implementation time (4-6 hours)
- May be overkill for 8 patterns

**Best For:**
- Growing projects (10+ sites expected)
- Teams familiar with design patterns
- When testability is critical
- Long-term maintainability priority

#### Config-Driven

**Pros:**
- Add sites without code changes
- Config is self-documenting
- Single engine to maintain
- Balance of simplicity and power
- Easy to validate configs

**Cons:**
- Config can get complex
- Engine has all pattern logic
- Harder to add truly novel patterns
- Config errors only caught at runtime

**Best For:**
- Frequent site additions
- Non-developers adding sites
- When patterns are well-defined
- Balance between flexibility and simplicity

---

## Migration Guide

### Pre-Migration Checklist

Before starting any refactoring:

- [ ] Backup current codebase
- [ ] Document current scraping results (baseline)
- [ ] Ensure all tests pass
- [ ] Check database has recent data
- [ ] Review open issues/bugs
- [ ] Schedule maintenance window if needed

### Universal Migration Steps

These steps apply to all three options:

#### 1. Create Baseline

```bash
# Run current scraper and save results
python llm_scraper.py --no-purge > baseline_output.txt

# Export current database
sqlite3 events.db ".dump" > baseline_db.sql

# Count events per source
sqlite3 events.db "SELECT source, COUNT(*) FROM events GROUP BY source;"
```

#### 2. Create Backup

```bash
# Backup files
cp llm_scraper.py llm_scraper.py.backup
cp sources.py sources.py.backup
cp llm_scrape_core.py llm_scrape_core.py.backup

# Backup database
cp events.db events.db.backup
```

#### 3. Implement Changes

Follow option-specific steps below.

#### 4. Test Individual Sites

```bash
# Test each pagination type
python _test_llm_scrape.py dirtydrummer  # Multi-month
python _test_llm_scrape.py azmnh         # JS button
python _test_llm_scrape.py chandler_lib  # URL pattern
python _test_llm_scrape.py fibber        # LLM detected
```

#### 5. Run Full Scrape

```bash
# Clear database and run full scrape
python llm_scraper.py > migration_output.txt
```

#### 6. Validate Results

```bash
# Compare event counts
sqlite3 events.db "SELECT source, COUNT(*) FROM events GROUP BY source;"

# Check for errors in output
grep -i error migration_output.txt

# Verify health dashboard
python server/app.py
# Visit http://localhost:5000/health
```

#### 7. Rollback if Needed

```bash
# Restore backups
cp llm_scraper.py.backup llm_scraper.py
cp sources.py.backup sources.py
cp events.db.backup events.db
```

---

### Option 1: Hybrid Minimal Migration

**Time Estimate:** 1-2 hours

#### Step-by-Step

1. **Review helper functions** in Option 1 section above

2. **Add helper functions to llm_scraper.py:**
   - Copy `_paginate_multi_month()`
   - Copy `_paginate_js_button()`
   - Copy `_paginate_url_pattern()`
   - Place after `parse_date()` function

3. **Replace scrape_and_save() body:**
   - Keep function signature
   - Replace if/elif blocks with routing logic
   - Keep database save logic unchanged

4. **Test incrementally:**
   ```bash
   # Test one site at a time
   python _test_llm_scrape.py dirtydrummer
   python _test_llm_scrape.py azmnh
   python _test_llm_scrape.py chandler_lib
   ```

5. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

6. **Compare results:**
   ```bash
   diff baseline_output.txt migration_output.txt
   ```

#### Rollback Plan

Simple file restore:
```bash
cp llm_scraper.py.backup llm_scraper.py
```

---

### Option 2: Strategy Pattern Migration

**Time Estimate:** 4-6 hours

#### Step-by-Step

1. **Create pagination package:**
   ```bash
   mkdir pagination
   touch pagination/__init__.py
   ```

2. **Create strategy files in order:**
   - `pagination/base.py` (foundation)
   - `pagination/llm_detected.py` (simplest)
   - `pagination/url_pattern.py`
   - `pagination/multi_month.py`
   - `pagination/js_button.py`
   - `pagination/factory.py` (last)

3. **Test each strategy as you create it:**
   ```bash
   # After creating llm_detected.py
   python -c "from pagination.llm_detected import LLMDetectedStrategy; print('OK')"
   ```

4. **Update llm_scraper.py:**
   - Add import: `from pagination import get_pagination_strategy`
   - Simplify `scrape_and_save()` to use factory
   - Keep database logic unchanged

5. **Test each pagination type:**
   ```bash
   python _test_llm_scrape.py fibber        # LLM detected
   python _test_llm_scrape.py chandler_lib  # URL pattern
   python _test_llm_scrape.py dirtydrummer  # Multi-month
   python _test_llm_scrape.py azmnh         # JS button
   ```

6. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

#### Rollback Plan

Remove pagination package and restore file:
```bash
rm -rf pagination/
cp llm_scraper.py.backup llm_scraper.py
```

---

### Option 3: Config-Driven Migration

**Time Estimate:** 3-4 hours

#### Step-by-Step

1. **Create pagination_engine.py:**
   - Copy complete implementation from Option 3 section
   - Test import: `python -c "from pagination_engine import PaginationEngine; print('OK')"`

2. **Extend sources.py gradually:**
   - Start with one site: add pagination_config dict
   - Test that site works
   - Add remaining sites one by one

3. **Update llm_scraper.py:**
   - Add import: `from pagination_engine import PaginationEngine`
   - Update SITES unpacking to include pagination_config
   - Update `scrape_and_save()` signature and body

4. **Test incrementally:**
   ```bash
   # After adding config for each site
   python _test_llm_scrape.py <site_key>
   ```

5. **Validate all configs:**
   ```python
   # Create validation script
   from sources import SITES
   for key, entry in SITES.items():
       config = entry[7]
       assert 'type' in config, f"{key}: missing 'type'"
       print(f"{key}: {config['type']} ✓")
   ```

6. **Run full scrape:**
   ```bash
   python llm_scraper.py --no-purge
   ```

#### Rollback Plan

Restore both files:
```bash
cp llm_scraper.py.backup llm_scraper.py
cp sources.py.backup sources.py
rm pagination_engine.py
```

---

### Post-Migration Validation

After completing any migration:

#### 1. Functional Tests

```bash
# Test all pagination types
for site in dirtydrummer azmnh chandler_lib mesa chandler tca gilbert fibber; do
    echo "Testing $site..."
    python _test_llm_scrape.py $site
done
```

#### 2. Data Validation

```sql
-- Check event counts per source
SELECT source, COUNT(*) as count 
FROM events 
GROUP BY source 
ORDER BY count DESC;

-- Check for missing data
SELECT source, COUNT(*) as count 
FROM events 
WHERE title IS NULL OR date IS NULL
GROUP BY source;

-- Check date ranges
SELECT source, MIN(date) as earliest, MAX(date) as latest
FROM events
GROUP BY source;
```

#### 3. Health Dashboard

```bash
python server/app.py
# Visit http://localhost:5000/health
# Verify:
# - All sources show recent runs
# - Success rates are high
# - Event counts are reasonable
```

#### 4. Performance Check

```bash
# Time full scrape
time python llm_scraper.py --no-purge

# Compare to baseline timing
# Should be within 10% of original
```

#### 5. Error Log Review

```bash
# Check for new errors
grep -i error migration_output.txt
grep -i exception migration_output.txt

# Compare to baseline
diff <(grep -i error baseline_output.txt) <(grep -i error migration_output.txt)
```

---

## Testing Strategy

### Test Levels

#### 1. Unit Tests (Strategy Pattern Only)

Create `tests/test_pagination.py`:

```python
"""
Unit tests for pagination strategies
"""

import pytest
from unittest.mock import Mock, patch
from pagination.url_pattern import URLPatternStrategy
from pagination.multi_month import MultiMonthStrategy


class TestURLPatternStrategy:
    """Test URL pattern pagination."""
    
    def test_chandler_lib_url_building(self):
        """Test BiblioCommons &page=N pattern."""
        strategy = URLPatternStrategy(
            key='chandler_lib',
            name='Test',
            start_url='https://example.com/events?start=2024-01-01',
            use_selenium=False,
            wait=0,
            max_pages=3
        )
        
        # Mock the fetch and extract methods
        strategy._fetch_page = Mock(return_value='<html></html>')
        strategy._extract_events = Mock(return_value={'events': [{'title': 'Test'}]})
        
        events = strategy.paginate()
        
        # Verify correct number of calls
        assert strategy._fetch_page.call_count <= 3
        assert len(events) > 0
    
    def test_mesa_regex_substitution(self):
        """Test regex URL substitution for mesa."""
        strategy = URLPatternStrategy(
            key='mesa',
            name='Test',
            start_url='https://example.com/events?pageindex=1',
            use_selenium=False,
            wait=0,
            max_pages=2
        )
        
        # Test URL building
        url = strategy._build_url(2)
        assert 'pageindex=2' in url


class TestMultiMonthStrategy:
    """Test multi-month pagination."""
    
    def test_dirtydrummer_url_generation(self):
        """Test month URL generation."""
        strategy = MultiMonthStrategy(
            key='dirtydrummer',
            name='Test',
            start_url='https://example.com/events',
            use_selenium=False,
            wait=0,
            max_pages=3
        )
        
        strategy._fetch_page = Mock(return_value='<html></html>')
        strategy._extract_events = Mock(return_value={'events': []})
        
        events = strategy.paginate()
        
        # Should fetch 3 months
        assert strategy._fetch_page.call_count == 3


# Run tests
# pytest tests/test_pagination.py -v
```

#### 2. Integration Tests

Create `tests/test_integration.py`:

```python
"""
Integration tests for full scraping workflow
"""

import pytest
from database.models import Session, Event
from llm_scraper import scrape_and_save


class TestScrapingIntegration:
    """Test full scraping workflow."""
    
    @pytest.fixture
    def session(self):
        """Create test database session."""
        session = Session()
        yield session
        session.close()
    
    def test_scrape_fibber(self, session):
        """Test scraping Fibber Magees (LLM detected pagination)."""
        found, added, success, error = scrape_and_save(
            key='fibber',
            name='Fibber Magees',
            start_url='https://www.fibbermageespub.com/fibber-magees-events',
            use_selenium=False,
            wait=3,
            max_pages=2,
            session=session
        )
        
        assert success is True
        assert error is None
        assert found >= 0
        assert added >= 0
    
    def test_scrape_with_error_handling(self, session):
        """Test error handling for invalid URL."""
        found, added, success, error = scrape_and_save(
            key='test',
            name='Test',
            start_url='https://invalid-url-that-does-not-exist.com',
            use_selenium=False,
            wait=0,
            max_pages=1,
            session=session
        )
        
        assert success is False
        assert error is not None


# Run tests
# pytest tests/test_integration.py -v
```

#### 3. Manual Test Cases

**Test Case 1: Multi-Month Pagination**
```bash
# Test dirtydrummer
python _test_llm_scrape.py dirtydrummer

# Expected:
# - 3 month URLs generated
# - Events from current + next 2 months
# - No duplicate events
```

**Test Case 2: JS Button Pagination**
```bash
# Test azmnh
python _test_llm_scrape.py azmnh

# Expected:
# - Selenium driver starts
# - Multiple pages clicked
# - Stops when "display: none" detected
```

**Test Case 3: URL Pattern Pagination**
```bash
# Test chandler_lib
python _test_llm_scrape.py chandler_lib

# Expected:
# - URLs with &page=1, &page=2, etc.
# - Stops when no events found
```

**Test Case 4: LLM-Detected Pagination**
```bash
# Test fibber
python _test_llm_scrape.py fibber

# Expected:
# - LLM extracts next_page_url
# - Follows links until null
# - Loop detection works
```

#### 4. Regression Test Suite

Create `tests/test_regression.py`:

```python
"""
Regression tests to ensure refactoring doesn't break existing functionality
"""

import pytest
from database.models import Session, Event
from datetime import datetime


class TestRegression:
    """Regression tests for refactoring."""
    
    @pytest.fixture
    def session(self):
        session = Session()
        yield session
        session.close()
    
    def test_all_sites_scrape_without_errors(self, session):
        """Test that all sites can be scraped without exceptions."""
        from sources import SITES
        from llm_scraper import scrape_and_save
        
        errors = []
        for key, (name, url, use_sel, wait, max_pages, note, color, *rest) in SITES.items():
            try:
                pagination_config = rest[0] if rest else {'type': 'llm_detected'}
                found, added, success, error = scrape_and_save(
                    key, name, url, use_sel, wait, 1,  # Only 1 page for speed
                    pagination_config if len(rest) > 0 else session,
                    session if len(rest) > 0 else None
                )
                if not success:
                    errors.append(f"{key}: {error}")
            except Exception as e:
                errors.append(f"{key}: {str(e)}")
        
        assert len(errors) == 0, f"Errors: {errors}"
    
    def test_event_deduplication(self, session):
        """Test that duplicate events are not created."""
        from llm_scraper import scrape_and_save
        
        # Scrape twice
        scrape_and_save('fibber', 'Test', 'https://example.com', False, 0, 1, session)
        count1 = session.query(Event).filter_by(source='fibber').count()
        
        scrape_and_save('fibber', 'Test', 'https://example.com', False, 0, 1, session)
        count2 = session.query(Event).filter_by(source='fibber').count()
        
        # Should not create duplicates
        assert count1 == count2
```

#### 5. Performance Tests

Create `tests/test_performance.py`:

```python
"""
Performance tests to ensure refactoring doesn't slow down scraping
"""

import time
import pytest
from llm_scraper import scrape_and_save
from database.models import Session


class TestPerformance:
    """Performance regression tests."""
    
    def test_scraping_speed(self):
        """Test that scraping completes within reasonable time."""
        session = Session()
        
        start = time.time()
        scrape_and_save(
            'fibber', 'Test', 'https://www.fibbermageespub.com/fibber-magees-events',
            False, 3, 2, session
        )
        duration = time.time() - start
        
        # Should complete within 30 seconds for 2 pages
        assert duration < 30, f"Scraping took {duration}s (expected < 30s)"
        
        session.close()
```

---

### Test Execution Plan

#### Phase 1: Pre-Migration Testing (Baseline)

```bash
# 1. Run current scraper and time it
time python llm_scraper.py --no-purge > baseline_results.txt

# 2. Count events
sqlite3 events.db "SELECT source, COUNT(*) FROM events GROUP BY source;" > baseline_counts.txt

# 3. Check for errors
grep -i error baseline_results.txt > baseline_errors.txt
```

#### Phase 2: Post-Migration Testing

```bash
# 1. Run refactored scraper
time python llm_scraper.py --no-purge > migration_results.txt

# 2. Count events
sqlite3 events.db "SELECT source, COUNT(*) FROM events GROUP BY source;" > migration_counts.txt

# 3. Check for errors
grep -i error migration_results.txt > migration_errors.txt

# 4. Compare results
diff baseline_counts.txt migration_counts.txt
diff baseline_errors.txt migration_errors.txt
```

#### Phase 3: Automated Testing (If using Strategy Pattern)

```bash
# Install pytest
pip install pytest pytest-cov

# Run unit tests
pytest tests/test_pagination.py -v

# Run integration tests
pytest tests/test_integration.py -v

# Run regression tests
pytest tests/test_regression.py -v

# Run with coverage
pytest tests/ --cov=pagination --cov=llm_scraper --cov-report=html
```

#### Phase 4: Manual Verification

1. **Health Dashboard Check:**
   ```bash
   python server/app.py
   # Visit http://localhost:5000/health
   # Verify all sources show recent successful runs
   ```

2. **Spot Check Events:**
   ```bash
   # Check a few events manually
   sqlite3 events.db "SELECT title, date, source FROM events LIMIT 10;"
   ```

3. **Test Each Pagination Type:**
   ```bash
   python _test_llm_scrape.py dirtydrummer  # Multi-month
   python _test_llm_scrape.py azmnh         # JS button
   python _test_llm_scrape.py chandler_lib  # URL append
   python _test_llm_scrape.py mesa          # URL regex
   python _test_llm_scrape.py fibber        # LLM detected
   ```

---

### Acceptance Criteria

Migration is successful when:

- [ ] All sites scrape without errors
- [ ] Event counts match baseline (±5%)
- [ ] No duplicate events created
- [ ] Scraping time within 10% of baseline
- [ ] Health dashboard shows all green
- [ ] Manual spot checks pass
- [ ] No new error messages in logs
- [ ] Code is more maintainable than before
- [ ] Documentation is updated
- [ ] Team understands new structure

---

## Appendix

### A. Quick Reference: Pagination Patterns

| Pattern | Sites | Key Characteristic |
|---------|-------|-------------------|
| LLM Detected | fibber, rak, yuccatap | LLM extracts next_page_url |
| URL Append | chandler_lib, chandler | ?page=N or &page=N |
| URL Regex | mesa | Regex substitution in URL |
| Multi-Month | dirtydrummer | Generate month URLs |
| Calendar Month | tca, gilbert | Month URLs + date injection |
| JS Button | azmnh, phoenix | Click pagination button |

### B. Common Issues and Solutions

**Issue:** Events duplicated after refactoring
**Solution:** Check that deduplication logic (title + date) is still in place

**Issue:** Some sites return 0 events
**Solution:** Verify pagination config matches site's actual pattern

**Issue:** Selenium timeouts increased
**Solution:** Check that wait times and scroll_passes are preserved

**Issue:** LLM returns invalid next_page_url
**Solution:** Verify URL validation logic (must start with 'http')

### C. Future Enhancements

Potential improvements for any option:

1. **Pagination Config Validation:**
   - Add schema validation for configs
   - Catch errors at startup, not runtime

2. **Retry Logic:**
   - Add per-page retry for transient failures
   - Don't fail entire site if one page fails

3. **Progress Tracking:**
   - Show progress bar for multi-page scrapes
   - Estimate time remaining

4. **Parallel Scraping:**
   - Scrape multiple sites concurrently
   - Respect rate limits per site

5. **Pagination Auto-Detection:**
   - Let LLM suggest pagination pattern
   - Reduce manual configuration

---

## Conclusion

This guide provides three complete refactoring options for the pagination logic in `llm_scraper.py`:

1. **Hybrid Minimal:** Quick cleanup with helper functions (1-2 hours)
2. **Strategy Pattern:** Full OOP design for scalability (4-6 hours)
3. **Config-Driven:** Balance of simplicity and power (3-4 hours)

Each option includes:
- Complete working code for all files
- Before/after comparisons
- Step-by-step migration guide
- Comprehensive testing strategy
- Rollback procedures

Choose based on your priorities:
- **Speed:** Hybrid Minimal
- **Scale:** Strategy Pattern
- **Balance:** Config-Driven

All three options significantly improve code maintainability while preserving existing functionality.

---

**Document End**
