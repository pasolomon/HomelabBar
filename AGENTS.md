# AGENTS.md — HomelabBar

Instructions for any coding agent working in this repository. `CLAUDE.md` imports this file with `@AGENTS.md`, so maintain instructions here.

## What this is
A macOS menu-bar app that shows the state of a Tailscale tailnet and whether a list of services is reachable.

## Read at session start
- `README.md`.

## Commands
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest
.venv/bin/homelabbar --once   # one refresh, printed as text; exits non-zero if anything is down
```

## Rules
- GitHub `main` is the source of truth. Fetch and fast-forward before working. Never force-push or rewrite history.
- This repository is public. Never commit secrets, credentials, tokens, or personal data.
- Commit only what you changed.
- Python 3.10 or newer. The only runtime dependency is `rumps`, on macOS.
- State comes from the local `tailscale status --json`. The app needs no API key; keep it that way.
- User configuration lives outside the repository. Do not commit real host names, addresses, or tailnet names; use the fixtures in `tests/fixtures/`.
- `--once` must keep working without a display, so it can run over SSH and in tests.

## Before you finish
- `.venv/bin/pytest` passes.
- Commit and push, then confirm the local branch matches `origin/main`.
