# gazefocus/app/workers.py
Verified against: GazeFocus@cce457d · 2026-09-29

Plain Python threads, with results delivered through a `QObject` bridge created on the main thread. Qt queues cross-thread signal emissions, so **every callback runs on the Qt main thread** (asserted in the tests).

- **`CameraWorker`**: open the camera, create the tracker, then loop `read → process → emit sample`, paced to `.fps`. `.fps` can change live: the idle rate is 5, the battery cap 10.
  - An open failure gives `on_failed("could not open the camera")`. 30 missed frames in a row gives `on_failed("the camera stopped delivering frames")`.
  - Any exception gives `on_crashed("Type: msg")`. The camera and tracker are always released.
- **`CalibrationJob`**: runs `runtime.calibrate` with cues and `samples_out` on its own camera session. It reports a `CalibrationOutcome`: a model, or an error.
  - **Keep a reference until `on_done` fires.** If the job is garbage-collected, its bridge goes with it and the queued result is dropped (seen while planning).
