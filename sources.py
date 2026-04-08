"""
sources.py -- Single source of truth for all scraped event sources.

Each entry in SITES defines everything about a source:
  - Scraping config  (url, selenium, wait, max_pages, pagination_config)
  - Display metadata (display_name, color)

TRIM_PATTERNS strips site-specific boilerplate (nav menus, filter sidebars,
cookie consent walls) from cleaned HTML before it reaches the LLM.  This
reduces token usage and speeds up local models significantly.

Both llm_scrape_core.py and server/app.py import SITES from here.
pagination_engine.py imports TRIM_PATTERNS from here.
Adding a new site means editing only this file.

SITES entry format:
    key: (display_name, url, use_selenium, wait_secs, max_pages, note, color, pagination_config)

color: (background, border, text) CSS hex strings for calendar chips.
pagination_config: Dict defining pagination behavior (see pagination_engine.py for details)
    - If None or omitted: Uses default LLM pagination (LLM extracts next_page_url)
    - Otherwise: Dict with 'type' key and type-specific config

TRIM_PATTERNS entry format:
    key: one of
         - string:       head trim only  — marks the END of pre-event boilerplate
                         (inclusive). Everything up to and including this string
                         is stripped.
         - (str, str):   (head, tail)    — also strips from the tail marker to end,
                         useful when a filter sidebar or footer follows the events.
         - None:         no trim (page starts directly with events).
         See HOW_TO_ADD_SCRAPERS.md for how to find and verify trim patterns.
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
        True, 8, 10, 'WordPress /page/N/ pagination',
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
        True, 5, 5, 'WordPress + The Events Calendar plugin',
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
        True, 10, 5, '',
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
# Boilerplate trim patterns
# ---------------------------------------------------------------------------
# Many sites prepend nav menus, filter sidebars, cookie banners, or calendar
# grids to their event pages.  This text wastes LLM tokens and slows local
# models by 1.5–2.6×.  TRIM_PATTERNS removes it before the text reaches
# ask_llm().
#
# HOW IT WORKS
# Each value is either:
#   - a string: marks the END of head boilerplate (inclusive). pagination_engine.
#     apply_trim() finds the first occurrence and discards everything up to and
#     including it.
#   - a (head, tail) tuple: head works as above; ALSO strips everything from the
#     first occurrence of `tail` to the end of the text. Use this when events
#     are followed by a filter sidebar or footer that inflates chunking.
#   - None: no trim (page opens directly with events).
#
# HOW TO FIND THE RIGHT STRING FOR A NEW SITE
#  1. Run: python3 _collect_artifacts.py          # saves debug_artifacts/<key>/page_1_cleaned.txt
#  2. Read the artifact: head -200 debug_artifacts/<key>/page_1_cleaned.txt
#  3. Find the last line of boilerplate before the first real event appears
#  4. Pick a multi-line span (2–3 lines) that:
#       - Is specific to the UI (not something that could be an event title/venue)
#       - Does NOT change month-to-month (avoid category names on rotating sites)
#       - Is stable across pagination pages (appears on page 2, 3, etc.)
#  5. Verify it appears exactly once: python3 -c "
#         text = open('debug_artifacts/<key>/page_1_cleaned.txt').read()
#         print(text.count('your pattern here'))
#     "
#  6. Add the entry here. Set to None if the page opens directly with events.
# ---------------------------------------------------------------------------
TRIM_PATTERNS = {
    # Fibber Magee's — nav header (stable); category filters follow but are only
    # 8 harmless lines.  Don't key on category names — they change.
    'fibber':              "Upcoming Events\nCalender View [/menu-1]\n",

    # Dirty Drummer — full 7-day calendar header row; far more specific than Fr/Sa alone
    'dirtydrummer':        "\nSu\nMo\nTu\nWe\nTh\nFr\nSa\n",

    # Yucca Tap Room — page opens directly with events; nothing to trim
    'yuccatap':            None,

    # Raising Arizona Kids — filter widget label before events (head trim), then the
    # huge Category/Age/Neighborhood filter sidebar after the pagination links (tail trim).
    # The sidebar is ~230 lines / ~3k chars and pushed the "Next >" pagination link into
    # a non-last chunk, causing the LLM to skip pages 2-7.
    'rak':                 ("Displaying:\nAll\n", "Calendar\nsearch our Calendar"),

    # City of Chandler — 3-line sequence at end of location filter + submit button;
    # more robust than just "\nGo\n" which is a single common word
    'chandler':            "\nWindmills West Park\nWinn Park\nGo\n",

    # City of Scottsdale — filter sidebar with 70+ category options
    'scottsdale':          "\nReset all filters\n",

    # City of Gilbert — CivicPlus calendar; full day-of-week header row (appears once)
    'gilbert':             "\nSunday\nMonday\nTuesday\nWednesday\nThursday\nFriday\nSaturday\n",

    # City of Phoenix — featured event + browse-by-topic nav; hidden menu marker
    'phoenix':             "\nclose menu\n",

    # City of Mesa — minimal 3-line header before event list
    'mesa':                "\nEvents listing\n",

    # Chandler Public Library (BiblioCommons) — filter sidebar before listing
    'chandler_lib':        "\nEvent items\n",

    # Tempe Public Library — complex calendar UI (~175 lines); cut right before events
    'tempe_lib':           "\nCreate Brochure\n",

    # AZ Museum of Natural History — slideshow nav (8 lines)
    'azmnh':               "\nCalendar [/azmnh-calendar]\n",

    # Chandler Center for the Arts — genre filter list
    'chandler_center':     "\nSearch by Title\n",

    # Mesa Arts Center — featured carousel + date-picker filter UI (~210 lines)
    'mesa_arts':           "\nYour selection will automatically update the results below.\n",

    # Scottsdale Arts — genre/location/setting filter lists; view-mode toggle
    'scottsdale_arts':     "\nCalendar View\nFilter\n",

    # ASU Kerr Cultural Center — filter accordions; last accordion is Series
    'asu_kerr':            "\nSeries\n:\n",

    # Tempe Center for the Arts — CivicPlus calendar (same pattern as gilbert)
    'tca':                 "\nSunday\nMonday\nTuesday\nWednesday\nThursday\nFriday\nSaturday\n",

    # Downtown Tempe — featured-events hero + filter UI; end of category list
    'downtown_tempe':      "\nWalks / Runs\nTempe Beach Park\nASU\n",

    # Desert Botanical Garden — enormous cookie-consent block (~1000 lines before events)
    'dbg':                 "\nUPCOMING EVENTS & EXHIBITS\n",

    # OdySea Aquarium — Cloudflare-blocked; no usable artifact, no trim possible
    'odysea':              None,

    # Hale Theatre — Selenium timeout; no usable artifact, no trim possible
    'hale_theatre':        None,

    # Arizona Mushroom Society — nav menu (duplicated) + login form before events
    'az_mushroom':         "\nAMS EVENT CALENDAR\n",

    # Backcountry Hunters & Anglers — US state chapter list + interest filters
    'backcountry_hunters': "\n-- Select Location --\n",
}

# ---------------------------------------------------------------------------
# Derived display dicts (used by server/app.py)
# ---------------------------------------------------------------------------
# Built automatically from SITES so they never drift out of sync.

SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}
