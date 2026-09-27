"""Read tailnet state from the local `tailscale` CLI (`tailscale status --json`)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

# launchd hands agents a minimal PATH, so check the usual install spots explicitly.
CLI_CANDIDATES = (
    "/opt/homebrew/bin/tailscale",
    "/usr/local/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
)


class TailscaleError(Exception):
    pass


@dataclass(frozen=True)
class Peer:
    id: str
    hostname: str
    dns_name: str
    os: str
    ips: tuple[str, ...]
    online: bool
    is_self: bool = False
    exit_node: bool = False
    exit_node_option: bool = False
    active: bool = False
    relay: str = ""
    cur_addr: str = ""
    tags: tuple[str, ...] = ()
    last_seen: datetime | None = None

    @property
    def name(self) -> str:
        return self.dns_name.split(".", 1)[0] or self.hostname or self.id

    @property
    def ipv4(self) -> str:
        return next((ip for ip in self.ips if ":" not in ip), self.ips[0] if self.ips else "")

    @property
    def address(self) -> str:
        """Best thing to hand ssh/open: the MagicDNS name, else the IPv4."""
        return self.dns_name.rstrip(".") or self.ipv4

    @property
    def connection(self) -> str:
        if self.cur_addr:
            return "direct"
        if self.relay:
            return f"relay {self.relay}"
        return ""


@dataclass(frozen=True)
class TailnetStatus:
    backend_state: str
    version: str
    tailnet: str
    magic_dns_suffix: str
    self_peer: Peer | None
    peers: tuple[Peer, ...]
    health: tuple[str, ...] = ()

    @property
    def running(self) -> bool:
        return self.backend_state == "Running"

    @property
    def exit_node(self) -> Peer | None:
        return next((p for p in self.peers if p.exit_node), None)

    def all_peers(self) -> list[Peer]:
        return ([self.self_peer] if self.self_peer else []) + list(self.peers)


_FRACTION = re.compile(r"\.(\d+)")


def parse_go_time(value: str | None) -> datetime | None:
    """Parse Go's RFC3339Nano output; Go's zero time means 'never'."""
    if not value or value.startswith("0001-01-01"):
        return None
    s = value[:-1] + "+00:00" if value.endswith("Z") else value
    # Python <3.11 only takes 3 or 6 fractional digits; Go emits up to 9.
    s = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), s, count=1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _peer(d: dict, is_self: bool = False) -> Peer:
    return Peer(
        id=str(d.get("ID") or ""),
        hostname=d.get("HostName") or "",
        dns_name=d.get("DNSName") or "",
        os=d.get("OS") or "",
        ips=tuple(d.get("TailscaleIPs") or ()),
        online=bool(d.get("Online")),
        is_self=is_self,
        exit_node=bool(d.get("ExitNode")),
        exit_node_option=bool(d.get("ExitNodeOption")),
        active=bool(d.get("Active")),
        relay=d.get("Relay") or "",
        cur_addr=d.get("CurAddr") or "",
        tags=tuple(d.get("Tags") or ()),
        last_seen=parse_go_time(d.get("LastSeen")),
    )


def parse_status(data: object) -> TailnetStatus:
    if not isinstance(data, dict):
        raise TailscaleError("unexpected status JSON")
    self_d = data.get("Self")
    peers = [_peer(p) for p in (data.get("Peer") or {}).values()]
    peers.sort(key=lambda p: (not p.online, p.name.lower()))
    tailnet = data.get("CurrentTailnet") or {}
    return TailnetStatus(
        backend_state=data.get("BackendState") or "Unknown",
        version=data.get("Version") or "",
        tailnet=tailnet.get("Name") or "",
        magic_dns_suffix=data.get("MagicDNSSuffix") or tailnet.get("MagicDNSSuffix") or "",
        self_peer=_peer(self_d, is_self=True) if self_d else None,
        peers=tuple(peers),
        health=tuple(data.get("Health") or ()),
    )


def find_cli(override: str = "") -> str | None:
    if override:
        return override if os.access(override, os.X_OK) else None
    found = shutil.which("tailscale")
    if found:
        return found
    return next((c for c in CLI_CANDIDATES if os.access(c, os.X_OK)), None)


def fetch_status(cli: str, timeout: float = 10.0) -> TailnetStatus:
    try:
        proc = subprocess.run(
            [cli, "status", "--json"], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise TailscaleError(f"tailscale status timed out after {timeout:g}s") from None
    except OSError as e:
        raise TailscaleError(f"cannot run {cli}: {e.strerror or e}") from None
    out = proc.stdout.strip()
    if not out:
        raise TailscaleError(_first_line(proc.stderr) or f"tailscale exited {proc.returncode}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise TailscaleError(_first_line(proc.stderr) or _first_line(out)) from None
    return parse_status(data)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")
