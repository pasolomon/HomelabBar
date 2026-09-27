# HomelabBar

A macOS menu-bar app that shows your Tailscale tailnet and whether your homelab services are up.

```
⌂ ✓     all good        ⌂ ✗2    two services down        ⌂ ⚠    Tailscale not running / not found
```

- **Tailnet:** state, exit node, health warnings, and every peer with its IP, OS, direct or relayed connection, and when an offline peer was last seen.
- **Peer actions:** SSH (opens Terminal via `ssh://`), Copy IP, Copy DNS Name.
- **Service checks:** TCP connect or HTTP(S) GET, run in parallel every `refresh_seconds`, with latency shown.
- **Notifications:** sent when a service goes down or recovers, when Tailscale stops, or when a peer listed in `watch_peers` goes offline.

The app reads state from the local `tailscale status --json`, so it needs no API key. Checks run from the Mac across the tailnet, and nothing is exposed.

## Install

Requires Python 3.10+ (Homebrew's is fine) and the Tailscale CLI. The CLI is found on `PATH`, in `/opt/homebrew/bin`, in `/usr/local/bin`, or inside `/Applications/Tailscale.app`.

```bash
git clone git@github.com:pasolomon/HomelabBar.git && cd HomelabBar
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/homelabbar                          # run it
scripts/launchagent.sh install .venv/bin/homelabbar   # start at login
```

On first run, the app writes a default config to `~/Library/Application Support/HomelabBar/config.json`. To change it, use **Edit Config…** and then **Reload Config** in the menu. `HOMELABBAR_CONFIG` or `--config` overrides the path.

`homelabbar --once` runs a single refresh and prints the menu as text. It works over SSH or on Linux, and exits non-zero if anything is down.

## Config

```json
{
  "refresh_seconds": 30,
  "timeout_seconds": 3,
  "notify": true,
  "ssh_user": "peter",
  "tailscale_cli": "",
  "hide_offline_peers": false,
  "watch_peers": ["ubuntu-sumrall"],
  "services": [
    {"name": "ubuntu-sumrall SSH", "type": "tcp", "host": "ubuntu-sumrall", "port": 22},
    {"name": "Grafana", "type": "http", "url": "https://ubuntu-sumrall:3000/api/health"},
    {"name": "Router UI", "type": "http", "url": "https://192.168.1.1/", "verify_tls": false, "expect": [200, 401]}
  ]
}
```

| key | meaning |
| --- | --- |
| `type: tcp` | healthy if `host:port` accepts a connection |
| `type: http` | healthy on any 2xx/3xx, or on one of the codes in `expect` if that's set |
| `verify_tls` | set `false` for self-signed certs |
| `open` | URL for the service's **Open** item (http services default to `url`) |
| `ssh_user` | prefixed to SSH targets; leave empty to let `~/.ssh/config` decide |

A bad entry is skipped and flagged in the menu. It never stops the app.

## Notes

- Notifications go through `osascript`. The first one may ask you to allow notifications for Script Editor in System Settings → Notifications.
- The app runs as a menu-bar-only process, with no Dock icon.
- `rumps` 0.4 never releases menu-item callbacks. `app.py` prunes its registry on each rebuild, so long uptimes don't leak memory.

## Development

```bash
.venv/bin/pip install -e '.[test]' && .venv/bin/pytest
```

The core (`tailscale`, `checks`, `config`, `snapshot`, `menu`) uses only the standard library and is tested on any OS. `app.py` is the only file that imports `rumps`, and a stub-`rumps` smoke test covers it.
