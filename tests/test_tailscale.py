import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homelabbar.tailscale import (
    TailscaleError,
    fetch_status,
    find_cli,
    parse_go_time,
    parse_status,
)

FIXTURE = Path(__file__).parent / "fixtures" / "status.json"


def load():
    return parse_status(json.loads(FIXTURE.read_text()))


def test_parse_status_basics():
    st = load()
    assert st.running
    assert st.tailnet == "example@github"
    assert st.magic_dns_suffix == "tail1234.ts.net"
    assert st.self_peer.is_self
    assert st.self_peer.name == "peters-macbook-pro"


def test_peers_sorted_online_first_then_name():
    assert [p.name for p in load().peers] == ["iphone", "ubuntu-sumrall", "old-pi"]


def test_peer_fields():
    by_name = {p.name: p for p in load().peers}
    srv = by_name["ubuntu-sumrall"]
    assert srv.ipv4 == "100.64.0.2"
    assert srv.address == "ubuntu-sumrall.tail1234.ts.net"
    assert srv.connection == "direct"
    assert srv.tags == ("tag:server",)
    assert srv.last_seen is None
    assert by_name["iphone"].connection == "relay mia"
    assert by_name["old-pi"].last_seen == datetime(2026, 9, 24, 10, 0, 0, 123456, tzinfo=timezone.utc)


def test_exit_node():
    assert load().exit_node.name == "ubuntu-sumrall"


def test_parse_status_tolerates_stopped_backend():
    st = parse_status({"BackendState": "Stopped", "Peer": None, "Self": None})
    assert not st.running
    assert st.peers == ()
    assert st.self_peer is None


def test_parse_status_rejects_non_object():
    with pytest.raises(TailscaleError):
        parse_status([])


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0001-01-01T00:00:00Z", None),
        ("", None),
        (None, None),
        ("garbage", None),
        ("2026-09-24T10:00:00Z", datetime(2026, 9, 24, 10, tzinfo=timezone.utc)),
        ("2026-09-24T10:00:00.5-05:00", datetime(2026, 9, 24, 15, 0, 0, 500000, tzinfo=timezone.utc)),
    ],
)
def test_parse_go_time(raw, expected):
    assert parse_go_time(raw) == expected


def _script(tmp_path, body):
    path = tmp_path / "tailscale"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_fetch_status_runs_cli(tmp_path):
    cli = _script(tmp_path, f'[ "$1 $2" = "status --json" ] || exit 2\ncat "{FIXTURE}"\n')
    assert fetch_status(cli).tailnet == "example@github"


def test_fetch_status_reports_stderr(tmp_path):
    cli = _script(tmp_path, 'echo "failed to connect to local tailscaled" >&2\nexit 1\n')
    with pytest.raises(TailscaleError, match="failed to connect"):
        fetch_status(cli)


def test_fetch_status_timeout(tmp_path):
    cli = _script(tmp_path, "sleep 5\n")
    with pytest.raises(TailscaleError, match="timed out"):
        fetch_status(cli, timeout=0.2)


def test_fetch_status_missing_binary(tmp_path):
    with pytest.raises(TailscaleError, match="cannot run"):
        fetch_status(str(tmp_path / "nope"))


def test_find_cli_override(tmp_path):
    cli = _script(tmp_path, "exit 0\n")
    assert find_cli(cli) == cli
    assert find_cli(str(tmp_path / "missing")) is None


def test_find_cli_uses_path(tmp_path, monkeypatch):
    cli = _script(tmp_path, "exit 0\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    assert find_cli() == cli
