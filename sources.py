"""
sources.py -- Single source of truth for all scraped event sources.

Each entry in SITES defines everything about a source:
  - Scraping config  (url, selenium, wait, max_pages)
  - Display metadata (display_name, color)

Both llm_scrape_core.py and server/app.py import from here.
Adding a new site means editing only this file.

SITES entry format:
    key: (display_name, url, use_selenium, wait_secs, max_pages, note, color)

color: (background, border, text) CSS hex strings for calendar chips.
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
# ---------------------------------------------------------------------------

SITES = {
    # --- Music venues ---
    'fibber': (
        'Fibber Magees',
        'https://www.fibbermageespub.com/fibber-magees-events',
        False, 3, 1, '',
        ('#fff7ed', '#c2410c', '#7c2d12'),
    ),
    'dirtydrummer': (
        'Dirty Drummer',
        'https://www.thedirtydrummer.com/events',
        True, 8, 1, 'Squarespace',
        ('#fdf2f8', '#9d174d', '#500724'),
    ),
    'yuccatap': (
        'Yucca Tap Room',
        'https://yuccatap.com/events',
        True, 8, 1, 'Squarespace infinite scroll',
        ('#fef2f2', '#b91c1c', '#450a0a'),
    ),

    # --- Government / community calendars ---
    'rak': (
        'Raising Arizona Kids',
        'https://www.raisingarizonakids.com/calendar/',
        True, 8, 4, 'WordPress /page/N/ pagination',
        ('#ecfeff', '#0891b2', '#164e63'),
    ),
    'chandler': (
        'City of Chandler',
        'https://www.chandleraz.gov/events-result?keyword=&categories%5B2%5D=2&categories%5B3%5D=3&categories%5B5%5D=5',
        True, 5, 3, '?page=N pagination',
        ('#fce7f3', '#db2777', '#831843'),
    ),
    'scottsdale': (
        'City of Scottsdale',
        'https://community.scottsdaleaz.gov/scottsdaleaz_main/calendar',
        True, 8, 1, '',
        ('#fee2e2', '#dc2626', '#7f1d1d'),
    ),
    'gilbert': (
        'City of Gilbert',
        'https://www.gilbertaz.gov/residents/calendar-month-view/',
        True, 15, 3, 'Akamai bot detection',
        ('#ffedd5', '#ea580c', '#7c2d12'),
    ),
    'phoenix': (
        'City of Phoenix',
        'https://www.phoenix.gov/calendar.html',
        True, 6, 2, '',
        ('#dbeafe', '#2563eb', '#1e3a8a'),
    ),
    'mesa': (
        'City of Mesa',
        'https://www.mesaaz.gov/Events-directory',
        True, 6, 2, '',
        ('#ede9fe', '#7c3aed', '#4c1d95'),
    ),

    # --- Libraries ---
    'chandler_lib': (
        'Chandler Public Library',
        'https://chandler.bibliocommons.com/v2/events',
        True, 5, 2, '',
        ('#dcfce7', '#16a34a', '#14532d'),
    ),
    'tempe_lib': (
        'Tempe Public Library',
        f'https://tempepubliclibrary.libnet.info/events?start={_today}&end={_plus90}',
        True, 8, 2, 'date-range URL required',
        ('#d1fae5', '#059669', '#064e3b'),
    ),

    # --- Arts / museums ---
    'azmnh': (
        'AZ Museum of Natural History',
        'https://www.azmnh.org/azmnh-events',
        True, 5, 1, '',
        ('#ecfdf5', '#10b981', '#064e3b'),
    ),
    'chandler_center': (
        'Chandler Center for the Arts',
        'https://www.chandlercenter.org/events',
        True, 5, 2, '',
        ('#fdf4ff', '#a21caf', '#581c87'),
    ),
    'mesa_arts': (
        'Mesa Arts Center',
        'https://www.mesaartscenter.com/shows/',
        True, 5, 1, '',
        ('#fce7f3', '#be185d', '#500724'),
    ),
    'scottsdale_arts': (
        'Scottsdale Arts',
        'https://scottsdalearts.org/whats-on/?categories=performances,events,programs-workshops',
        True, 15, 2, 'Akamai bot detection + category filter URL',
        ('#ffe4e6', '#e11d48', '#881337'),
    ),
    'asu_kerr': (
        'ASU Kerr Cultural Center',
        'https://asukerr.com/events/',
        True, 5, 2, 'WordPress /page/N/ -- no per-event URLs',
        ('#fef3c7', '#d97706', '#78350f'),
    ),
    'tca': (
        'Tempe Center for the Arts',
        'https://www.tempecenterforthearts.com/events/calendar',
        True, 15, 2, 'Akamai bot detection',
        ('#f5d0fe', '#c026d3', '#4a044e'),
    ),
    'downtown_tempe': (
        'Downtown Tempe',
        'https://www.downtowntempe.com/events',
        False, 0, 1, 'static HTML -- no per-event URLs',
        ('#fef9c3', '#b45309', '#78350f'),
    ),

    # --- Previously disabled venues (now using LLM scraper) ---
    'kidsoutandabout': (
        'Kids Out and About',
        'https://www.kidsoutandabout.com/phoenix-az',
        True, 8, 3, 'Previously had timeout issues',
        ('#f0fdfa', '#0d9488', '#134e4a'),
    ),
    'dbg': (
        'Desert Botanical Garden',
        'https://www.dbg.org/events/',
        True, 10, 2, 'Previously blocked by corporate firewall',
        ('#f0fdf4', '#22c55e', '#14532d'),
    ),
    'odysea': (
        'OdySea Aquarium',
        'https://www.odyseaaquarium.com/events/',
        True, 10, 2, 'Previously blocked by corporate firewall',
        ('#e0f2fe', '#0284c7', '#0c4a6e'),
    ),
    'hale_theatre': (
        'Hale Theatre Arizona',
        'https://www.haletheater.com/events',
        True, 8, 2, 'Previously had parsing issues',
        ('#fef9c3', '#ca8a04', '#713f12'),
    ),
}

# ---------------------------------------------------------------------------
# Derived display dicts (used by server/app.py)
# ---------------------------------------------------------------------------
# Built automatically from SITES so they never drift out of sync.
# Legacy scraper keys are appended below for historical scraper_run records.

SOURCE_NAMES = {key: entry[0] for key, entry in SITES.items()}
SOURCE_COLORS = {key: entry[6] for key, entry in SITES.items()}

# Legacy source keys from the old BeautifulSoup scrapers.
# Kept so the /health dashboard can display names for historical scraper_run rows.
_LEGACY_SOURCES = {
    'phoenix_gov':        ('City of Phoenix',           ('#dbeafe', '#2563eb', '#1e3a8a')),
    'tempe_gov':          ('City of Tempe',             ('#e0e7ff', '#4f46e5', '#312e81')),
    'mesa_gov':           ('City of Mesa',              ('#ede9fe', '#7c3aed', '#4c1d95')),
    'chandler_gov':       ('City of Chandler',          ('#fce7f3', '#db2777', '#831843')),
    'scottsdale_gov':     ('City of Scottsdale',        ('#fee2e2', '#dc2626', '#7f1d1d')),
    'gilbert_gov':        ('City of Gilbert',           ('#ffedd5', '#ea580c', '#7c2d12')),
    'chandler_library':   ('Chandler Public Library',   ('#dcfce7', '#16a34a', '#14532d')),
    'tempe_library':      ('Tempe Public Library',      ('#d1fae5', '#059669', '#064e3b')),
    'fibbermagees':       ("Fibber Magee's",            ('#fff7ed', '#c2410c', '#7c2d12')),
    'raisingarizonakids': ('Raising Arizona Kids',      ('#ecfeff', '#0891b2', '#164e63')),
    'kidsoutandabout':    ('Kids Out and About',        ('#f0fdfa', '#0d9488', '#134e4a')),
    'dbg':                ('Desert Botanical Garden',   ('#f0fdf4', '#22c55e', '#14532d')),
    'odysea':             ('OdySea Aquarium',           ('#e0f2fe', '#0284c7', '#0c4a6e')),
    'hale_theatre':       ('Hale Theatre Arizona',      ('#fef9c3', '#ca8a04', '#713f12')),
    'eventbrite':         ('Eventbrite',                ('#fff1f2', '#f43f5e', '#881337')),
}

for key, (name, color) in _LEGACY_SOURCES.items():
    SOURCE_NAMES[key]  = name
    SOURCE_COLORS[key] = color
