#!/usr/bin/env python3
from database.models import Session, Event
session = Session()
events = session.query(Event).filter_by(source='tca').filter(
    Event.date >= '2026-04-01', Event.date < '2026-05-01'
).order_by(Event.date).all()
print(f"April TCA events: {len(events)}")
for e in events:
    print(f"  {e.date.strftime('%m/%d %I:%M %p')} - {e.title}")
session.close()
