"""
wait_and_scrape.py - Wait 30 minutes then scrape Arizona Mushroom Society

This script waits for the Groq API daily token limit to reset, then
scrapes the az_mushroom site with the better model.
"""
import time
import subprocess
from datetime import datetime

print("="*70)
print("WAITING FOR GROQ API RATE LIMIT RESET")
print("="*70)
print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("Waiting 30 minutes for daily token limit to reset...")
print()

# Wait 30 minutes (1800 seconds)
wait_seconds = 1800
for i in range(6):
    remaining = wait_seconds - (i * 300)
    print(f"  {remaining//60} minutes remaining...")
    time.sleep(300)  # Sleep 5 minutes at a time

print()
print("="*70)
print("STARTING SCRAPE")
print("="*70)
print(f"Scrape time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# First delete existing mushroom events
print("Deleting existing az_mushroom events...")
subprocess.run([
    "python", "-c",
    "from database.models import Session, Event; "
    "s = Session(); "
    "deleted = s.query(Event).filter_by(source='az_mushroom').delete(); "
    "s.commit(); "
    "print(f'Deleted {deleted} events'); "
    "s.close()"
])

print()
print("Starting scrape...")
subprocess.run(["python", "llm_scraper.py", "az_mushroom", "--no-purge"])

print()
print("="*70)
print("DONE")
print("="*70)
