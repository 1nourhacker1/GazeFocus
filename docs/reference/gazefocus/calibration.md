# gazefocus/calibration.py
Verified against: GazeFocus@7fdf407 · 2026-09-29

`commit_calibration(model, counts, samples, *, monitors, dock_monitor, camera, force=False)` is the one path used by both `calibrate-cli` and the tray's Recalibrate:
- **"too close" (< 2σ)** returns `CommitResult(saved=False, "…The previous calibration was kept.")` unless `force`.
- Otherwise it copies the current file to `calibration.prev.json`, then writes `calibration.json` (v2) with the layout fingerprint and `zone_monitors` from `monitors` and `dock_monitor`.
- It also writes `calibration-samples.jsonl`: one `{"screen": "LG"|"LAPTOP", HeadSample…}` per line. `load_samples` reads it back for offline refits (Plan 1 deferred minor #9).
