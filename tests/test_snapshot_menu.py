import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from homelabbar.__main__ import main
from homelabbar.checks import CheckResult, Service
from homelabbar.config import Config
from homelabbar.menu import ago, build_menu, render_text
from homelabbar.snapshot import Snapshot, collect, summarize, transitions
from homelabbar.tailscale import TailscaleError, parse_status

FIXTURE = Path(__file__).parent / "fixtures" / "status.json"
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
SSH = Service("ssh", "tcp", host="ubuntu-sumrall", port=22)
WEB = Service("web", "http", url="https://grafana.lan")


def status():
    return parse_status(json.loads(FIXTURE.read_text()))


def snap(ssh_ok=True, web_ok=True, st="fixture", err=""):
    return Snapshot(
        taken_at=NOW,
        status=status() if st == "fixture" else st,
        tailscale_error=err,
        results=(
            CheckResult(SSH, ssh_ok, "open" if ssh_ok else "connection refused", 12.0 if ssh_ok else None),
            CheckResult(WEB, web_ok, "HTTP 200" if web_ok else "HTTP 502", 40.0),
        ),
    )


def test_summarize():
    assert summarize(None) == "⌂ …"
    assert summarize(snap()) == "⌂ ✓"
    assert summarize(snap(ssh_ok=False, web_ok=False)) == "⌂ ✗2"
    assert summarize(snap(st=None, err="not found")) == "⌂ ⚠"


def test_collect_with_stubs():
    config = Config(services=(SSH,))

    def checker(services, timeout):
        return [CheckResult(s, True, "open", 1.0) for s in services]

    s = collect(config, cli_finder=lambda _: "/bin/tailscale", status_fetcher=lambda _: status(), checker=checker)
    assert s.tailscale_ok and len(s.results) == 1

    def boom(_):
        raise TailscaleError("tailscaled not running")

    s = collect(config, cli_finder=lambda _: "/bin/tailscale", status_fetcher=boom, checker=checker)
    assert s.tailscale_error == "tailscaled not running" and s.status is None

    s = collect(config, cli_finder=lambda _: None, checker=checker)
    assert "not found" in s.tailscale_error


def test_transitions_baseline_is_silent():
    assert transitions(None, snap(ssh_ok=False)) == []


def test_transitions_service_down_and_up():
    down = transitions(snap(), snap(ssh_ok=False))
    assert down == [("ssh is down", "ubuntu-sumrall:22 · connection refused")]
    up = transitions(snap(ssh_ok=False), snap())
    assert up == [("ssh recovered", "ubuntu-sumrall:22 · open")]
    assert transitions(snap(), snap()) == []


def test_transitions_tailscale_and_peers():
    events = transitions(snap(), snap(st=None, err="stopped"), watch_peers=("ubuntu-sumrall",))
    assert events == [("Tailscale is not running", "stopped")]

    st = status()
    offline = replace(st, peers=tuple(replace(p, online=False) if p.name == "ubuntu-sumrall" else p for p in st.peers))
    events = transitions(snap(), snap(st=offline), watch_peers=("Ubuntu-Sumrall",))
    assert events == [("Ubuntu-Sumrall is offline", "Tailscale peer")]


def test_ago():
    assert ago(None, NOW) == "never seen"
    assert ago(datetime(2026, 9, 27, 11, 59, 30, tzinfo=timezone.utc), NOW) == "just now"
    assert ago(datetime(2026, 9, 27, 11, 15, tzinfo=timezone.utc), NOW) == "45m ago"
    assert ago(datetime(2026, 9, 24, 10, tzinfo=timezone.utc), NOW) == "3d ago"


def _titles(items):
    return [i.title for i in items if i is not None]


def test_build_menu_initial():
    assert _titles(build_menu(None, Config()))[0] == "Checking…"


def test_build_menu_full():
    items = build_menu(snap(web_ok=False), Config(ssh_user="peter"), now=NOW)
    titles = _titles(items)
    assert titles[0] == "Tailnet example@github · Running"
    assert "Exit node: ubuntu-sumrall" in titles
    assert "Services · 1/2 up" in titles
    assert "🟢 ssh · 12 ms" in titles
    assert "🔴 web · HTTP 502" in titles
    assert "Peers · 2/3 online" in titles
    assert "🟢 peters-macbook-pro · 100.64.0.1 · this Mac" in titles
    assert "⚪ old-pi · 100.64.0.3 · 3d ago" in titles
    assert titles[-1] == "Quit HomelabBar"

    server = next(i for i in items if i and i.title.startswith("🟢 ubuntu-sumrall"))
    assert server.title == "🟢 ubuntu-sumrall · 100.64.0.2 · exit node"
    actions = [c.action for c in server.children if c and c.action]
    assert ("ssh", "peter@ubuntu-sumrall.tail1234.ts.net") in actions
    assert ("copy", "100.64.0.2") in actions

    phone = next(i for i in items if i and i.title.startswith("🟢 iphone"))
    assert not any(c and c.action and c.action[0] == "ssh" for c in phone.children)

    me = next(i for i in items if i and "this Mac" in i.title)
    assert not any(c and c.action and c.action[0] == "ssh" for c in me.children)

    web = next(i for i in items if i and i.title.startswith("🔴 web"))
    assert ("open", "https://grafana.lan") in [c.action for c in web.children if c]


def test_build_menu_hide_offline_and_tailscale_error():
    titles = _titles(build_menu(snap(), Config(hide_offline_peers=True), now=NOW))
    assert not any("old-pi" in t for t in titles)
    assert "Peers · 2/3 online" in titles

    titles = _titles(build_menu(snap(st=None, err="tailscale CLI not found"), Config()))
    assert titles[0] == "⚠ Tailscale: tailscale CLI not found"
    assert not any(t.startswith("Peers") for t in titles)


def test_render_text_nests():
    text = render_text(build_menu(snap(), Config(), now=NOW))
    assert "    Copy IP  [copy 100.64.0.2]" in text


def test_main_once(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no tailscale on PATH
    monkeypatch.setattr("homelabbar.tailscale.CLI_CANDIDATES", ())
    cfg = tmp_path / "config.json"
    cfg.write_text('{"services": []}')
    assert main(["--config", str(cfg), "--once"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("⌂ ⚠")
    assert "tailscale CLI not found" in out
