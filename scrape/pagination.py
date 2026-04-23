"""
pagination_engine.py -- Configuration-driven pagination for event scrapers

This module provides a unified pagination system that handles all scraping patterns
through declarative configuration rather than procedural code. Adding a new scraper
requires only adding a config entry to sources.py -- no code changes needed.

DESIGN PHILOSOPHY
-----------------
Instead of writing custom pagination code for each site, we define pagination
behavior through configuration. The engine interprets these configs and executes
the appropriate fetch/parse/paginate strategy.

SUPPORTED PAGINATION TYPES
---------------------------
1. 'llm'           - LLM extracts next_page_url from page content (default)
2. 'multi_month'   - Scrape N months by generating month-based URLs
3. 'url_param'     - Increment URL parameter (?page=N, &page=N, pageindex=N)
4. 'js_button'     - Click JavaScript pagination buttons (no URL change)
5. 'calendar_grid' - Month-view calendar with date injection for LLM context

ADDING A NEW SCRAPER
--------------------
1. Add entry to sources.py SITES dict with pagination config
2. Run: python llm_scraper.py <your_key>
3. Done!

See HOW_TO_ADD_SCRAPERS.md for detailed examples.
"""

import re, time, calendar as cal_mod
from datetime import datetime, timedelta
from typing import Callable
from selenium.webdriver.common.by import By
from llm_scrape_core import (
    fetch_requests, fetch_selenium, close_driver, get_driver,
    clean_html, ask_llm, _SPOOF_UA
)
from sources import TRIM_PATTERNS
import logging

log = logging.getLogger(__name__)


def apply_trim(text: str, site_key: str) -> str:
    """
    Strip boilerplate from cleaned HTML text using site-specific patterns.

    TRIM_PATTERNS value can be:
      - str:         head trim only  — strip everything before (and including) the pattern
      - (str, str):  head + tail     — also strip everything from the tail pattern to end
      - None:        no trimming
    """
    pattern = TRIM_PATTERNS.get(site_key)
    if not pattern:
        return text

    head, tail = (pattern, None) if isinstance(pattern, str) else pattern

    before = len(text)
    if head and head in text:
        text = text[text.index(head) + len(head):]
    if tail and tail in text:
        text = text[:text.index(tail)]

    removed = before - len(text)
    if removed:
        log.debug(f"[{site_key}] trim: {removed:,} chars removed, {len(text):,} remain")
    return text


# ===========================================================================
# Pagination Handlers
# ===========================================================================

def _paginate_multi_month(
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    config: dict,
    site_name: str
):
    """Multi-month pagination: Generate URLs for N consecutive months.

    url_template supports {month}, {year}, and {month_name} (lowercase).
    """
    months = config.get('months', 3)
    url_template = config.get('url_template')

    if not url_template:
        raise ValueError(f"multi_month pagination requires 'url_template' in config")

    print(f"  Multi-month scraping: {months} months")

    import calendar as _cal
    base_date = datetime.now()
    for i in range(months):
        month_date = base_date + timedelta(days=30 * i)
        url = url_template.format(
            month=month_date.month, year=month_date.year,
            month_name=_cal.month_name[month_date.month].lower(),
        )
        
        print(f"  Month {i+1}: {url}")
        
        try:
            if use_selenium:
                html = fetch_selenium(url, wait)
            else:
                html = fetch_requests(url)
            
            yield (url, html, i + 1)
            
            if i < months - 1:
                time.sleep(2)
                
        except Exception as e:
            print(f"\n    ERROR on month {i+1}: {e}")
            if i == 0:
                raise
            break


def _paginate_url_param(
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    config: dict,
    site_name: str
):
    """URL parameter pagination: Increment a query parameter for each page."""
    param_name = config.get('param_name', 'page')
    start_index = config.get('start_index', 1)
    param_pattern = config.get('param_pattern')

    if not param_pattern:
        param_pattern = rf'{param_name}=\d+'
    
    print(f"  Explicit pagination: {max_pages} pages")
    
    for page_num in range(max_pages):
        page_index = start_index + page_num
        
        if page_num == 0 and start_index == 1:
            url = start_url
        else:
            if re.search(param_pattern, start_url):
                url = re.sub(param_pattern, f'{param_name}={page_index}', start_url)
            else:
                separator = '&' if '?' in start_url else '?'
                url = f"{start_url}{separator}{param_name}={page_index}"
        
        print(f"  Page {page_num}: {url}")
        
        try:
            if use_selenium:
                html = fetch_selenium(url, wait)
            else:
                html = fetch_requests(url)
            
            yield (url, html, page_num)
            
            if page_num < max_pages - 1:
                time.sleep(2)
                
        except Exception as e:
            print(f"\n    ERROR on page {page_num}: {e}")
            if page_num == 0:
                raise
            break


