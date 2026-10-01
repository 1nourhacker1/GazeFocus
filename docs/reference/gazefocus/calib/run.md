# gazefocus/calib/run.py
Verified against: GazeFocus@b887938 · 2026-10-01

`CalibrationRun`: one follow-the-drop run on screen (spec §9). It joins the pure session (`calib/session.py`), its overlay windows (`calib/overlay.py`) and the beeps, paced by the display's refresh. The app (`app/main.py`) owns the camera and feeds `on_sample`.

- **`CalibrationRun(screens, dock, on_done, cue, on_open, overlay, ticker, clock, native, refraction)`:**
  - `screens`: {"external monitor": rect, "LAPTOP": rect}, logical. `dock`: the point the drop leaves from.
  - `overlay` and `ticker` default to `Overlay(screens)` and a `VBlankTicker`. Tests pass fakes and a manual clock.
- **`start()`:** starts the session at `clock()`, opens the overlay, calls `on_open()` (the app lifts the dock back above the overlay), and starts the ticker.
- **Each tick:**
  1. `session.frame(now)`, then `overlay.show(frame, now)`.
  2. When the phase changes to one in `CUES`: `cue("EXTERNAL")`, `cue("LAPTOP")`, `cue("DONE")`. The app plays each on a helper thread.
  3. At `done`: `session.result()`, then the ticker stops and closes, the overlay hides, and `on_done(result)` is called exactly once.
- **A frame that raises** (the overlay, a GDI grab) ends the run: the overlay is hidden (a failing hide is only logged) and `on_done` gets a "Calibration failed" result with the error. Both screens never stay dimmed (final-review fix).
- **`on_sample(sample)`** reaches the session only while `active`.
- **`cancel()`:** the session is cancelled, the ticker stopped and closed, and the overlay hidden. `on_done` is never called. A tick already queued does nothing. Calling it twice is harmless.
- `external_name` is passed on to the session.
