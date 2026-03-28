#!/usr/bin/env python3
from database.models import Session, Event
from collections import Counter

def check_source_months(source):
    session = Session()
    events = session.query(Event).filter_by(source=source).all()

    months = Counter([e.date.month for e in events])
    print(f'{source.title()} month distribution:')
    for m, count in sorted(months.items()):
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m]
        print(f'{month_name}: {count} events')

    session.close()

if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else 'yuccatap'
    check_source_months(source)