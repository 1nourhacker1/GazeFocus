# gazefocus/storage.py
Verified against: GazeFocus@b887938 · 2026-10-01

The file is `%APPDATA%\GazeFocus\calibration.json` (`calibration_path()`).
It's written atomically (`.tmp`, then rename). The format is **version 2** (3 features plus per-feature `sd`; version 1 files are refused with "please recalibrate"):
`version`, `created`, `layout{fingerprint, monitors[]}`, `zone_monitors`, `camera`, `model{w,b,separation,mean_external,mean_laptop,sd}`, `samples`.

- `load_calibration` **never raises on bad content**. Missing file gives `(None, None)`. Unreadable JSON, missing keys, a wrong version, non-finite, wrong-sized or non-positive-sd weights give `(None, "<reason>; please recalibrate")`.
- `load_if_matches(path, fingerprint)` also refuses a calibration taken under a different monitor layout.
- Deviation from spec §10: per-screen covariance matrices are not stored, because nothing uses them.
- **Files from before the rename load:** `_upgrade_names` turns "LG" keys in `zone_monitors` and `samples` into "EXTERNAL", and the model's `mean_lg` into `mean_external`. The next save writes the new names.