def _paginate_js_button(
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    config: dict,
    site_name: str
):
    """JavaScript button pagination: Click buttons to navigate pages."""
    from selenium.webdriver.common.by import By
    
    button_selector = config.get('button_selector')
    disabled_check = config.get('disabled_check', 'attribute')
    scroll_before_click = config.get('scroll_before_click', False)
    wait_after_click = config.get('wait_after_click', 3)
    
    if not button_selector:
        raise ValueError(f"js_button pagination requires 'button_selector' in config")
    
    print(f"  JS button pagination: {max_pages} pages max")
    
    close_driver()
    driver = get_driver()
    
    # CDP user-agent spoofing
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        'userAgent': _SPOOF_UA,
        'acceptLanguage': 'en-US,en;q=0.9',
        'platform': 'Win32',
    })
    
    try:
        driver.get(start_url)
    except Exception:
        pass
    time.sleep(wait)
    
    for page_num in range(max_pages):
        if scroll_before_click and page_num > 0:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        
        html = driver.page_source
        print(f"  Page {page_num}: {start_url}")
        
        yield (start_url, html, page_num)
        
        if page_num < max_pages - 1:
            try:
                if disabled_check == 'style':
                    # Check parent element for display:none style
                    next_btn = driver.find_element(By.CSS_SELECTOR, button_selector)
                    parent = next_btn.find_element(By.XPATH, '..')
                    style = parent.get_attribute('style') or ''
                    if 'display: none' in style or 'display:none' in style:
                        print(f"    Last page reached (style check)")
                        break
                    driver.execute_script("arguments[0].click();", next_btn)
                elif disabled_check == 'attribute':
                    # Check for disabled attribute
                    btns = driver.find_elements(By.CSS_SELECTOR, button_selector)
                    if len(btns) < 2 or btns[1].get_attribute('disabled'):
                        print(f"    Last page reached (disabled check)")
                        break
                    driver.execute_script("arguments[0].click();", btns[1])
                else:
                    # Simple click
                    next_btn = driver.find_element(By.CSS_SELECTOR, button_selector)
                    driver.execute_script("arguments[0].click();", next_btn)
                
                time.sleep(wait_after_click)
            except Exception as e:
                print(f"    Pagination ended: {e}")
                break
    
    close_driver()


def _paginate_calendar_grid(
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    config: dict,
    site_name: str
):
    """Calendar grid pagination: Month-view calendar with date injection."""
    months = config.get('months', 3)
    url_template = config.get('url_template')
    inject_dates = config.get('inject_dates', False)
    
    if not url_template:
        raise ValueError(f"calendar_grid pagination requires 'url_template' in config")
    
    print(f"  Calendar grid scraping: {months} months")
    
    base_date = datetime.now()
    for i in range(months):
        month_date = base_date + timedelta(days=30 * i)
        url = url_template.format(month=month_date.month, year=month_date.year)
        
        print(f"  Month {i+1}: {url}")
        
        try:
            if use_selenium:
                html = fetch_selenium(url, wait)
            else:
                html = fetch_requests(url)
            
            # Inject full dates if requested
            if inject_dates:
                text = clean_html(html)
                month_name = month_date.strftime('%B')
                days_in_month = cal_mod.monthrange(month_date.year, month_date.month)[1]
                
                for day in range(1, days_in_month + 1):
                    text = re.sub(rf'(?m)^{day}$', f'{month_name} {day}, {month_date.year}:', text)
                
                # Reconstruct HTML-like structure for consistency
                html = f"<html><body>{text}</body></html>"
            
            yield (url, html, i + 1)
            
            if i < months - 1:
                time.sleep(2)
                
        except Exception as e:
            print(f"\n    ERROR on month {i+1}: {e}")
            if i == 0:
                raise
            break


# ===========================================================================
# Handler Registry
# ===========================================================================

_HANDLERS = {
    'multi_month': _paginate_multi_month,
    'url_param': _paginate_url_param,
    'js_button': _paginate_js_button,
    'calendar_grid': _paginate_calendar_grid,
}


# ===========================================================================
# Main Scraping Function
# ===========================================================================

