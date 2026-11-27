#!/usr/bin/env bash
# Thursday evening digest: score any unscored events, then push the weekend's top picks via ntfy.
cd /home/ubuntu/event_tracker
docker compose --profile scraper run --rm scraper python score_events.py >/dev/null 2>&1 || echo "scoring failed (digest uses existing scores)" >&2
msg=$(docker exec event_tracker-web-1 python /app/scripts/weekly_digest.py) || exit 1
title=$(head -1 <<<"$msg"); body=$(tail -n +2 <<<"$msg")
NTFY_PRIORITY=default /home/ubuntu/event_tracker/scripts/notify.sh "$title" "$body"
