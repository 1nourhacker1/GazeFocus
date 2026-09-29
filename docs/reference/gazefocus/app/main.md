# gazefocus/app/main.py
Verified against: GazeFocus@a0e7f5a · 2026-09-29

`run_app()`:
1. DPI awareness.
2. The single-instance mutex; exits **4** if one is already running.
3. The model check; exits **5** if it's missing.
4. config.toml (defaults written if missing) and logs.
5. `QApplication` (it doesn't quit when a window closes).
6. `GazeFocusApp`.
7. A 1 Hz `tick`, and a 200 ms wake timer so Ctrl+C works.
8. `qapp.exec()`, then `close()` on the way out.

`GazeFocusApp` wires, on the Qt main thread:
- `MessageWindow` carrying `InputWatcher` (Raw Input), `Hotkey` (Ctrl+Alt+G → `toggle_pause`) and `SystemEvents` (lock, unlock, suspend, resume, display change → re-layout after 1.5 s).
- `ForegroundHook` → `MruTracker` (targets only in the lists; everything else counts as manual).
- `CameraWorker` → `_on_sample` → `Controller.on_sample`, only while `state.switching`.
- `Tray`: status, Pause, Recalibrate (a `CalibrationJob` with beeps, then `commit_calibration`, then `refresh_layout`), config, logs, Quit.

**`refresh_layout()`:**
- Exactly 2 monitors are required, otherwise "unsupported".
- The calibration must match the layout fingerprint, otherwise "missing" or "layout changed".
- Both zones must map to present devices.
- A fresh `Controller` is then built.

**`apply()`:** the camera runs iff `state.camera_wanted` and no retry or restart timer is pending.

**`tick()` (1 Hz):**
- polls the config (a live reload rebuilds the controller and re-registers the hotkey)
- sets fps: `camera.fps`; `idle_fps` after `idle_after_s` without input; at most `battery_fps` on battery
- retries the camera every 5 s after a failure
- restarts after a crash after 2 s; after 3 crashes it gives up with a tray notification
- resets the failure count after 60 s healthy

**Camera for calls:** manual only, by pausing (the user's decision, 2026-09-29).
