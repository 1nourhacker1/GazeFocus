# gazefocus/runtime.py
Verified against: GazeFocus@90c2edd · 2026-09-29

Camera-driven loops used by the CLI. Every loop takes `read_frame`, `track`, `clock`, `sleep` and `say`, so the tests run on a fake clock. The default clock is `time.perf_counter` (`time.monotonic` ticks every 15.6 ms on Windows).

- `Pacer(fps)` sleeps to the next frame slot. If it falls behind it drops the missed slots instead of catching up.
- `collect_phase` discards the first `settle_s` (**1.0 s**; the desk session showed a head turn between screens takes about 1 s) and returns the samples.
- `calibrate`:
  1. Runs the prompts `LG` then `LAPTOP`, 6 s each, with a 2 s lead-in.
  2. Requires **at least 40 face samples** per screen, otherwise `ValueError` ("too few face samples… too dark?").
  3. Fits the model, prints the separation and its quality, and returns `(model, counts)`.
- `cue(name)` fires with `"LG"`, `"LAPTOP"` and `"DONE"` as each phase is announced. The CLI turns these into beeps (1, 2, 3), because typed cues arrived too late during the desk session.
- `watch_loop` is a **dry run**. Focus is simulated: it starts on LAPTOP and moves on each `switch`. There's no keyboard or mouse input yet (Plan 2). It prints a status line (with `margin_bar`) whenever the gaze zone changes, or on a switch or block.
- `bench_loop` prints a `BenchReport.line()` every `report_every` seconds and returns the whole-run report.
  - CPU % is process CPU time ÷ wall time ÷ cores; RSS comes from psutil.
  - `verdict()` checks the spec targets: **CPU ≤ 2 %** and **RSS ≤ 300 MB**.
