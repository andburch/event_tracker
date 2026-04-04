# CLAUDE.md ??? Phoenix Valley Events Recommender

## What this is

A personal, daily-use tool for finding interesting events in Phoenix Valley, AZ. Pragmatism over polish ??? working and low-maintenance beats clever and brittle. It is not built for others or for showcase.

---

## Adding a new scraper

When asked to add a scraper, follow this sequence:

1. **Visit the site** ??? fetch or browse it; determine static HTML vs JS-rendered, how pagination works, and what platform it's on (WordPress, Squarespace, Civic Plus, Localist, etc.)
2. **Go slow, be thorough** ??? Don't be afraid to increase wait times, add slow scrolls to load more content, see if you can take a screenshot of the page and inspect it. Really take a deep look.
2. **Find a similar existing source** ??? check `sources.py` for a site on the same platform or with the same pagination pattern and use it as your template. We don't want to create a lot of code bloat.
4. **Test**: `python _test_llm_scrape.py <key>` ??? confirm events are actually found
5. **If it fails**: try 1-2 obvious fixes (wrong `use_selenium` flag, `wait_secs` too short), then **stop and describe exactly what you see** ??? the user is the expert at debugging specific sites; don't thrash. Ask for a screenshot if needed.

Full reference: `HOW_TO_ADD_SCRAPERS.md`

---

## Hard-won lessons

- **Try not to invent new pagination patterns.** The 5 types (`None`/LLM, `multi_month`, `url_param`, `js_button`, `calendar_grid`) cover almost everything. Find the closest match before considering anything else.
- **Check for platform patterns first.** Sites on the same backend often share the exact same config. Look at existing sources before starting from scratch.
- **Groq rate limits are a real constraint.** Default to conservative `max_pages` (3???5) unless we are running local LLMs. Don't add extra LLM calls to an API. Run `check_groq_quota.py` before bulk scraping.
- **Bot detection is probabilistic.** A scraper failing once doesn't mean the config is wrong ??? it might be Akamai/Cloudflare on a bad day. Try a longer `wait_secs` or fresh Selenium session before assuming the config is broken.
- **Config-only is a solved problem.** The whole point is that new scrapers require nearly zero new Python code. If you find yourself writing a custom fetch or parse function, stop and reconsider. 

---

## Intentional decisions ??? do not "fix" these

| Thing | Why it exists |
|---|---|
| Sentinel time `12:34` | Marks events with no specified time; used throughout date logic. No event would REALLY have this as its time. |
| All scraper config in `sources.py` or `config.py` | Avoids custom scraper code sprawl |
| Groq + LLM model names | Set in `config.py`; don't hardcode model names elsewhere |

---

## Key commands

```bash
python llm_scraper.py <key>              # Scrape one site
python _test_llm_scrape.py <key>         # Test without DB writes
python _test_llm_scrape.py <key> --dump  # See raw HTML the LLM receives
python check_groq_quota.py               # Check Groq rate limit status
```

See `QUICK_REFERENCE.md` for the full command list.
