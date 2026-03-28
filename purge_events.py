#!/usr/bin/env python3
"""
Purge all events from the database.

This script will delete all records from the events table while preserving
other data like user profiles, feedback history, and scraper run logs.
"""

from database.models import Session, Event

def purge_all_events():
    """Delete all events from the database."""
    session = Session()
    try:
        # Count events before deletion
        event_count = session.query(Event).count()
        print(f"Found {event_count} events in database")
        
        if event_count == 0:
            print("No events to delete")
            return
        
        # Delete all events
        deleted_count = session.query(Event).delete()
        session.commit()
        
        print(f"Successfully deleted {deleted_count} events from database")
        
    except Exception as e:
        session.rollback()
        print(f"Error purging events: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("Purging all events from database...")
    purge_all_events()
    print("Done!")