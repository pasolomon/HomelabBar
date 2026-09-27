"""Toolkit-neutral menu model. app.py turns it into rumps items; --once prints it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .checks import CheckResult
from .config import Config
from .snapshot import Snapshot
from .tailscale import Peer

NO_SSH_OS = {"ios", "tvos", "android"}

# Actions: ("refresh",) ("edit_config",) ("reload_config",) ("quit",)
#          ("copy", text) ("open", url) ("ssh", "user@host")


@dataclass
class Item:
    title: str
    action: tuple | None = None
    children: list[Item | None] = field(default_factory=list)


def ago(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "never seen"
    secs = int(((now or datetime.now(timezone.utc)) - dt).total_seconds())
    if secs < 60:
        return "just now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if secs >= size:
            return f"{secs // size}{unit} ago"
    return "just now"


def _clip(text: str, width: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def service_item(r: CheckResult) -> Item:
    svc = r.service
    if r.ok:
        latency = f" · {r.latency_ms:.0f} ms" if r.latency_ms is not None else ""
        title = f"🟢 {svc.name}{latency}"
    else:
        title = f"🔴 {svc.name} · {_clip(r.detail, 40)}"
    children: list[Item | None] = [Item(f"{svc.target} · {r.detail}")]
    open_url = svc.open_url or (svc.url if svc.kind == "http" else "")
    if open_url:
        children.append(Item("Open", ("open", open_url)))
    children.append(Item("Copy Address", ("copy", svc.target)))
    return Item(title, children=children)


def peer_item(p: Peer, config: Config, now: datetime | None = None) -> Item:
    dot = "🟢" if p.online or p.is_self else "⚪"
    parts = [f"{dot} {p.name}"]
    if p.ipv4:
        parts.append(p.ipv4)
    if p.is_self:
        parts.append("this Mac")
    if p.exit_node:
        parts.append("exit node")
    if not p.online and not p.is_self:
        parts.append(ago(p.last_seen, now))

    detail = " · ".join(x for x in (p.os, p.connection) if x)
    children: list[Item | None] = [Item(detail or p.hostname)]
    if p.tags:
        children.append(Item("Tags: " + ", ".join(p.tags)))
    children.append(None)
    if not p.is_self and p.address and p.os.lower() not in NO_SSH_OS:
        target = f"{config.ssh_user}@{p.address}" if config.ssh_user else p.address
        children.append(Item(f"SSH {target}", ("ssh", target)))
    if p.ipv4:
        children.append(Item("Copy IP", ("copy", p.ipv4)))
    if p.dns_name:
        children.append(Item("Copy DNS Name", ("copy", p.address)))
    return Item(" · ".join(parts), children=children)


FOOTER: list[Item | None] = [
    Item("Refresh Now", ("refresh",)),
    Item("Edit Config…", ("edit_config",)),
    Item("Reload Config", ("reload_config",)),
    None,
    Item("Quit HomelabBar", ("quit",)),
]


def build_menu(s: Snapshot | None, config: Config, now: datetime | None = None) -> list[Item | None]:
    items: list[Item | None] = []
    if s is None:
        return [Item("Checking…"), None, *FOOTER]

    st = s.status
    if st is not None:
        items.append(Item(f"Tailnet {st.tailnet or '—'} · {st.backend_state}"))
        if st.exit_node:
            items.append(Item(f"Exit node: {st.exit_node.name}"))
        items.extend(Item(f"⚠ {_clip(h)}") for h in st.health[:3])
    else:
        items.append(Item(f"⚠ Tailscale: {_clip(s.tailscale_error)}"))
    items.append(Item(f"Updated {s.taken_at.astimezone().strftime('%H:%M:%S')}"))
    items.extend(Item(f"⚠ Config: {_clip(e)}") for e in s.config_errors[:5])

    items.append(None)
    if s.results:
        up = len(s.results) - len(s.down)
        items.append(Item(f"Services · {up}/{len(s.results)} up"))
        items.extend(service_item(r) for r in s.results)
    else:
        items.append(Item("No services configured"))

    if st is not None:
        peers = st.all_peers()
        others = [p for p in peers if not p.is_self]
        online = sum(p.online for p in others)
        if config.hide_offline_peers:
            peers = [p for p in peers if p.online or p.is_self]
        items.append(None)
        items.append(Item(f"Peers · {online}/{len(others)} online"))
        items.extend(peer_item(p, config, now) for p in peers)

    items.append(None)
    items.extend(FOOTER)
    return items


def render_text(items: list[Item | None], depth: int = 0) -> str:
    lines = []
    pad = "    " * depth
    for it in items:
        if it is None:
            lines.append(pad + "──────")
            continue
        suffix = f"  [{' '.join(map(str, it.action))}]" if it.action else ""
        lines.append(pad + it.title + suffix)
        if it.children:
            lines.append(render_text(it.children, depth + 1))
    return "\n".join(lines)
