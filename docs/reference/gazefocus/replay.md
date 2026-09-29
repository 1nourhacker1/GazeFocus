# gazefocus/replay.py
Verified against: GazeFocus@bf7feda · 2026-09-29

- **Recording format** (JSONL, one frame per line, **no video**): `{"sample": HeadSample fields, "ctx": Context fields}`, with `focus_zone` stored as a string.
- `replay(frames, model, cfg)` runs a fresh `ZoneClassifier` and `GazeDecider`.
  - Every `switch` is assumed to succeed and moves the *simulated* focus.
  - The simulated focus follows the recording only on the first frame and whenever `last_manual_focus_t` changes (a real click or Alt+Tab). Focus changes the *recording's* model made itself are ignored, so a recording can be replayed honestly through a different model (final-review fix).
- `summarize` prints one line per switch and one line per run of the same blocked category (numbers are ignored, so a typing run prints once).
- Used by `gazefocus replay FILE` (Task 12) to tune thresholds against real behaviour without sitting at the desk.
- Uses `logic.decider.reason_category` for collapsing runs.
