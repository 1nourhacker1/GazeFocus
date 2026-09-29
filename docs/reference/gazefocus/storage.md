# gazefocus/storage.py
Verified against: GazeFocus@3cc6d6e · 2026-09-29

The file is `%APPDATA%\GazeFocus\calibration.json` (`calibration_path()`).
It's written atomically (`.tmp`, then rename). The format is version 1:
`version`, `created`, `layout{fingerprint, monitors[]}`, `zone_monitors`, `camera`, `model{w,b,separation,mean_lg,mean_laptop}`, `samples`.

- `load_calibration` **never raises on bad content**. Missing file gives `(None, None)`. Unreadable JSON, missing keys, a wrong version, or non-finite weights give `(None, "<reason>; please recalibrate")`.
- `load_if_matches(path, fingerprint)` also refuses a calibration taken under a different monitor layout.
- Deviation from spec §10: per-screen covariance matrices are not stored, because nothing uses them.
