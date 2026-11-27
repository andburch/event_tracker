#!/usr/bin/env python3
"""Print a short "this weekend" digest (Fri-Sun, Phoenix time): pinned events first, then the
highest-scored ones, deduplicated by title. Run inside the web container (it reads /data/events.db):
  docker exec event_tracker-web-1 python /app/scripts/weekly_digest.py
scripts/weekly_digest.sh scores unscored events first, then sends this via ntfy."""
import re, sqlite3, sys
sys.path.insert(0, '/app')
from sources import SOURCE_NAMES
from datetime import datetime, timedelta
TOP = 6
now = datetime.now()                                   # container runs TZ=America/Phoenix
fri = (now + timedelta(days=(4 - now.weekday()) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
mon = fri + timedelta(days=3)
c = sqlite3.connect('/data/events.db')
rows = c.execute("select date, title, venue, source, score, pinned from events where date >= ? and date < ? "
                 "order by pinned desc, score desc", (fri.isoformat(' '), mon.isoformat(' '))).fetchall()
seen, picks = set(), []
for d, title, venue, src, score, pinned in rows:
    key = re.sub(r'[^a-z0-9]', '', title.lower())
    # same show under slightly different titles ("The Fab Four: Tribute to..." vs "Tribute to..."):
    # treat as a duplicate if either title contains the other's first 25 characters
    dup = any(k[:25] in key or key[:25] in k for k in seen)
    if dup or (not pinned and (score is None or score < 0.5)): continue
    seen.add(key); picks.append((d, title, venue, src, score, pinned))
    if len([p for p in picks if not p[5]]) >= TOP: break
def when(d):
    dt = datetime.fromisoformat(d[:19])
    return dt.strftime('%a') + ('' if (dt.hour, dt.minute) == (12, 34) else dt.strftime(' %-I:%M%p').lower().replace(':00', ''))
lines = [f"{'📌 ' if p else ''}{when(d)} · {t[:60]} · {SOURCE_NAMES.get(s, s)}" for d, t, v, s, sc, p in picks]
print(f"Weekend {fri:%b %-d}–{(mon - timedelta(days=1)):%-d}: {len(rows)} events")
print('\n'.join(lines) if lines else 'Nothing scored highly this weekend.')
print('All events: http://homeserver-vm:5000/')
