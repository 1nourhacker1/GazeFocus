"""Filesystem locations. GAZEFOCUS_HOME overrides %APPDATA%\\GazeFocus (used by tests)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    # src/gazefocus/paths.py -> parents[0]=gazefocus, [1]=src, [2]=repo root
    return Path(__file__).resolve().parents[2]


def model_path() -> Path:
    return repo_root() / "models" / "face_landmarker.task"


def app_dir() -> Path:
    override = os.environ.get("GAZEFOCUS_HOME")
    base = Path(override) if override else Path(os.environ["APPDATA"]) / "GazeFocus"
    base.mkdir(parents=True, exist_ok=True)
    return base
