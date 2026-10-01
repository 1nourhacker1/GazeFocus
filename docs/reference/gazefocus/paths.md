# gazefocus/paths.py
Verified against: GazeFocus@PENDING · 2026-10-01

- `repo_root()`: the repository root (computed from the file's location).
- `model_path()`: `<repo>/models/face_landmarker.task`, fetched by `scripts/fetch_model.py` (SHA-256 pinned).
- `app_dir()`: `%APPDATA%\GazeFocus`, created on demand. Overridden by `GAZEFOCUS_HOME` (every test sets this in `tests/conftest.py`).
- `bundle_dir()`: where the app's own files are: the repo, or inside a standalone build (PyInstaller sets `sys.frozen`) its bundle folder, `sys._MEIPASS`. `model_path()` is `bundle_dir()/models/face_landmarker.task`, so the standalone zip carries the model inside.
