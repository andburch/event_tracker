# Phoenix Events Scraper - Venue Technical Challenges

This document outlines the technical difficulties and implementation details for each event source in the Phoenix Events Recommender system.

## Overview

The system uses two approaches:
- **LLM System** (Current): Uses `llm_scrape_core.py` with AI-powered content extraction
- **Deprecated Scrapers** (Legacy): Custom BeautifulSoup scrapers in `scrapers/` folder

## Venue Technical Details

| **Venue** | **Method** | **Selenium Required** | **Special Challenges** | **Pagination** | **Wait Time** | **Max Pages** | **Notes** |
|-----------|------------|----------------------|----------------------|----------------|---------------|-----------|-----------|
| **Fibber Magees** | LLM/Requests | No | None | None | 3s | 1 | Simple static HTML |
| **Dirty Drummer** | LLM/Selenium | Yes | Squarespace platform | None | 8s | 1 | JavaScript-rendered content |
| **Yucca Tap Room** | LLM/Selenium | Yes | Squarespace infinite scroll | Infinite scroll | 8s | 1 | Requires scrolling to load more events |
| **Raising Arizona Kids** | LLM/Selenium | Yes | WordPress pagination | `/page/N/` URLs | 8s | 4 | Standard WordPress pagination |
| **City of Chandler** | LLM/Selenium | Yes | Complex filtering | `?page=N` parameter | 5s | 3 | Pre-filtered category URLs |
| **City of Scottsdale** | LLM/Selenium | Yes | Basic calendar | None | 8s | 1 | Simple government calendar |
| **City of Gilbert** | Deprecated/Selenium | Yes | **Akamai bot detection** | Next Month links | 15s | 3 | Requires CDP user-agent spoofing |
| **City of Phoenix** | Deprecated/Selenium | Yes | JavaScript pagination | Next button clicks | 6s | 2 | Dynamic pagination buttons |
| **City of Mesa** | LLM/Selenium | Yes | Events directory | Standard pagination | 6s | 2 | Government events listing |
| **Chandler Library** | LLM/Selenium | Yes | BiblioCommons platform | Standard pagination | 5s | 2 | Library event system |
| **Tempe Library** | LLM/Selenium | Yes | **Date-range URLs required** | Standard pagination | 8s | 2 | Must construct date-range URLs |
| **AZ Natural History** | LLM/Selenium | Yes | Museum events | None | 5s | 1 | Simple museum calendar |
| **Chandler Arts Center** | LLM/Selenium | Yes | Arts venue | Standard pagination | 5s | 2 | Theater/arts events |
| **Mesa Arts Center** | Deprecated/Selenium | Yes | Show listings | None | 5s | 1 | Performance venue |
| **Scottsdale Arts** | Deprecated/Selenium | Yes | **Akamai + Load More** | "Load More" button | 15s | 2 | Bot detection + dynamic loading |
| **ASU Kerr Center** | LLM/Selenium | Yes | **No per-event URLs** | `/page/N/` WordPress | 5s | 2 | Events lack individual URLs |
| **Tempe Arts Center** | LLM/Selenium | Yes | **Akamai bot detection** | Standard pagination | 15s | 2 | Heavy bot protection |
| **Downtown Tempe** | LLM/Requests | No | **No per-event URLs** | None | 0s | 1 | Static HTML, no detail pages |
| **Kids Out and About** | LLM/Selenium | Yes | **Previous timeout issues** | Standard pagination | 8s | 3 | Previously unreliable |
| **Desert Botanical** | LLM/Selenium | Yes | **Corporate firewall blocks** | Standard pagination | 10s | 2 | Network access issues |
| **OdySea Aquarium** | LLM/Selenium | Yes | **Corporate firewall blocks** | Standard pagination | 10s | 2 | Network access issues |
| **Hale Theatre** | LLM/Selenium | Yes | **Previous parsing issues** | Standard pagination | 8s | 2 | Complex HTML structure |
| **Eventbrite** | Deprecated/Selenium | Yes | **JSON-LD + HTML fallback** | Dynamic loading | 5s | 1 | Structured data + complex JS |
| **Tempe Gov (RSS)** | Deprecated/RSS | No | **Multiple RSS feeds** | None | 0s | 1 | 13 different category feeds |

