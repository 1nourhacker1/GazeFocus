# gazefocus/replay.py
Verified against: GazeFocus@660fa19 · 2026-09-29

- **Recording format** (JSONL, one frame per line, **no video**): `{"sample": HeadSample fields, "ctx": Context fields}`, with `focus_zone` stored as a string.
- `replay(frames, model, cfg)` runs a fresh `ZoneClassifier` and `GazeDecider`.
  - Every `switch` is assumed to succeed and moves the *simulated* focus.
  - When the recorded `focus_zone` changes (a real click or Alt+Tab), the simulated focus follows the recording.
- `summarize` prints one line per switch and one line per run of the same blocked category (numbers are ignored, so a typing run prints once).
- Used by `gazefocus replay FILE` (Task 12) to tune thresholds against real behaviour without sitting at the desk.
