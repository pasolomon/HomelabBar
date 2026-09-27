"""JSON config: load, validate, and write the first-run default."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .checks import Service

APP_NAME = "HomelabBar"

DEFAULT_CONFIG = {
    "refresh_seconds": 30,
    "timeout_seconds": 3,
    "notify": True,
    "ssh_user": "",
    "tailscale_cli": "",
    "hide_offline_peers": False,
    "watch_peers": ["ubuntu-sumrall"],
    "services": [
        {"name": "ubuntu-sumrall SSH", "type": "tcp", "host": "ubuntu-sumrall", "port": 22},
    ],
}


@dataclass(frozen=True)
class Config:
    refresh_seconds: int = 30
    timeout_seconds: float = 3.0
    notify: bool = True
    ssh_user: str = ""
    tailscale_cli: str = ""
    hide_offline_peers: bool = False
    watch_peers: tuple[str, ...] = ()
    services: tuple[Service, ...] = ()


def default_path() -> Path:
    if os.environ.get("HOMELABBAR_CONFIG"):
        return Path(os.environ["HOMELABBAR_CONFIG"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "config.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "homelabbar" / "config.json"


def ensure_config(path: Path) -> bool:
    """Write the default config if none exists. Returns True if it was created."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    return True


def load_config(path: Path) -> tuple[Config, list[str]]:
    """Never raises on bad content: returns defaults plus human-readable errors."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return Config(), [f"{path} not found"]
    except (OSError, json.JSONDecodeError) as e:
        return Config(), [f"cannot read config: {e}"]
    return parse_config(data)


def _number(data: dict, key: str, default: float, lo: float, hi: float, errors: list[str]) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{key} must be a number")
        return default
    if not lo <= value <= hi:
        errors.append(f"{key} clamped to {lo:g}–{hi:g}")
        return min(max(value, lo), hi)
    return value


def _service(raw: object, index: int, errors: list[str]) -> Service | None:
    where = f"services[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{where} must be an object")
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{where} needs a name")
        return None
    name = name.strip()
    kind = raw.get("type", "tcp")
    open_url = raw.get("open") or ""
    if kind == "tcp":
        host, port = raw.get("host"), raw.get("port")
        if not isinstance(host, str) or not host:
            errors.append(f"{name}: tcp needs host")
            return None
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            errors.append(f"{name}: tcp needs port 1–65535")
            return None
        return Service(name=name, kind="tcp", host=host, port=port, open_url=open_url)
    if kind == "http":
        url = raw.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            errors.append(f"{name}: http needs an http(s):// url")
            return None
        expect = raw.get("expect", [])
        if isinstance(expect, int) and not isinstance(expect, bool):
            expect = [expect]
        if not isinstance(expect, list) or not all(
            isinstance(c, int) and not isinstance(c, bool) for c in expect
        ):
            errors.append(f"{name}: expect must be a status code or list of them")
            expect = []
        return Service(
            name=name,
            kind="http",
            url=url,
            expect=tuple(expect),
            verify_tls=bool(raw.get("verify_tls", True)),
            open_url=open_url,
        )
    errors.append(f"{name}: unknown type {kind!r} (use tcp or http)")
    return None


def parse_config(data: object) -> tuple[Config, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return Config(), ["config must be a JSON object"]

    services: list[Service] = []
    seen: set[str] = set()
    raw_services = data.get("services", [])
    if not isinstance(raw_services, list):
        errors.append("services must be a list")
        raw_services = []
    for i, raw in enumerate(raw_services):
        svc = _service(raw, i, errors)
        if svc is None:
            continue
        if svc.name.lower() in seen:
            errors.append(f"duplicate service name {svc.name!r} skipped")
            continue
        seen.add(svc.name.lower())
        services.append(svc)

    watch = data.get("watch_peers", [])
    if not isinstance(watch, list) or not all(isinstance(w, str) for w in watch):
        errors.append("watch_peers must be a list of hostnames")
        watch = []

    config = Config(
        refresh_seconds=int(_number(data, "refresh_seconds", 30, 5, 3600, errors)),
        timeout_seconds=float(_number(data, "timeout_seconds", 3, 0.5, 30, errors)),
        notify=bool(data.get("notify", True)),
        ssh_user=str(data.get("ssh_user") or ""),
        tailscale_cli=str(data.get("tailscale_cli") or ""),
        hide_offline_peers=bool(data.get("hide_offline_peers", False)),
        watch_peers=tuple(watch),
        services=tuple(services),
    )
    return config, errors
