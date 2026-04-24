#!/usr/bin/env bash
# Run the subset of scrapers assigned to today. Invoked by events-scrape.timer.
set -euo pipefail

cd /home/ubuntu/event_tracker

# Map ISO weekday (1=Mon .. 7=Sun) to site keys.
case "$(date +%u)" in
  1) KEYS="fibber dirtydrummer yuccatap valley_bar sleepy_whale" ;;
  2) KEYS="chandler scottsdale gilbert phoenix mesa" ;;
  3) KEYS="chandler_lib tempe_lib azmnh dbg odysea" ;;
  4) KEYS="chandler_center mesa_arts scottsdale_arts asu_kerr tca" ;;
  5) KEYS="downtown_tempe changing_hands sweet_basil farm_south_mtn summerwinds" ;;
  6) KEYS="az_mushroom az_worm_farm backcountry_hunters az_flycasters hale_theatre" ;;
  7) KEYS="rak evac" ;;
esac

echo "[$(date -Iseconds)] weekly_scrape: $KEYS"
exec docker compose --profile scraper run --rm scraper python llm_scraper.py $KEYS
