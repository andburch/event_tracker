#!/usr/bin/env bash
# Send a push alert via ntfy.sh. Usage: notify.sh "Title" "Message"
# Topic lives in ~/.config/homeserver-alerts/topic (subscribe to it in the ntfy app).
TOPIC_FILE="/home/ubuntu/.config/homeserver-alerts/topic"
[ -r "$TOPIC_FILE" ] || { echo "notify: no topic file, skipping" >&2; exit 0; }
curl -fsS --max-time 15 -H "Title: $1" -H "Priority: high" -H "Tags: warning" \
  -d "$2" "https://ntfy.sh/$(cat "$TOPIC_FILE")" > /dev/null
