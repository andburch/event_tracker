"""
sources.py -- Single source of truth for all scraped event sources.

Each entry in SITES defines everything about a source:
  - Scraping config  (url, selenium, wait, max_pages, pagination_config)
  - Display metadata (display_name, color)

Both llm_scrape_core.py and server/app.py import from here.
Adding a new site means editing only this file.

SITES entry format:
    key: (display_name, url, use_selenium, wait_secs, max_pages, note, color, pagination_config)

color: (background, border, text) CSS hex strings for calendar chips.
pagination_config: Dict defining pagination behavior (see pagination_engine.py for details)
    - If None or omitted: Uses default LLM pagination (LLM extracts next_page_url)
    - Otherwise: Dict with 'type' key and type-specific config
"""

from datetime import datetime, timedelta

_today  = datetime.now().strftime('%Y-%m-%d')
_plus90 = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

# ---------------------------------------------------------------------------
# Site registry
# ---------------------------------------------------------------------------
# use_selenium=True  -- site requires JavaScript to render events
# use_selenium=False -- static HTML, requests is sufficient (faster)
# wait_secs          -- sleep after page load; increase for slow/Akamai sites
# max_pages          -- safety cap on pagination depth
# note               -- documents quirks for future reference
# color              -- (background, border, text) for calendar chip display
# pagination_config  -- dict defining pagination behavior (None = default LLM pagination)
# ---------------------------------------------------------------------------

