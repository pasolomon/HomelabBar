"""One refresh cycle's worth of state, plus the logic that interprets it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .checks import CheckResult, run_checks
from .config import Config
from .tailscale import TailnetStatus, TailscaleError, fetch_status, find_cli


@dataclass(frozen=True)
class Snapshot:
    taken_at: datetime
    status: TailnetStatus | None
    tailscale_error: str
    results: tuple[CheckResult, ...]
    config_errors: tuple[str, ...] = ()

    @property
    def down(self) -> list[CheckResult]:
        return [r for r in self.results if not r.ok]

    @property
    def tailscale_ok(self) -> bool:
        return self.status is not None and self.status.running


def collect(
    config: Config,
    config_errors: tuple[str, ...] = (),
    *,
    cli_finder: Callable[[str], str | None] = find_cli,
    status_fetcher: Callable[[str], TailnetStatus] = fetch_status,
    checker: Callable[..., list[CheckResult]] = run_checks,
) -> Snapshot:
    status, error = None, ""
    cli = cli_finder(config.tailscale_cli)
    if cli is None:
        error = "tailscale CLI not found (set tailscale_cli in config)"
    else:
        try:
            status = status_fetcher(cli)
        except TailscaleError as e:
            error = str(e)
    results = checker(config.services, config.timeout_seconds)
    return Snapshot(
        taken_at=datetime.now(timezone.utc),
        status=status,
        tailscale_error=error,
        results=tuple(results),
        config_errors=tuple(config_errors),
    )


def summarize(s: Snapshot | None) -> str:
    """Menu-bar title."""
    if s is None:
        return "⌂ …"
    if not s.tailscale_ok:
        return "⌂ ⚠"
    down = len(s.down)
    return f"⌂ ✗{down}" if down else "⌂ ✓"


def _peer_online(s: Snapshot) -> dict[str, bool]:
    if s.status is None:
        return {}
    out: dict[str, bool] = {}
    for p in s.status.peers:
        out[p.name.lower()] = p.online
        out.setdefault(p.hostname.lower(), p.online)
    return out


def transitions(
    prev: Snapshot | None, cur: Snapshot, watch_peers: tuple[str, ...] = ()
) -> list[tuple[str, str]]:
    """(title, message) notifications for state changes since the last snapshot.

    The first snapshot establishes a baseline and produces nothing.
    """
    if prev is None:
        return []
    events: list[tuple[str, str]] = []

    if prev.tailscale_ok and not cur.tailscale_ok:
        why = cur.status.backend_state if cur.status else cur.tailscale_error
        events.append(("Tailscale is not running", why))
    elif not prev.tailscale_ok and cur.tailscale_ok:
        events.append(("Tailscale is running", cur.status.tailnet if cur.status else ""))

    before = {r.service.name: r.ok for r in prev.results}
    for r in cur.results:
        was = before.get(r.service.name)
        if was is None or was == r.ok:
            continue
        if r.ok:
            events.append((f"{r.service.name} recovered", f"{r.service.target} · {r.detail}"))
        else:
            events.append((f"{r.service.name} is down", f"{r.service.target} · {r.detail}"))

    # Only compare peers when both snapshots actually saw the tailnet;
    # a Tailscale outage is reported once above, not once per peer.
    if watch_peers and prev.tailscale_ok and cur.tailscale_ok:
        old, new = _peer_online(prev), _peer_online(cur)
        for name in watch_peers:
            key = name.lower()
            if key in old and key in new and old[key] != new[key]:
                state = "back online" if new[key] else "offline"
                events.append((f"{name} is {state}", "Tailscale peer"))
    return events
