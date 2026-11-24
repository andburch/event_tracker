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

Test: `./scripts/notify.sh "Test" "hello"`
