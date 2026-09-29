# gazefocus/paths.py
Verified against: GazeFocus@42223e4 · 2026-09-29

- `repo_root()`: the repository root (computed from the file's location).
- `model_path()`: `<repo>/models/face_landmarker.task`, fetched by `scripts/fetch_model.py` (SHA-256 pinned).
- `app_dir()`: `%APPDATA%\GazeFocus`, created on demand. Overridden by `GAZEFOCUS_HOME` (every test sets this in `tests/conftest.py`).
