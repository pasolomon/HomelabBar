"""Drive app.py against a stand-in rumps so the glue code runs off-Mac."""

import importlib
import sys
import types
from collections import OrderedDict

import pytest

from homelabbar.checks import CheckResult


def fake_rumps():
    mod = types.ModuleType("rumps")
    impl = types.ModuleType("rumps.rumps")

    class NSApp:
        _ns_to_py_and_callback = {}

    class Menu(OrderedDict):
        def update(self, items):
            for it in items:
                key = object() if it is mod.separator else it.title
                self[key] = it

    class MenuItem(Menu):
        def __init__(self, title, callback=None):
            super().__init__()
            self.title, self.callback = title, callback
            self._menuitem = object()
            NSApp._ns_to_py_and_callback[self._menuitem] = (self, callback)

    class Timer:
        def __init__(self, callback, interval):
            self.callback, self.interval, self.running = callback, interval, False

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    class App:
        def __init__(self, name, title=None, quit_button="Quit"):
            self.title, self.menu = title, Menu()

    impl.NSApp = NSApp
    mod.rumps = impl
    mod.separator = object()
    mod.Menu, mod.MenuItem, mod.Timer, mod.App = Menu, MenuItem, Timer, App
    mod.quit_application = lambda: setattr(mod, "quit_called", True)
    return mod


@pytest.fixture
def app_module(monkeypatch):
    rumps = fake_rumps()
    monkeypatch.setitem(sys.modules, "rumps", rumps)
    monkeypatch.delitem(sys.modules, "homelabbar.app", raising=False)
    app = importlib.import_module("homelabbar.app")
    calls = []
    for name in ("copy", "open_url", "edit", "notify"):
        monkeypatch.setattr(app.macos, name, lambda *a, _n=name: calls.append((_n, *a)))
    yield app, rumps, calls
    sys.modules.pop("homelabbar.app", None)


def test_app_refresh_render_dispatch(app_module, tmp_path, monkeypatch):
    app, rumps, calls = app_module
    cfg = tmp_path / "config.json"
    cfg.write_text('{"services": [{"name": "ssh", "type": "tcp", "host": "h", "port": 22}]}')

    state = {"ok": True}

    def fake_collect(config, errors):
        from homelabbar.snapshot import Snapshot
        from datetime import datetime, timezone

        svc = config.services[0]
        return Snapshot(datetime.now(timezone.utc), None, "no tailscale", (CheckResult(svc, state["ok"], "x", 1.0),))

    monkeypatch.setattr(app, "collect", fake_collect)
    a = app.HomelabBarApp(cfg)
    a._worker.join()
    a._apply_pending(None)
    assert a.title == "⌂ ⚠"
    titles = [k for k in a.menu if isinstance(k, str)]
    assert "🟢 ssh · 1 ms" in titles and "Quit HomelabBar" in titles

    # Service goes down: one notification, and the registry doesn't grow per render.
    size = len(rumps.rumps.NSApp._ns_to_py_and_callback)
    state["ok"] = False
    a._refresh()
    a._worker.join()
    a._apply_pending(None)
    assert ("notify", "ssh is down", "h:22 · x") in calls
    assert len(rumps.rumps.NSApp._ns_to_py_and_callback) == size

    # Menu callbacks route to the right actions.
    item = a.menu["🔴 ssh · x"]
    item["Copy Address"].callback(None)
    assert ("copy", "h:22") in calls
    a.menu["Edit Config…"].callback(None)
    assert ("edit", cfg) in calls
    cfg.write_text('{"refresh_seconds": 120, "services": [{"name": "ssh", "type": "tcp", "host": "h", "port": 22}]}')
    a.menu["Reload Config"].callback(None)
    assert a._refresh_timer.interval == 120
    a.menu["Quit HomelabBar"].callback(None)
    assert rumps.quit_called


def test_duplicate_titles_kept_distinct(app_module, tmp_path):
    app, _, _ = app_module
    from homelabbar.menu import Item

    cfg = tmp_path / "config.json"
    cfg.write_text('{"services": []}')
    a = app.HomelabBarApp.__new__(app.HomelabBarApp)
    out = a._to_rumps([Item("same"), Item("same")])
    assert len({i.title for i in out}) == 2
