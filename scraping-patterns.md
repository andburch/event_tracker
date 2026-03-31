# Scraping Patterns

A living document of what we've learned scraping each venue, organized into reusable categories.

---

## Pattern Categories

### Type A: Static / Single Page
The LLM gets everything in one fetch. No pagination needed.

- `fetch_requests` or `fetch_selenium` with a single call
- LLM returns `next_page_url: null`
- Works well when the site loads all events at once

**Sites:** `fibber`, `downtown_tempe`

---

### Type B: Infinite Scroll / Lazy Load
All events are on one URL but require scrolling to trigger JS loading.

- `fetch_selenium` with `scroll_passes=10` (default)
- The height-check loop stops early when no new content loads
- LLM returns `next_page_url: null`

**Sites:** `yuccatap`, `scottsdale`

---

### Type C: Standard URL Pagination
The LLM can see "Next" links in the page text and follows them automatically.

- Standard scraping loop in `scrape_and_save`
- LLM extracts `next_page_url` from visible link text
- `max_pages` acts as a safety cap

**Sites:** `rak` (`/page/N/`), `chandler_lib`, `tempe_lib`, `asu_kerr`

---

### Type D: Explicit URL Pagination (LLM-blind)
Pagination buttons exist but are JS/image-based — the LLM can't see them.
We construct page URLs explicitly and loop through them.

**Sub-types:**
- `?page=N` zero-indexed → `chandler`
- `pageindex=N` one-indexed (baked into complex URL) → `mesa`

**Sites:** `chandler`, `mesa`

---

### Type E: Month-View Calendar
Site shows one month at a time. Navigation buttons are JS/image — LLM can't see them.
We construct month URLs explicitly and loop through current + N future months.

**Sub-types:**
- `?view=calendar&month=MM-YYYY` → `dirtydrummer`
- `/-curm-M/-cury-YYYY/` → `gilbert`

**Sites:** `dirtydrummer`, `gilbert`

---

### Type F: JS Button Pagination (no URL change)
Pagination is driven entirely by JS button clicks. URL never changes.
We use Selenium to click the Next button between pages.

- Requires a CSS selector for the Next button
- Stop condition: button has `disabled` attribute or disappears

**Sites:** `phoenix` (selector: `a.cmp-searchCustom__pagination-btn`, second button = Next)

---

## Site-by-Site Notes

| Key | Type | Notes |
|-----|------|-------|
| fibber | A | Static, requests. 24 events. Good date coverage. |
| dirtydrummer | E | Squarespace month-view. `?view=calendar&month=MM-YYYY`. 3 months = 32 events. |
| yuccatap | B | Squarespace infinite scroll. 79 events, coverage through Aug. |
| rak | C | WordPress `/page/N/`. Date ranges like "Oct 17 - Apr 25" → use start date. Past-date filter catches stale events. |
| chandler | D | `?page=N` zero-indexed. Removed category filters, scrape everything. max_pages=10. |
| scottsdale | B | Loads ~42 events. Scroll stops growing at ~37k chars — likely has a "load more" button we're not clicking. |
| gilbert | E | Akamai bot detection. `/-curm-M/-cury-YYYY/`. 5 months = 35 events. |
| phoenix | F | JS button pagination. `a.cmp-searchCustom__pagination-btn[1]`. 5 pages = 51 events. |
| mesa | D | `pageindex=N` one-indexed, baked into complex filter URL. 5 pages = 35 events. No times on events. |

---

## General Lessons

- **Date formats**: LLM now asked to return YYYY-MM-DD. Day-of-week prefixes ("Thursday, March 26") and date ranges ("Oct 17 - Apr 25") are handled.
- **Past-date filtering**: Events with dates before today are skipped at save time. Date-range events currently running use today's date.
- **URL copying**: LLM prompted to copy URLs exactly, not paraphrase. Still imperfect with smaller models.
- **Scroll passes**: Default is 10 for all Selenium fetches. Height-check exits early if no new content loads, so this is safe for all sites.
- **max_pages**: Bumped to 5 globally (10 for chandler). Acts as a safety cap, not a target.
