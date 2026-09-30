# gazefocus/app/main.py
Verified against: GazeFocus@c85c304 · 2026-09-30

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
- `Tray`: status, Pause, Recalibrate, config, logs, Quit.

**Recalibrate** (a `CalibrationJob` with beeps, then `commit_calibration`, then `refresh_layout`) has three guards, all final-review fixes:
- It's refused unless exactly 2 monitors are present (a tray notification). Otherwise a one-monitor file would replace the good one.
- It records the layout fingerprint at the start. If the layout differs at the end, the result isn't saved and the previous calibration is kept.
- Pause, lock and sleep (`_set(flag, True)`) cancel a running job, which releases the camera; you get "Calibration cancelled" and nothing is saved.

**`refresh_layout()`:**
- Exactly 2 monitors are required, otherwise "unsupported".
- The calibration must match the layout fingerprint, otherwise "missing" or "layout changed".
- Both zones must map to present devices.
- A fresh `Controller` is then built.

**`apply()`:** the camera runs iff `state.camera_wanted` and no retry or restart timer is pending. If a stopped run still holds the camera, `worker.start()` is refused and the next `tick` retries.

**`close()`:** cancels any calibration job, then stops the camera, waiting up to 3 s.

**`tick()` (1 Hz):**
- polls the config (a live reload rebuilds the controller and re-registers the hotkey)
- sets fps: `camera.fps`; `idle_fps` after `idle_after_s` without input; at most `battery_fps` on battery
- retries the camera every 5 s after a failure
- restarts after a crash after 2 s; after 3 crashes it gives up with a tray notification
- resets the failure count after 60 s healthy

**Camera for calls:** manual only, by pausing (the user's decision, 2026-09-29).

**The dock (Plan 3):**
- `make_dock` builds a `DockWindow`, unless `dock.enabled` is false.
- `qt_work_area` finds the Qt screen by origin: Qt names screens "LG FHD", not `\\.\DISPLAY5`.
- `_update_dock` runs for every sample, on `apply()` and on foreground changes. "No face" shows after 0.5 s.
- `_dock_visibility` runs on `apply()` (1 Hz) and on foreground changes: the dock hides while locked, asleep, or under a fullscreen app.
- `_on_panel` sets the camera preview to 10 fps while the panel is open.
- A change to any dock setting rebuilds the dock.
