"""
reset_and_restart.py — Purge events from the DB, then launch the server
and scraper as independent background processes.

Usage:
    python reset_and_restart.py

Preserves: feedback_history, user_profile, preference_profile_history
Clears:    events, scraper_runs
"""

import sys
import subprocess
import time
import os
from pathlib import Path

# Resolve the venv Python executable relative to this script's location.
# Falls back to the current interpreter if venv doesn't exist.
_root = Path(__file__).parent
_venv_python = _root / "venv" / "Scripts" / "python.exe"
PYTHON = str(_venv_python) if _venv_python.exists() else sys.executable

# ---------------------------------------------------------------------------
# Step 1: Purge events and scraper_run history
# ---------------------------------------------------------------------------
print("=" * 50)
print(" Phoenix Events Recommender - Full Reset")
print("=" * 50)
print()
print("[1/3] Purging events from database...")

from database.models import Session, Event, ScraperRun

session = Session()
deleted_events = session.query(Event).delete()
deleted_runs   = session.query(ScraperRun).delete()
session.commit()
session.close()

print(f"      Deleted {deleted_events} events and {deleted_runs} scraper run records.")
print()

# ---------------------------------------------------------------------------
# Step 2: Start Flask server in a new terminal window
# ---------------------------------------------------------------------------
print("[2/3] Starting Flask server...")

subprocess.Popen(
    [PYTHON, "server/app.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE,
    cwd=str(_root),
)

# Give the server a moment to bind before scrapers start hitting the DB
time.sleep(2)
print("      Server starting at http://localhost:5000")
print()

# ---------------------------------------------------------------------------
# Step 3: Start scraper run in a new terminal window
# ---------------------------------------------------------------------------
print("[3/3] Starting scraper run...")

subprocess.Popen(
    [PYTHON, "scraper_runner.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE,
    cwd=str(_root),
)

print("      Scrapers running in background window.")
print()
print("Done. Visit http://localhost:5000 once scraping completes.")
