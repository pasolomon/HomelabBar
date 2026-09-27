import json

from homelabbar.config import DEFAULT_CONFIG, ensure_config, load_config, parse_config


def test_default_config_is_valid():
    config, errors = parse_config(DEFAULT_CONFIG)
    assert errors == []
    assert config.services[0].target == "ubuntu-sumrall:22"


def test_ensure_config_writes_once(tmp_path):
    path = tmp_path / "sub" / "config.json"
    assert ensure_config(path)
    path.write_text('{"refresh_seconds": 60}')
    assert not ensure_config(path)
    assert load_config(path)[0].refresh_seconds == 60


def test_load_config_bad_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{nope")
    config, errors = load_config(path)
    assert config.services == ()
    assert errors and "cannot read config" in errors[0]


def test_http_service_options():
    config, errors = parse_config(
        {
            "services": [
                {"name": "Grafana", "type": "http", "url": "https://grafana.lan", "expect": 401,
                 "verify_tls": False, "open": "https://grafana.lan/d/home"},
            ]
        }
    )
    assert errors == []
    svc = config.services[0]
    assert svc.expect == (401,) and not svc.verify_tls and svc.open_url.endswith("/home")


def test_invalid_services_are_skipped_with_errors():
    config, errors = parse_config(
        {
            "services": [
                {"name": "ok", "type": "tcp", "host": "h", "port": 22},
                {"name": "OK", "type": "tcp", "host": "h", "port": 23},
                {"type": "tcp", "host": "h", "port": 22},
                {"name": "badport", "type": "tcp", "host": "h", "port": 70000},
                {"name": "boolport", "type": "tcp", "host": "h", "port": True},
                {"name": "badurl", "type": "http", "url": "ftp://x"},
                {"name": "weird", "type": "icmp"},
                "string",
            ]
        }
    )
    assert [s.name for s in config.services] == ["ok"]
    assert len(errors) == 7


def test_numbers_clamped_and_typed():
    config, errors = parse_config({"refresh_seconds": 1, "timeout_seconds": "fast"})
    assert config.refresh_seconds == 5
    assert config.timeout_seconds == 3.0
    assert len(errors) == 2


def test_non_object():
    config, errors = parse_config(json.loads("[]"))
    assert errors == ["config must be a JSON object"]
