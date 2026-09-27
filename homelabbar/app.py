"""The menu-bar app (macOS only; needs rumps)."""

from __future__ import annotations

import threading
from pathlib import Path

import rumps

from . import macos
from .config import Config, ensure_config, load_config
from .menu import Item, build_menu
from .snapshot import Snapshot, collect, summarize, transitions

SEPARATOR = getattr(rumps, "separator", None)


def _forget_callbacks(menu) -> None:
    """Drop rumps' callback-registry entries for items about to be cleared.

    rumps 0.4 records every MenuItem in a class-level dict that Menu.clear() never
    prunes, so rebuilding the menu each refresh would leak without this.
    """
    registry = getattr(getattr(rumps.rumps, "NSApp", None), "_ns_to_py_and_callback", None)
    if registry is None:
        return
    for item in list(menu.values()):
        if isinstance(item, rumps.MenuItem):
            registry.pop(item._menuitem, None)
            _forget_callbacks(item)


class HomelabBarApp(rumps.App):
    def __init__(self, config_path: Path):
        super().__init__("HomelabBar", title=summarize(None), quit_button=None)
        self.config_path = config_path
        self.config = Config()
        self.config_errors: tuple[str, ...] = ()
        self._snapshot: Snapshot | None = None
        self._pending: Snapshot | None = None
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._refresh_timer: rumps.Timer | None = None

        self._load_config()
        self._render()
        # Checks run on a worker thread; results are applied on the main thread,
        # which is the only thread allowed to touch AppKit.
        self._apply_timer = rumps.Timer(self._apply_pending, 1)
        self._apply_timer.start()
        self._start_refresh_timer()
        self._refresh()

    # --- lifecycle -------------------------------------------------------

    def _load_config(self) -> None:
        ensure_config(self.config_path)
        self.config, errors = load_config(self.config_path)
        self.config_errors = tuple(errors)

    def _start_refresh_timer(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        self._refresh_timer = rumps.Timer(lambda _: self._refresh(), self.config.refresh_seconds)
        self._refresh_timer.start()

    def _refresh(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        config, errors = self.config, self.config_errors
        self._worker = threading.Thread(target=self._collect, args=(config, errors), daemon=True)
        self._worker.start()

    def _collect(self, config: Config, errors: tuple[str, ...]) -> None:
        snapshot = collect(config, errors)
        with self._lock:
            self._pending = snapshot

    def _apply_pending(self, _timer) -> None:
        with self._lock:
            snapshot, self._pending = self._pending, None
        if snapshot is None:
            return
        if self.config.notify:
            for title, message in transitions(self._snapshot, snapshot, self.config.watch_peers):
                macos.notify(title, message)
        self._snapshot = snapshot
        self._render()

    # --- menu ------------------------------------------------------------

    def _render(self) -> None:
        self.title = summarize(self._snapshot)
        _forget_callbacks(self.menu)
        self.menu.clear()
        self.menu.update(self._to_rumps(build_menu(self._snapshot, self.config)))

    def _to_rumps(self, items: list[Item | None]) -> list:
        out: list = []
        seen: set[str] = set()
        for it in items:
            if it is None:
                out.append(SEPARATOR)
                continue
            # rumps keys items by title, so equal titles in one menu would collapse.
            title = it.title
            while title in seen:
                title += "​"
            seen.add(title)
            mi = rumps.MenuItem(title, callback=self._callback(it.action) if it.action else None)
            if it.children:
                mi.update(self._to_rumps(it.children))
            out.append(mi)
        return out

    def _callback(self, action: tuple):
        return lambda _sender: self._dispatch(action)

    def _dispatch(self, action: tuple) -> None:
        kind, *args = action
        if kind == "refresh":
            self._refresh()
        elif kind == "copy":
            macos.copy(args[0])
        elif kind == "open":
            macos.open_url(args[0])
        elif kind == "ssh":
            macos.open_url("ssh://" + args[0])
        elif kind == "edit_config":
            macos.edit(self.config_path)
        elif kind == "reload_config":
            self._load_config()
            self._start_refresh_timer()
            self._render()
            self._refresh()
        elif kind == "quit":
            rumps.quit_application()


def run(config_path: Path) -> None:
    try:  # menu-bar only: no Dock icon, no app switcher entry
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    HomelabBarApp(config_path).run()
