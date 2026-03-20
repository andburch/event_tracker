"""
scrapers/__init__.py — Scraper registry.

SCRAPERS is the authoritative list of active scrapers that scraper_runner.py
iterates over on each run. To disable a scraper temporarily, comment it out
here and optionally move it to DISABLED_SCRAPERS for documentation purposes.

Disabled scraper notes
----------------------
EventbriteScraper   — Excluded per user request (too many irrelevant events)
KidsOutAndAboutScraper — Disabled: consistent timeout issues
DBGScraper          — Blocked by corporate firewall; works fine from home network
OdySeaScraper       — Blocked by corporate firewall; works fine from home network
HaleTheatreScraper  — Disabled: press-page parsing is incomplete
"""

from .eventbrite_scraper import EventbriteScraper
from .phoenix_gov_scraper import PhoenixGovScraper
from .fibbermagees_scraper import FibberMageesScraper
from .yuccatap_scraper import YuccaTapScraper
from .dirtydrummer_scraper import DirtyDrummerScraper
from .kidsoutandabout_scraper import KidsOutAndAboutScraper
from .raisingarizonakids_scraper import RaisingArizonaKidsScraper
from .tempe_gov_scraper import TempeGovScraper
from .mesa_gov_scraper import MesaGovScraper
from .chandler_gov_scraper import ChandlerGovScraper
from .scottsdale_gov_scraper import ScottsdaleGovScraper
from .chandler_library_scraper import ChandlerLibraryScraper
from .chandler_center_scraper import ChandlerCenterScraper
from .mesa_arts_scraper import MesaArtsScraper
from .tempe_library_scraper import TempeLibraryScraper
from .dbg_scraper import DBGScraper
from .odysea_scraper import OdySeaScraper
from .azmnh_scraper import AZMNHScraper
from .scottsdale_arts_scraper import ScottsdaleArtsScraper
from .tca_scraper import TCAScraper
from .asu_kerr_scraper import ASUKerrScraper
from .gilbert_gov_scraper import GilbertGovScraper
from .hale_theatre_scraper import HaleTheatreScraper
from .downtown_tempe_scraper import DowntownTempeScraper

# Active scrapers — run on every scraper_runner.py invocation
SCRAPERS = [
    # EventbriteScraper(),        # Excluded per user request
    PhoenixGovScraper(),
    FibberMageesScraper(),
    YuccaTapScraper(),
    DirtyDrummerScraper(),
    # KidsOutAndAboutScraper(),   # Disabled: timeout issues
    RaisingArizonaKidsScraper(),
    TempeGovScraper(),
    MesaGovScraper(),
    ChandlerGovScraper(),
    ScottsdaleGovScraper(),
    ChandlerLibraryScraper(),
    ChandlerCenterScraper(),
    MesaArtsScraper(),
    TempeLibraryScraper(),
    AZMNHScraper(),
    ScottsdaleArtsScraper(),
    ASUKerrScraper(),
    TCAScraper(),
    GilbertGovScraper(),
    DowntownTempeScraper(),
    # DBGScraper(),               # Disabled: blocked by corporate firewall (works from home)
    # OdySeaScraper(),            # Disabled: blocked by corporate firewall (works from home)
    # HaleTheatreScraper(),       # Disabled: press page parsing incomplete
]

# Inactive scrapers — kept here so they're importable and visible in /health dashboard
DISABLED_SCRAPERS = [
    EventbriteScraper(),
    KidsOutAndAboutScraper(),
    DBGScraper(),
    OdySeaScraper(),
    HaleTheatreScraper(),
]
