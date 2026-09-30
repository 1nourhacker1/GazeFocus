# gazefocus/app/workers.py
Verified against: GazeFocus@beaa5d8 · 2026-09-30

Plain Python threads, with results delivered through a `QObject` bridge created on the main thread. Qt queues cross-thread signal emissions, so **every callback runs on the Qt main thread** (asserted in the tests).

- **`CameraWorker`**: open the camera, create the tracker, then loop `read → process → emit sample`, paced to `.fps`. `.fps` can change live: the idle rate is 5, the battery cap 10.
  - An open failure gives `on_failed("could not open the camera")`. 30 missed frames in a row gives `on_failed("the camera stopped delivering frames")`.
  - Any exception gives `on_crashed("Type: msg")`. The camera and tracker are always released.
  - **Each run has its own stop event** (final-review fix). A shared event let `start()` revive a run whose stop had timed out during a slow open, so a camera thread could be left that nothing could stop.
  - `stop(timeout=0.5)` asks the run to end and joins for at most `timeout`, so the Qt thread never freezes. An open still in progress can take seconds. When it returns, the stopped run releases the camera at once and reports nothing.
  - `alive`: the thread still exists, either running or stopped but not yet done with the camera. `running`: alive and not asked to stop.
  - `start()` returns False while `alive`. The app's 1 Hz `tick` simply tries again.
- **`CalibrationJob`**: runs `runtime.calibrate` with cues and `samples_out` on its own camera session. It reports a `CalibrationOutcome`: a model, or an error.
  - **Keep a reference until `on_done` fires.** If the job is garbage-collected, its bridge goes with it and the queued result is dropped (seen while planning).
  - **`cancel(timeout=0.5)`** (final-review fix): the frame read, the pacing sleep and the cue each raise `CalibrationCancelled` once it's set. That releases the camera within a frame and skips any further beeps.
    - The result is `CalibrationOutcome(cancelled=True)`.
    - A cue already playing finishes first, which takes about 450 ms per beep.
- **Preview tap:** while `preview_fps > 0` (the app sets 10 while the dock's panel is open), the worker also emits `on_preview(frame, sample)`, a 160 × 120 copy, at most `preview_fps` times a second.
