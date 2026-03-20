"""
Test the new venue scrapers individually
"""
import sys
sys.path.insert(0, '.')

def test_scraper(scraper_class, name):
    print(f"\n{'='*50}")
    print(f"Testing {name}")
    print('='*50)
    try:
        s = scraper_class()
        events = s.scrape()
        print(f"  RESULT: {len(events)} events")
        for e in events[:5]:
            print(f"  - {e.get('title','?')[:60]} | {e.get('date','?')} | {e.get('venue','?')[:40]}")
        return len(events)
    except Exception as ex:
        print(f"  ERROR: {ex}")
        import traceback; traceback.print_exc()
        return 0

results = {}

scraper_name = sys.argv[1] if len(sys.argv) > 1 else 'all'

if scraper_name in ('all', 'azmnh'):
    from scrapers.azmnh_scraper import AZMNHScraper
    results['azmnh'] = test_scraper(AZMNHScraper, 'AZMNH')

if scraper_name in ('all', 'mesa_arts'):
    from scrapers.mesa_arts_scraper import MesaArtsScraper
    results['mesa_arts'] = test_scraper(MesaArtsScraper, 'Mesa Arts Center')

if scraper_name in ('all', 'chandler_center'):
    from scrapers.chandler_center_scraper import ChandlerCenterScraper
    results['chandler_center'] = test_scraper(ChandlerCenterScraper, 'Chandler Center')

if scraper_name in ('all', 'chandler_library'):
    from scrapers.chandler_library_scraper import ChandlerLibraryScraper
    results['chandler_library'] = test_scraper(ChandlerLibraryScraper, 'Chandler Library')

if scraper_name in ('all', 'tempe_library'):
    from scrapers.tempe_library_scraper import TempeLibraryScraper
    results['tempe_library'] = test_scraper(TempeLibraryScraper, 'Tempe Library')

if scraper_name in ('all', 'scottsdale_arts'):
    from scrapers.scottsdale_arts_scraper import ScottsdaleArtsScraper
    results['scottsdale_arts'] = test_scraper(ScottsdaleArtsScraper, 'Scottsdale Arts')

if scraper_name in ('all', 'asu_kerr'):
    from scrapers.asu_kerr_scraper import ASUKerrScraper
    results['asu_kerr'] = test_scraper(ASUKerrScraper, 'ASU Kerr Cultural Center')

if scraper_name in ('all', 'tca'):
    from scrapers.tca_scraper import TCAScraper
    results['tca'] = test_scraper(TCAScraper, 'Tempe Center for the Arts')

print(f"\n{'='*50}")
print("SUMMARY")
print('='*50)
for name, count in results.items():
    status = "OK" if count > 0 else "FAIL"
    print(f"  [{status}] {name}: {count} events")
