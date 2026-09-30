# gazefocus/calib/session.py
Verified against: GazeFocus@362439b · 2026-09-30

One run of the "follow the drop" calibration (spec §9). Pure: time comes in, frames come out.
The app feeds it the tracking camera's samples (`on_sample`) and asks for a frame on every vsync (`frame(now)`); the overlay (`calib/overlay.py`) draws the frame. Both clocks are `time.perf_counter`, like `HeadSample.t`.

- **`CalibrationSession(lg, laptop, dock)`:** screens as logical (x, y, w, h) rects, and the dock point the drop leaves from and returns to.
  - `start(now)` begins, or restarts for **Redo**: samples cleared, back to `start`.
  - `phase`: one of `PHASES`' names, then `done`, or `cancelled` after `cancel()`.
  - `tau` is timeline time: wall time minus the time the tours stood waiting. `last_now` is the last frame's time.
- **`PHASES`** (the mockup's timeline, seconds): `start` .42 → `lg_travel` 1.1 → `lg_card` 1.3 → `lg_tour` 5.2 → `lap_travel` 1.1 → `lap_card` 1.2 → `lap_tour` 5.2 → `return` .7 → `outro` .6 → `done`. About 17 s with a face in view.
- **`frame(now) -> OverlayFrame`:**
  - `dims`: black-overlay opacity per screen. `lg_*`: LG .25, laptop .62. `lap_*` and `return`: the reverse. Otherwise 0.
  - `drop: DropState(x, y, opacity, along, across, angle)`:
    - The path is `travel` (dock → LG centre → laptop centre → dock) and the eased Catmull-Rom tours (`calib/path.py`).
    - It fades in over 0.25 s at `lg_travel` and out at `outro`.
    - The stretch is measured over one 60 Hz frame of the timeline, so it doesn't depend on the frame rate. A waiting drop doesn't stretch.
  - `ring`: the tour's progress (0..1) during tours, else None.
  - `card`:
    - `lg_card`: "Look at this screen" / "Follow the drop with your eyes" on the LG.
    - `lap_card`: "Now this screen" / "Follow the drop" on the laptop.
    - During a tour, after `LOST_CARD_S` (0.3 s) without a face: "Can't see you" / "Is the room too dark?" on that screen.
  - `waiting`: a tour stands still.
- **Waiting for the face:**
  - A tour's clock stops while the latest sample has no face, or no sample has arrived for `STALE_S` (1 s: a camera that stopped).
  - Before the first sample, there's no face yet, so the camera may take its time to open.
  - After `GIVE_UP_S` (20 s) of waiting, the run ends (`done`), and the result is "Couldn't see you" / "No face for 20 s. Is the room too dark, or is another app using the camera?" (final-review fix: a busy camera meant an endless wait).
- **Sampling:** only face samples, only during tours, only after the tour's first `SETTLE_S` (0.4 s of timeline). That's about 72 per screen at 15 fps.
- **`CUES`:** the beeps the app plays when a phase begins. `lg_travel` → LG (1), `lap_travel` → LAPTOP (2), `done` → DONE (3).
- **`result() -> CalibrationResult(model, samples, counts, quality, title, message)`:**
  - Fewer than `MIN_CAL_SAMPLES` (40) on either screen: "Too few samples", no model.
  - `fit_zone_model` fails, or the quality is "too close": the title "Too close" and the message "Turn your head a little more, or move the LG closer to the laptop." (the panel shows them apart; together they read as the plan's sentence).
  - Otherwise "Calibrated ✓", with the hint "Look at each screen: the water should follow."
  - `can_save` is true only for a model that isn't too close.
- The laptop leg travels to the laptop's centre, where its tour begins; the mockup's (.5, .55) would make the drop jump 53 px at the tour's start (Plan 4 ruling).
