#!/usr/bin/env bash
# Send a push alert via ntfy.sh. Usage: notify.sh "Title" "Message"
# Optional: NTFY_PRIORITY=low|default|high|urgent (default high).
# high/urgent alerts are sent twice: now, and a "(repeat)" that ntfy.sh itself
# delivers 30 min later (Delay header), in case the phone's push was dropped.
# Topic lives in ~/.config/homeserver-alerts/topic (subscribe to it in the ntfy app).
TOPIC_FILE="/home/ubuntu/.config/homeserver-alerts/topic"
[ -r "$TOPIC_FILE" ] || { echo "notify: topic file $TOPIC_FILE missing/unreadable - alert NOT sent" >&2; exit 1; }
URL="https://ntfy.sh/$(cat "$TOPIC_FILE")"
PRIORITY="${NTFY_PRIORITY:-high}"
case "$PRIORITY" in high|urgent) TAGS=warning ;; *) TAGS=white_check_mark ;; esac
curl -fsS --max-time 15 -H "Title: $1" -H "Priority: $PRIORITY" -H "Tags: $TAGS" \
  -d "$2" "$URL" > /dev/null || exit 1
if [ "$PRIORITY" = high ] || [ "$PRIORITY" = urgent ]; then
  curl -fsS --max-time 15 -H "Title: $1 (2nd reminder)" -H "Priority: $PRIORITY" -H "Tags: $TAGS" \
    -H "Delay: 30m" -d "SECOND REMINDER of an alert first sent 30 min ago ($(date '+%a %-I:%M %p')). It may have cleared since; a later \"all clear\" message would say so.

$2" "$URL" > /dev/null \
    || echo "notify: repeat could not be scheduled (first alert WAS sent)" >&2
fi
exit 0
