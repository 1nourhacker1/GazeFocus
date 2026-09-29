# GazeFocus

Webcam "focus follows gaze" for a two-monitor Windows desk. Look at a screen, and keyboard focus goes to the last window you used there. A Liquid Glass status dock sits under the laptop camera.

**Status: Plan 2 of 3.** `gazefocus run` is the real app: focus follows your gaze. Plan 3 adds the Liquid Glass dock and the calibration overlay.

## Using it
- Start it with `uv run gazefocus run`. A two-tile icon appears in the tray (possibly under the ^ overflow arrow).
- **Before a video call, press Ctrl+Alt+G** (or tray → Pause). This webcam can't be shared, so pausing releases it. Press it again afterwards.
- **Recalibrate** is in the tray. Listen for the beeps: 1 = look at the LG, 2 = the laptop, 3 = done.
- Logs are in `%APPDATA%\GazeFocus\logs`. `decisions.log` has one line per switch or block.

## Setup
```bash
uv sync
uv run python scripts/fetch_model.py   # MediaPipe face model, SHA-256 checked
uv run pytest
```

## Commands
| Command | What it does |
|---|---|
| `uv run gazefocus run` | The background app: tray icon, real focus switching; Ctrl+Alt+G pauses and releases the camera |
| `uv run gazefocus diag monitors \| windows \| focus LG` | Check the Windows side: the layout, focus targets per screen, a single focus switch |
| `uv run gazefocus probe` | Guided measurement of tracking range, yaw sign and speed (spike M0-A) |
| `uv run gazefocus live` | Live mirrored camera window: face box, eye points, head-direction arrow, yaw/pitch (q quits) |
| `uv run gazefocus calibrate-cli` | Look at the LG, then the laptop (6 s each); saves `%APPDATA%\GazeFocus\calibration.json` |
| `uv run gazefocus watch [--record FILE]` | Live: which screen you're looking at, the margin bar, and the switches it would make |
| `uv run gazefocus replay FILE` | Run a recording back through the logic; use it to tune `config.toml` |
| `uv run gazefocus bench [--minutes 10]` | CPU and RAM against the budget (≤ 2 % CPU, ≤ 300 MB) |

Settings: `%APPDATA%\GazeFocus\config.toml`, written with the defaults on first run.
Camera frames are never saved; recordings hold only head angles and timings.

Design: `docs/superpowers/specs/2026-09-29-gazefocus-design.md` · Docs index: `docs/treestruct.md`
