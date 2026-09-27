"""Thin wrappers over macOS command-line tools."""

from __future__ import annotations

import subprocess
from pathlib import Path


def copy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=False)


def open_url(url: str) -> None:
    # ssh:// URLs open a new Terminal window (or whatever handles ssh:// on this Mac).
    subprocess.run(["open", url], check=False)


def edit(path: Path) -> None:
    subprocess.run(["open", "-t", str(path)], check=False)


def notify(title: str, message: str) -> None:
    # Pass text as argv, never spliced into the script, so names can't break the AppleScript.
    subprocess.run(
        [
            "osascript",
            "-e", "on run argv",
            "-e", 'display notification (item 2 of argv) with title "HomelabBar" subtitle (item 1 of argv)',
            "-e", "end run",
            title,
            message,
        ],
        check=False,
        capture_output=True,
    )
