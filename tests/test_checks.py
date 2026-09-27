import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from homelabbar.checks import Service, check, run_checks


@pytest.fixture
def http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code = int(self.path.strip("/") or 200)
            self.send_response(code)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_tcp_open():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        r = check(Service("x", "tcp", host="127.0.0.1", port=listener.getsockname()[1]), 2)
    assert r.ok and r.detail == "open" and r.latency_ms is not None


def test_tcp_refused():
    r = check(Service("x", "tcp", host="127.0.0.1", port=closed_port()), 2)
    assert not r.ok and r.detail == "connection refused"


def test_tcp_bad_host():
    r = check(Service("x", "tcp", host="no-such-host.invalid", port=22), 2)
    assert not r.ok and r.detail == "DNS lookup failed"


@pytest.mark.parametrize(
    "path,expect,ok",
    [
        ("/200", (), True),
        ("/302", (), True),
        ("/401", (), False),
        ("/500", (), False),
        ("/401", (401,), True),
        ("/200", (204,), False),
    ],
)
def test_http_status(http_server, path, expect, ok):
    r = check(Service("x", "http", url=http_server + path, expect=expect), 2)
    assert r.ok is ok
    assert r.detail == f"HTTP {path[1:]}"


def test_http_refused():
    r = check(Service("x", "http", url=f"http://127.0.0.1:{closed_port()}/"), 2)
    assert not r.ok and r.detail == "connection refused"


def test_run_checks_preserves_order():
    port = closed_port()
    services = [Service(f"s{i}", "tcp", host="127.0.0.1", port=port) for i in range(5)]
    assert [r.service.name for r in run_checks(services, 1)] == [s.name for s in services]
    assert run_checks([], 1) == []
