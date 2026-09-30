# gazefocus/app/workers.py
Verified against: GazeFocus@948ff3a · 2026-09-30

A plain Python thread, with results delivered through a `QObject` bridge created on the main thread. Qt queues cross-thread signal emissions, so **every callback runs on the Qt main thread** (asserted in the tests).

- **`CameraWorker`**: open the camera, create the tracker, then loop `read → process → emit sample`, paced to `.fps`. `.fps` can change live: the idle rate is 5, the battery cap 10.
  - An open failure gives `on_failed("could not open the camera")`. 30 missed frames in a row gives `on_failed("the camera stopped delivering frames")`.
  - Any exception gives `on_crashed("Type: msg")`. The camera and tracker are always released.
  - **Each run has its own stop event** (final-review fix). A shared event let `start()` revive a run whose stop had timed out during a slow open, so a camera thread could be left that nothing could stop.
  - `stop(timeout=0.5)` asks the run to end and joins for at most `timeout`, so the Qt thread never freezes. An open still in progress can take seconds. When it returns, the stopped run releases the camera at once and reports nothing.
  - `alive`: the thread still exists, either running or stopped but not yet done with the camera. `running`: alive and not asked to stop.
  - `start()` returns False while `alive`. The app's 1 Hz `tick` simply tries again.
  - `backend`: the last opened camera's backend. It's saved with a calibration made from this worker's samples.
- There's no calibration thread any more (Plan 4): the in-app calibration samples this worker. `calibrate-cli` still uses `runtime.calibrate` with its own camera.
- **Preview tap:** while `preview_fps > 0` (the app sets 10 while the dock's panel is open), the worker also emits `on_preview(frame, sample)`, a 160 × 120 copy, at most `preview_fps` times a second.
