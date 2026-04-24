# systemd units (reference copies)

The live copies are installed at `/etc/systemd/system/`. These are the version-controlled source of truth — update them here, then reinstall.

## Install

```bash
sudo cp scripts/systemd/*.service scripts/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now events-scrape.timer events-score.timer
```

## Inspect

```bash
systemctl list-timers events-*
journalctl -u events-scrape.service -f
journalctl -u events-score.service -f
```