SITES = {
    # --- Music venues ---
    'fibber': (
        'Fibber Magees',
        'https://www.fibbermageespub.com/fibber-magees-events',
        False, 3, 5, '',
        ('#fff7ed', '#c2410c', '#7c2d12'),
        None,  # Default LLM pagination
    ),
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
    'yuccatap': (
        'Yucca Tap Room',
        'https://yuccatap.com/events',
        True, 8, 5, 'Squarespace infinite scroll',
        ('#fef2f2', '#b91c1c', '#450a0a'),
        None,  # Default LLM pagination
    ),

    # --- Government / community calendars ---
    'rak': (
        'Raising Arizona Kids',
        'https://www.raisingarizonakids.com/calendar/',
        True, 8, 5, 'WordPress /page/N/ pagination',
        ('#ecfeff', '#0891b2', '#164e63'),
        None,  # Default LLM pagination (LLM extracts /page/N/ URLs)
    ),
    'chandler': (
        'City of Chandler',
        'https://www.chandleraz.gov/events-result',
        True, 5, 10, '?page=N zero-indexed pagination',
        ('#fce7f3', '#db2777', '#831843'),
        {
            'type': 'url_param',
            'param_name': 'page',
            'start_index': 0,  # Zero-indexed
            'stop_on_empty': True
        },
    ),
    'scottsdale': (
        'City of Scottsdale',
        'https://community.scottsdaleaz.gov/scottsdaleaz_main/calendar',
        True, 8, 5, '',
        ('#fee2e2', '#dc2626', '#7f1d1d'),
        None,  # Default LLM pagination
    ),
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
    'mesa': (
        'City of Mesa',
        'https://www.mesaaz.gov/Events-directory?dlv_OC%20CL%20Public%20Events%20Listing=(=)(dd_OC%20Composite%20Date=Mar%2028%202026)(dd_OC%20Event%20Categories=Community%20Class%2FProgram|Groundbreaking-Ribbon%20Cutting|Special%20Event%2FFestival|Parks%2C%20Recreation%20and%20Community%20Facilities)(pageindex=1)',
        True, 6, 5, 'pageindex=N pagination, no times on events',
        ('#ede9fe', '#7c3aed', '#4c1d95'),
        {
            'type': 'url_param',
            'param_name': 'pageindex',
            'start_index': 1,
            'stop_on_empty': True
        },
    ),

    # --- Libraries ---
    'chandler_lib': (
        'Chandler Public Library',
        f'https://chandler.bibliocommons.com/v2/events?start={_today}&end={_plus90}',
        True, 5, 3, 'BiblioCommons - date range URL, &page=N pagination',
        ('#dcfce7', '#16a34a', '#14532d'),
        {
            'type': 'url_param',
            'param_name': 'page',
            'start_index': 1,
            'stop_on_empty': True
        },
    ),
    'tempe_lib': (
        'Tempe Public Library',
        f'https://tempepubliclibrary.libnet.info/events?start={_today}&end={_plus90}',
        True, 8, 5, 'date-range URL required',
        ('#d1fae5', '#059669', '#064e3b'),
        None,  # Default LLM pagination
    ),

    # --- Arts / museums ---
    'azmnh': (
        'AZ Museum of Natural History',
        'https://www.azmnh.org/azmnh-events',
        True, 5, 5, '',
        ('#ecfdf5', '#10b981', '#064e3b'),
        {
            'type': 'js_button',
            'button_selector': 'li.nextLink a.page-link',
            'disabled_check': 'style',  # Check parent li for display:none
            'scroll_before_click': False,
            'wait_after_click': 3
        },
    ),
    'chandler_center': (
        'Chandler Center for the Arts',
        'https://www.chandlercenter.org/events',
        True, 5, 5, '',
        ('#fdf4ff', '#a21caf', '#581c87'),
        None,  # Default LLM pagination
    ),
    'mesa_arts': (
        'Mesa Arts Center',
        'https://www.mesaartscenter.com/shows/',
        True, 5, 5, '',
        ('#fce7f3', '#be185d', '#500724'),
        None,  # Default LLM pagination
    ),
    'scottsdale_arts': (
        'Scottsdale Arts',
        'https://scottsdalearts.org/whats-on/?categories=performances,events,programs-workshops',
        True, 15, 5, 'Akamai bot detection + category filter URL',
        ('#ffe4e6', '#e11d48', '#881337'),
        None,  # Default LLM pagination
    ),
    'asu_kerr': (
        'ASU Kerr Cultural Center',
        'https://asukerr.com/events/',
        True, 5, 5, 'WordPress /page/N/ -- no per-event URLs',
        ('#fef3c7', '#d97706', '#78350f'),
        None,  # Default LLM pagination (LLM extracts /page/N/ URLs)
    ),
    'tca': (
        'Tempe Center for the Arts',
        'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar',
        True, 15, 5, 'Akamai bot detection',
        ('#f5d0fe', '#c026d3', '#4a044e'),
        {
            'type': 'calendar_grid',
            'months': 3,
            'url_template': 'https://www.tempecenterforthearts.com/events/tca-advanced-components/events-calendar/-curm-{month}/-cury-{year}',
            'inject_dates': True
        },
    ),
    'downtown_tempe': (
        'Downtown Tempe',
        'https://www.downtowntempe.com/events',
        False, 0, 5, 'static HTML -- no per-event URLs',
        ('#fef9c3', '#b45309', '#78350f'),
        None,  # Default LLM pagination
    ),

    # --- Previously disabled venues (now using LLM scraper) ---
    'dbg': (
        'Desert Botanical Garden',
        'https://www.dbg.org/events/',
        True, 10, 1, 'Single page, no per-event URLs',
        ('#f0fdf4', '#22c55e', '#14532d'),
        None,  # Single page, no pagination
    ),
    'odysea': (
        'OdySea Aquarium',
        'https://www.odyseaaquarium.com/events/',
        True, 10, 5, 'Previously blocked by corporate firewall',
        ('#e0f2fe', '#0284c7', '#0c4a6e'),
        None,  # Default LLM pagination
    ),
    'hale_theatre': (
        'Hale Theatre Arizona',
        'https://www.haletheater.com/events',
        True, 8, 5, 'Previously had parsing issues',
        ('#fef9c3', '#ca8a04', '#713f12'),
        None,  # Default LLM pagination
    ),
    'az_mushroom': (
        'Arizona Mushroom Society',
        'https://www.arizonamushroomsociety.org/coming-events',
        True, 5, 3, 'Community events',
        ('#f0fdf4', '#16a34a', '#14532d'),
        None,  # Default LLM pagination
    ),
    'backcountry_hunters': (
        'Backcountry Hunters & Anglers - Arizona',
        'https://www.backcountryhunters.org//events/pageid/eventlistview/categoryid/17',
        True, 5, 3, 'Arizona chapter events',
        ('#fef3c7', '#ca8a04', '#713f12'),
        None,  # Default LLM pagination
    ),
}

# ---------------------------------------------------------------------------
# Derived display dicts (used by server/app.py)
# ---------------------------------------------------------------------------
# Built automatically from SITES so they never drift out of sync.

SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}
