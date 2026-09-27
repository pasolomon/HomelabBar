"""Service health checks: TCP connect and HTTP(S) GET."""

from __future__ import annotations

import socket
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    kind: str  # "tcp" | "http"
    host: str = ""
    port: int = 0
    url: str = ""
    expect: tuple[int, ...] = ()  # empty: any 2xx/3xx is healthy
    verify_tls: bool = True
    open_url: str = ""

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}" if self.kind == "tcp" else self.url


@dataclass(frozen=True)
class CheckResult:
    service: Service
    ok: bool
    detail: str
    latency_ms: float | None = None


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000


def check_tcp(svc: Service, timeout: float) -> CheckResult:
    start = time.monotonic()
    try:
        with socket.create_connection((svc.host, svc.port), timeout=timeout):
            pass
    except socket.gaierror:
        return CheckResult(svc, False, "DNS lookup failed")
    except TimeoutError:
        return CheckResult(svc, False, "timed out")
    except ConnectionRefusedError:
        return CheckResult(svc, False, "connection refused")
    except OSError as e:
        return CheckResult(svc, False, e.strerror or str(e))
    return CheckResult(svc, True, "open", _elapsed_ms(start))


def _unverified_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def check_http(svc: Service, timeout: float) -> CheckResult:
    ctx = None if svc.verify_tls else _unverified_context()
    req = urllib.request.Request(svc.url, headers={"User-Agent": "HomelabBar"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
        e.close()
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, TimeoutError):
            return CheckResult(svc, False, "timed out")
        if isinstance(reason, ssl.SSLCertVerificationError):
            return CheckResult(svc, False, "TLS certificate not trusted")
        if isinstance(reason, socket.gaierror):
            return CheckResult(svc, False, "DNS lookup failed")
        if isinstance(reason, ConnectionRefusedError):
            return CheckResult(svc, False, "connection refused")
        return CheckResult(svc, False, str(getattr(reason, "strerror", None) or reason))
    except TimeoutError:
        return CheckResult(svc, False, "timed out")
    except OSError as e:
        return CheckResult(svc, False, e.strerror or str(e))
    ok = code in svc.expect if svc.expect else 200 <= code < 400
    return CheckResult(svc, ok, f"HTTP {code}", _elapsed_ms(start))


def check(svc: Service, timeout: float) -> CheckResult:
    try:
        return check_tcp(svc, timeout) if svc.kind == "tcp" else check_http(svc, timeout)
    except Exception as e:  # a bad check must never take down the refresh loop
        return CheckResult(svc, False, f"check error: {e}")


def run_checks(services: tuple[Service, ...] | list[Service], timeout: float) -> list[CheckResult]:
    if not services:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(services))) as pool:
        return list(pool.map(lambda s: check(s, timeout), services))
