"""
Deterministic event-link repair, configured per source in sources.LINK_FROM_TEXT.

Some list layouts put each event's link on a line next to its title (e.g. "More Info [url]"
just ABOVE the title). LLMs often attach the neighbouring event's link instead. For sources
configured here, after extraction each event's url is taken straight from the page text:
find the event's title line (for repeated titles, the occurrence nearest this event's date
and time) and use the first matching link found scanning in the configured direction.
No LLM calls. Events whose title isn't found keep the model's url.
"""
import re
from datetime import datetime

_URL = re.compile(r'\[(https?://[^\]\s]+)\]')


def _date_forms(d):
    try:
        dt = datetime.strptime((d or '')[:10], '%Y-%m-%d')
    except ValueError:
        return []
    return [s.lower() for s in (f"{dt:%B} {dt.day}, {dt.year}", f"{dt:%B} {dt:%d}, {dt.year}",
                                f"{dt:%b} {dt.day}", f"{dt:%B} {dt.day}", f"{dt.month}/{dt.day}/")]


def relink(events, text, position='before', link_label=None, max_lines=8):
    """Set ev['url'] from `text` for each event. position: 'before' (link above title) or 'after'.
    link_label: only use links on lines starting with this text (e.g. 'More Info').
    Returns the number of urls changed."""
    lines = text.splitlines()
    low = [l.strip().lower() for l in lines]
    changed = 0
    for ev in events:
        t = re.sub(r'\s+', ' ', ev.get('title') or '').strip().lower()
        if len(t) < 3:
            continue
        occ = [i for i, l in enumerate(low) if l == t] or [i for i, l in enumerate(low) if t[:40] in l]
        if not occ:
            continue
        if len(occ) > 1:
            forms = _date_forms(ev.get('date'))
            tm = (ev.get('time') or '').lower().replace(' ', '').lstrip('0')
            def score(i):
                near = [abs(j - i) for j in range(max(0, i - 4), min(len(low), i + 6)) if any(f in low[j] for f in forms)]
                t_ok = 0 if tm and any(tm == l.replace(' ', '').lstrip('0') for l in low[max(0, i - 4): i + 6]) else 1
                return (min(near) if near else 99, t_ok, i)
            idx = min(occ, key=score)
        else:
            idx = occ[0]
        rng = (range(idx - 1, max(-1, idx - 1 - max_lines), -1) if position == 'before'
               else range(idx, min(len(lines), idx + 1 + max_lines)))
        for j in rng:
            if link_label and not low[j].startswith(link_label.lower()):
                continue
            m = _URL.search(lines[j])
            if m:
                if ev.get('url') != m.group(1):
                    changed += 1
                ev['url'] = m.group(1)
                break
    return changed