def scrape_with_pagination(
    key: str,
    name: str,
    start_url: str,
    use_selenium: bool,
    wait: int,
    max_pages: int,
    pagination_config: dict | None,
    provider: str = None,
) -> list[dict]:
    """
    Main pagination engine entry point.
    
    Args:
        key: Site key (e.g., 'fibber', 'chandler')
        name: Display name for logging
        start_url: Starting URL
        use_selenium: Whether to use Selenium vs requests
        wait: Seconds to wait after page load
        max_pages: Maximum pages to scrape
        pagination_config: Pagination configuration dict or None for default LLM pagination
    
    Returns:
        List of event dictionaries extracted from all pages
    """
    all_events = []
    page_stats = []  # per-page: {page, url, events, text_chars, duration}

    # Default to LLM pagination if no config provided
    if not pagination_config:
        pagination_config = {'type': 'llm'}

    pagination_type = pagination_config.get('type', 'llm')

    print(f"  Pagination type: {pagination_type}")

    # Clear stale artifacts from prior runs, then save each stage as we go.
    # Disk errors are swallowed — artifact failures must not break scrapes.
    try:
        import artifact_store
        artifact_store.prepare_source_dir(key)
    except OSError as e:
        log.warning(f"Artifact dir prep failed: {e}")

    # Special handling for LLM pagination (loop-based, not generator)
    if pagination_type == 'llm':
        current_url = start_url
        visited = set()
        page_num = 0

        while current_url and page_num < max_pages:
            page_num += 1
            if current_url in visited:
                print(f"    Loop detected, stopping")
                break
            visited.add(current_url)

            print(f"  Page {page_num}: {current_url[:80]}")
            page_t0 = time.time()

            try:
                if use_selenium:
                    html = fetch_selenium(current_url, wait, scroll_passes=10)
                else:
                    html = fetch_requests(current_url)

                text = apply_trim(clean_html(html), key)
                print(f"    text={len(text)} chars", end='  ')

                try:
                    artifact_store.save(key, f'page_{page_num}_raw.html', html)
                    artifact_store.save(key, f'page_{page_num}_cleaned.txt', text)
                except OSError as e:
                    log.warning(f"Artifact write failed: {e}")

                result = ask_llm(text, current_url=current_url, site_hint=name,
                                 provider=provider,
                                 artifact_prefix=f'{key}/page_{page_num}')
                page_events = result.get('events', [])
                next_url = result.get('next_page_url')
                all_events.extend(page_events)
                print(f"events={len(page_events)}  next={next_url or 'null'}")

                page_stats.append({
                    'page': page_num, 'url': current_url,
                    'events': len(page_events), 'text_chars': len(text),
                    'duration': round(time.time() - page_t0, 1),
                })

                if next_url and not next_url.startswith('http'):
                    break
                current_url = next_url
                if current_url:
                    time.sleep(2)

            except Exception as e:
                print(f"\n    ERROR on page {page_num}: {e}")
                if page_num == 1:
                    raise
                break

    else:
        # Use handler from registry
        handler = _HANDLERS.get(pagination_type)
        if not handler:
            raise ValueError(f"Unknown pagination type: {pagination_type}")

        # Generator pattern: handler yields (url, html, page_num) tuples.
        # Use enumerate for artifact filenames because some handlers yield
        # 0-indexed page_num (url_param, js_button) while others yield 1-indexed.
        try:
            for artifact_page, (url, html, page_num) in enumerate(handler(
                start_url, use_selenium, wait, max_pages, pagination_config, name
            ), start=1):
                page_t0 = time.time()
                text = apply_trim(clean_html(html), key)
                print(f"    text={len(text)} chars", end='  ')

                try:
                    artifact_store.save(key, f'page_{artifact_page}_raw.html', html)
                    artifact_store.save(key, f'page_{artifact_page}_cleaned.txt', text)
                except OSError as e:
                    log.warning(f"Artifact write failed: {e}")

                result = ask_llm(text, current_url=url, site_hint=name,
                                 provider=provider,
                                 artifact_prefix=f'{key}/page_{artifact_page}')
                page_events = result.get('events', [])
                all_events.extend(page_events)
                print(f"events={len(page_events)}")

                page_stats.append({
                    'page': artifact_page, 'url': url,
                    'events': len(page_events), 'text_chars': len(text),
                    'duration': round(time.time() - page_t0, 1),
                })

        except Exception as e:
            print(f"\n    ERROR during pagination: {e}")
            if not all_events:
                raise

    # Write scrape-side summary (DB-side stats appended by scrape_and_save)
    try:
        import json as _json
        scrape_summary = {
            'source': key,
            'name': name,
            'pagination_type': pagination_type,
            'fetch_mode': 'selenium' if use_selenium else 'requests',
            'pages_scraped': len(page_stats),
            'events_from_llm': len(all_events),
            'per_page': page_stats,
        }
        artifact_store.save(key, 'run_summary.json', _json.dumps(scrape_summary, indent=2))
    except Exception as e:
        log.warning(f"Run summary write failed: {e}")

    return all_events
