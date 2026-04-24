#!/usr/bin/env bash
# Score any events with score IS NULL. Invoked by events-score.timer.
set -euo pipefail

cd /home/ubuntu/event_tracker
echo "[$(date -Iseconds)] weekly_score"
exec docker compose --profile scraper run --rm scraper python score_events.py
