# gazefocus/app/main.py
Verified against: GazeFocus@b887938 · 2026-10-01

`run_app()`:
1. DPI awareness.
2. The single-instance mutex; exits **4** if one is already running.
3. The model check; exits **5** if it's missing.
4. config.toml (defaults written if missing) and logs.
5. `QApplication` (it doesn't quit when a window closes).
6. `GazeFocusApp`.
7. A 1 Hz `tick`, and a 200 ms wake timer so Ctrl+C works.
8. `qapp.exec()`, then `close()` on the way out.

**`gui_main()`** is `gazefocus-app.exe` (a `[project.gui-scripts]` entry, run by pythonw with no console): it calls `run_app()`. Without a console, `log_to_stderr()` is False, so the log goes only to the files.

`GazeFocusApp` wires, on the Qt main thread:
- `MessageWindow` carrying `InputWatcher` (Raw Input; its `InputTracker` reports each real key-down to `_on_key`, which hears calibration's Esc), `Hotkey` (Ctrl+Alt+G → `toggle_pause`) and `SystemEvents` (lock, unlock, suspend, resume, display change → re-layout after 1.5 s).
- `ForegroundHook` → `MruTracker` (targets only in the lists; everything else counts as manual).
- `CameraWorker` → `_on_sample` → `Controller.on_sample`, only while `state.switching`. During a calibration run the samples go to the run instead; while the result panel is up, to a `ZoneClassifier` on the new model (the preview below).
- `Tray`: status, Pause, Recalibrate, config, logs, Quit.

**Recalibrate** (Plan 4, spec §9):
- **Triggers:** the tray, the hover panel's Recalibrate, a click on the collapsed dock while it shows "!" for not calibrated or layout changed (`_on_pill`; otherwise a pill click pauses), and the **first start** without a calibration (`first_run`).
- **The flow:** every trigger opens the dock's **intro** (`show_intro`); tracking goes on meanwhile.
  - **Start** (`_start_run`): the fingerprint is recorded, `state.calibrating` is set, and a `calib.run.CalibrationRun` (`run_factory`) starts. It gets the two screens (`qt_screen_rect`, logical, matched by origin; external monitor and laptop by `zone_monitors`) and the dock's `pill_centre()`.
  - The **tracking camera** stays on (or starts) at the full `camera.fps`, and the run samples it. The dock is lifted back above the overlay (`raise_to_top`).
  - Beeps play on a helper thread (`_cue`), because `winsound.Beep` blocks.
  - **Done** (`_run_done`): the dock shows the **result** panel. A saveable result also gets a live **preview**: a `ZoneClassifier` on the new model moves the dock's water, but nothing switches.
  - **Save:** `commit_calibration` with the worker's camera `backend`, then `refresh_layout`. **Redo:** a new run, without the intro.
  - Without a dock, the run starts at once, and a saveable result is saved directly.
- **Every exit ends it** (final-review fixes):
  - A Redo that finds a monitor gone ends the calibration, rather than staying in CALIBRATING.
  - A rebuilt dock (config reload) shows the same intro or result, and Recalibrate re-shows a lost one.
  - A result left alone for `RESULT_TIMEOUT_S` (60 s), or pause, lock or sleep while it's up (`_settle_result`), is **saved** if it can be; otherwise it's dropped. Esc still discards it.
  - A camera failure mid-run cancels the run with a notification. The tracker's 3rd crash cancels it too, so there's no restart loop while calibrating.
- **Guards and cancels** (`cancel_calibration`; the previous calibration always stays):
  - Refused unless exactly 2 monitors are present and both screens are found (a tray notification).
  - **Esc** (only listening: the focused app gets it too), **Not now**, and pause, lock or sleep (`_set(flag, True)`).
  - A **layout change** mid-run, or while the result shows, cancels it with a notification (`_relayout`). A change detected only at Save means nothing is saved.

**`refresh_layout()`:**
- Exactly 2 monitors are required, otherwise "unsupported".
- The calibration must match the layout fingerprint, otherwise "missing" or "layout changed".
- Both zones must map to present devices.
- A fresh `Controller` is then built.

**`apply()`:** the camera runs iff `state.camera_wanted` (running, retrying, or calibrating) and no retry or restart timer is pending. If a stopped run still holds the camera, `worker.start()` is refused and the next `tick` retries.

**`close()`:** ends any calibration (the overlay closes), then stops the camera, waiting up to 3 s.

**`tick()` (1 Hz):**
- polls the config (a live reload rebuilds the controller and re-registers the hotkey)
- sets fps: `camera.fps`; `idle_fps` after `idle_after_s` without input; at most `battery_fps` on battery; always `camera.fps` while calibrating
- retries the camera every 5 s after a failure
- restarts after a crash after 2 s; after 3 crashes it gives up with a tray notification
- resets the failure count after 60 s healthy

**Camera for calls:** manual only, by pausing (the user's decision, 2026-09-29).

**The dock (Plan 3):**
- `make_dock` builds a `DockWindow`, unless `dock.enabled` is false.
- `qt_work_area` finds the Qt screen by origin: Qt names screens "LG FHD", not `\\.\DISPLAY5`.
- `_update_dock` runs for every sample, on `apply()` and on foreground changes. "No face" shows after 0.5 s without one, counted from the first frame after a camera start if no face has been seen since.
- `_dock_visibility` runs on `apply()` (1 Hz) and on foreground changes: the dock hides while locked, asleep, or under a fullscreen app.
- `_on_panel` sets the camera preview to 10 fps while the panel is open. A rebuilt dock starts with it off (its panel is closed).
- A change to any dock setting rebuilds the dock; a `typing_freeze_ms` change alone is pushed with `set_freeze`.
- **Screen names:** `_name_screens` (in `refresh_layout`) asks `screen_name` (`qt_screen_name`: Qt's screen name, matched by origin) for the external monitor's own name. `display_name` drops empty or "Generic PnP Monitor" names. The result, or "External", goes into `names`, which reaches the dock, the tray, the calibration run (`external_name`) and the result panel.
