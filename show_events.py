#!/usr/bin/env python3
"""Show events in 12-hour format"""

from database.models import Session, Event

def show_events_by_source(source):
    session = Session()
    events = session.query(Event).filter_by(source=source).order_by(Event.date).all()
    
    print(f'{source.title()} events (12-hour format): {len(events)} total')
    for e in events[:15]:
        date_str = e.date.strftime('%m/%d %I:%M %p')
        print(f'{date_str} - {e.title}')
    
    if len(events) > 15:
        print(f'... and {len(events) - 15} more')
    
    session.close()

if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else 'fibber'
    show_events_by_source(source)