## Major Technical Challenges

### 1. Bot Detection & Anti-Scraping
- **Akamai Protection**: Gilbert, Scottsdale Arts, Tempe Arts
  - Requires CDP user-agent spoofing
  - Extended wait times (15s)
  - May require rotating user agents

### 2. Dynamic Content Loading
- **Infinite Scroll**: Yucca Tap Room
  - Must scroll repeatedly to load all events
  - Requires monitoring scroll height changes
- **Load More Buttons**: Scottsdale Arts
  - Must click "Load More" button repeatedly
  - Up to 20 clicks to load full content

### 3. Network & Firewall Issues
- **Corporate Firewall Blocking**: Desert Botanical, OdySea Aquarium
  - Sites blocked by some corporate networks
  - Requires proxy or alternative network access
- **Timeout Issues**: Kids Out and About
  - Previously unreliable, now using LLM system

### 4. Complex Pagination Systems
- **JavaScript Pagination**: Phoenix Gov
  - Dynamic "Next" button clicks
  - Must wait for page loads between clicks
- **WordPress Pagination**: Raising Arizona Kids, ASU Kerr
  - Standard `/page/N/` URL structure
- **Parameter-based**: Chandler Gov
  - Uses `?page=N` URL parameters

### 5. Data Structure Limitations
- **No Individual Event URLs**: ASU Kerr, Downtown Tempe
  - Events don't have dedicated detail pages
  - Limits data richness and verification
- **Date-Range Requirements**: Tempe Library
  - Must construct URLs with start/end date parameters
  - Format: `?start=YYYY-MM-DD&end=YYYY-MM-DD`

### 6. Platform-Specific Challenges
- **Squarespace Sites**: Dirty Drummer, Yucca Tap
  - Heavy JavaScript rendering
  - Infinite scroll implementation
- **BiblioCommons**: Chandler Library
  - Library-specific event platform
  - Standardized but complex structure
- **RSS Aggregation**: Tempe Gov
  - 13 separate RSS feeds to process
  - Deduplication across feeds required

## Implementation Notes

### LLM System Advantages
- Handles diverse HTML structures automatically
- No need for site-specific parsing logic
- Adapts to layout changes without code updates
- Extracts semantic meaning from content

### LLM System Limitations
- Requires API calls (cost and rate limits)
- May miss structured data that custom scrapers catch
- Less precise than targeted scrapers for complex sites
- Cannot handle some advanced interactions (user-agent spoofing)

### Deprecated Scraper Advantages
- Highly optimized for specific site structures
- Can handle complex interactions (CDP commands, precise clicking)
- No API costs or rate limits
- Faster execution for simple sites

### Deprecated Scraper Disadvantages
- Brittle - breaks when sites change layouts
- Requires maintenance for each site
- Complex codebase with site-specific logic
- Harder to add new sources

## Recommendations

1. **Keep LLM system as primary** for most sources
2. **Use deprecated scrapers** for sites with severe technical challenges:
   - Gilbert (Akamai protection)
   - Phoenix (complex pagination)
   - Scottsdale Arts (Load More + Akamai)
   - Tempe Gov (RSS efficiency)
3. **Monitor and fallback** - Use deprecated scrapers as backup when LLM fails
4. **Gradual migration** - Move complex sites to LLM as the system improves

## Configuration Reference

All current configurations are defined in `sources.py`:
- `use_selenium`: Whether Selenium is required
- `wait_secs`: Seconds to wait after page load
- `max_pages`: Maximum pages to scrape
- `note`: Documents specific challenges

Legacy scrapers are in `scrapers/` folder but marked as deprecated.