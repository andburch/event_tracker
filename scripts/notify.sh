#!/usr/bin/env bash
# Send a push alert via ntfy.sh. Usage: notify.sh "Title" "Message"
# Optional: NTFY_PRIORITY=low|default|high (default high).
# Topic lives in ~/.config/homeserver-alerts/topic (subscribe to it in the ntfy app).
TOPIC_FILE="/home/ubuntu/.config/homeserver-alerts/topic"
[ -r "$TOPIC_FILE" ] || { echo "notify: topic file $TOPIC_FILE missing/unreadable - alert NOT sent" >&2; exit 1; }
PRIORITY="${NTFY_PRIORITY:-high}"
TAGS=$([ "$PRIORITY" = high ] && echo warning || echo white_check_mark)
curl -fsS --max-time 15 -H "Title: $1" -H "Priority: $PRIORITY" -H "Tags: $TAGS" \
  -d "$2" "https://ntfy.sh/$(cat "$TOPIC_FILE")" > /dev/null
