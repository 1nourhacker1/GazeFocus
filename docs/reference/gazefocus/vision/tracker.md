# gazefocus/vision/tracker.py
Verified against: GazeFocus@beaa5d8 · 2026-09-30

- `HeadTracker(model_path)` runs MediaPipe `FaceLandmarker` in **VIDEO** mode:
  1 face, confidence thresholds 0.5, blendshapes off, facial transformation matrices on.
  It runs on the CPU through XNNPACK.
- `detect(bgr, t)`: BGR→RGB, `mp.Image(SRGB)`, then `detect_for_video(image, ms)`, returning the **raw** result (landmarks + matrices), used by the live view.
- `process(bgr, t)`: `detect()` → `HeadSample` via `sample_from_result`.
- `next_timestamp_ms` keeps timestamps strictly increasing, because VIDEO mode rejects repeats or decreases.
- M0-A results: yaw **positive** toward the LG, face tracked 100 % up to +62°, 6–7 ms per frame. See `docs/spikes/m0a-tracking.md`.
- A missing model raises `FileNotFoundError` naming `scripts/fetch_model.py`.
- `sample_from_result` also fills `box` (the landmarks' bounds) and `nose` (landmark 1).
