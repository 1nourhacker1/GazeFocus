# gazefocus/app/state.py
Verified against: GazeFocus@948ff3a · 2026-09-30

`AppState.status` returns the highest-priority reason:
calibrating > locked > asleep > paused > unsupported layout > not calibrated > layout changed > tracker failed (3 crashes) > camera unavailable > running.

- `camera_wanted` is True in `RUNNING`, `CAMERA_WAIT` (retrying) and `CALIBRATING` (the calibration overlay samples the tracking camera, Plan 4). Pause, lock and sleep release it.
- `switching` is True only in `RUNNING`.
- Manual pause (Ctrl+Alt+G or the tray) is how the camera is handed to a video call; that's the user's choice from 2026-09-29.
