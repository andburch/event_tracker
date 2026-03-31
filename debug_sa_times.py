from database.models import Session, Event
session = Session()
events = session.query(Event).filter_by(source='scottsdale_arts').all()
no_time = [e for e in events if e.date.hour == 12 and e.date.minute == 34]
print(f'{len(no_time)} events with sentinel time:')
for e in no_time[:15]:
    print(f'  {e.date.strftime("%m/%d")} - {e.title[:55]}')
session.close()
