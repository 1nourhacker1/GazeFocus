# GazeFocus

Webcam "focus follows gaze" for a two-monitor Windows desk. Look at a screen, and keyboard focus goes to the last window you used there. A Liquid Glass status dock sits under the laptop camera.

**Status: Plan 4 of 4: the "follow the drop" calibration (accepted at the desk 2026-09-30).** `gazefocus run` is the real app: focus follows your gaze, the dock under the laptop camera shows what it's doing, and Recalibrate guides you with a glowing drop.

## Using it
- Start it with `uv run gazefocus run`. A two-tile icon appears in the tray (possibly under the ^ overflow arrow).
- **Before a video call, press Ctrl+Alt+G** (or tray → Pause). This webcam can't be shared, so pausing releases it. Press it again afterwards.
- **The dock** sits under the laptop camera. The bigger tile holds the water: that's where focus is. Amber water under a lid means frozen while you type; steam means no face; bars mean paused; "!" means something needs you.
  - **Hover** it for the live camera preview, the numbers, and Pause/Recalibrate. **Click** it to pause (or, when it shows "!" because there's no calibration, to calibrate).
  - It never takes focus, and it hides under fullscreen apps and while the screen is locked.
- **Recalibrate** (the tray, or the dock's panel; it opens by itself the first time):
  - The dock asks first: **Start** or **Not now**.
  - The screens dim, and a green drop tours the LG, then the laptop. Follow it with your eyes and turn your head naturally (about 17 s). It waits if it can't see your face.
  - The beeps still mark each step: 1 = the LG, 2 = the laptop, 3 = done.
  - The dock then shows the result: the samples, the separation, and the water already following the new calibration. **Save** or **Redo**.
  - **Esc** cancels at any point, and so do pausing and locking the screen. The previous calibration is kept.
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
| `uv run gazefocus dock-demo` | The dock on its own, cycling through every state (no camera); hover it for the panel |
| `uv run gazefocus live` | Live mirrored camera window: face box, eye points, head-direction arrow, yaw/pitch (q quits) |
| `uv run gazefocus calibrate-cli` | Look at the LG, then the laptop (6 s each); saves `%APPDATA%\GazeFocus\calibration.json` |
| `uv run gazefocus watch [--record FILE]` | Live: which screen you're looking at, the margin bar, and the switches it would make |
| `uv run gazefocus replay FILE` | Run a recording back through the logic; use it to tune `config.toml` |
| `uv run gazefocus bench [--minutes 10]` | CPU and RAM against the budget (≤ 2 % CPU, ≤ 300 MB) |

Settings: `%APPDATA%\GazeFocus\config.toml`, written with the defaults on first run. The dock's are under `[dock]`: `scale` (2.625: the pill is 115.5 × 52.5), `refraction` (the lens rim) and `enabled`. A config.toml written before Plan 3 pins `scale = 1.75`: set it to 2.625 for the current size.
Camera frames are never saved; recordings hold only head angles and timings.

Design: `docs/superpowers/specs/2026-09-29-gazefocus-design.md` · Docs index: `docs/treestruct.md`
