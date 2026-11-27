# systemd units (reference copies)

The live copies are installed at `/etc/systemd/system/`. These are the version-controlled source of truth — update them here, then reinstall.

## Install

```bash
sudo cp scripts/systemd/*.service scripts/systemd/*.timer /etc/systemd/system/   # includes events-alert@.service
sudo systemctl daemon-reload
sudo systemctl enable --now events-scrape.timer events-score.timer
```

## Inspect

```bash
systemctl list-timers events-*
journalctl -u events-scrape.service -f
journalctl -u events-score.service -f
```

## Failure alerts

`events-scrape.service` and `events-score.service` have `OnFailure=events-alert@%n.service`. When a run exits non-zero (every site failed, 0 events found, or nothing could be scored), `events-alert@.service` runs `scripts/notify.sh`. That posts a high-priority push to ntfy.sh. The topic name is in `~/.config/homeserver-alerts/topic` (chmod 600, not in git); subscribe to it in the ntfy phone app.

Test: `./scripts/notify.sh "Test" "hello"`. Set `NTFY_PRIORITY=low` (or `default`) for non-alert messages; it defaults to `high`.

The same script is used by the server-wide health check (`~/maintenance/check-services-alert.sh`, a 6-hour systemd user timer), which also sends a weekly "all good" check-in.

## Weekly digest (user unit)

`events-digest.timer` runs as a **user** unit (`~/.config/systemd/user/`), every Thursday at 17:00 Phoenix time. It calls `scripts/weekly_digest.sh`, which first scores any unscored events, then pushes the weekend's (Fri–Sun) pinned and top-scored events via ntfy. Preview it with `docker exec event_tracker-web-1 python /app/scripts/weekly_digest.py`. Reinstall with `cp scripts/systemd/events-digest.* ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now events-digest.timer`.
