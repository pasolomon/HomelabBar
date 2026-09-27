from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import default_path, ensure_config, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homelabbar", description="Tailscale + homelab menu-bar monitor")
    parser.add_argument("--config", type=Path, default=None, help="config file (default: %(default)s)")
    parser.add_argument("--once", action="store_true", help="run one refresh, print the menu, exit")
    args = parser.parse_args(argv)
    path = (args.config or default_path()).expanduser()

    if args.once:
        from .menu import build_menu, render_text
        from .snapshot import collect, summarize

        if ensure_config(path):
            print(f"wrote default config to {path}", file=sys.stderr)
        config, errors = load_config(path)
        snapshot = collect(config, tuple(errors))
        print(summarize(snapshot))
        print(render_text(build_menu(snapshot, config)))
        return 1 if snapshot.down or not snapshot.tailscale_ok else 0

    if sys.platform != "darwin":
        parser.error("the menu-bar app is macOS-only; use --once elsewhere")
    from .app import run

    run(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
