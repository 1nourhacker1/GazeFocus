# gazefocus/app/state.py
Verified against: GazeFocus@b322e17 · 2026-09-29

`AppState.status` returns the highest-priority reason:
calibrating > locked > asleep > paused > unsupported layout > not calibrated > layout changed > tracker failed (3 crashes) > camera unavailable > running.

- `camera_wanted` is True only in `RUNNING` or `CAMERA_WAIT` (retrying). Pause, lock, sleep and calibration all release the tracking camera.
- `switching` is True only in `RUNNING`.
- Manual pause (Ctrl+Alt+G or the tray) is how the camera is handed to a video call; that's the user's choice from 2026-09-29.
