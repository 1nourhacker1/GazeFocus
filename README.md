# GazeFocus

Webcam "focus follows gaze" for a two-monitor Windows desk. Look at a screen, and keyboard focus goes to the last window you used there. A Liquid Glass status dock sits under the laptop camera.

**Status: Plan 1 of 3.** These are terminal tools and a **dry run**: GazeFocus shows what it *would* do and focuses nothing yet.
Plan 2 adds the real focus switch; Plan 3 adds the dock and the calibration overlay.

## Setup
```bash
uv sync
uv run python scripts/fetch_model.py   # MediaPipe face model, SHA-256 checked
uv run pytest
```

## Commands
| Command | What it does |
|---|---|
| `uv run gazefocus probe` | Guided measurement of tracking range, yaw sign and speed (spike M0-A) |
| `uv run gazefocus live` | Live mirrored camera window: face box, eye points, head-direction arrow, yaw/pitch (q quits) |
| `uv run gazefocus calibrate-cli` | Look at the LG, then the laptop (6 s each); saves `%APPDATA%\GazeFocus\calibration.json` |
| `uv run gazefocus watch [--record FILE]` | Live: which screen you're looking at, the margin bar, and the switches it would make |
| `uv run gazefocus replay FILE` | Run a recording back through the logic; use it to tune `config.toml` |
| `uv run gazefocus bench [--minutes 10]` | CPU and RAM against the budget (≤ 2 % CPU, ≤ 300 MB) |

Settings: `%APPDATA%\GazeFocus\config.toml`, written with the defaults on first run.
Camera frames are never saved; recordings hold only head angles and timings.

Design: `docs/superpowers/specs/2026-09-29-gazefocus-design.md` · Docs index: `docs/treestruct.md`
