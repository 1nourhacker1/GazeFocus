"""Filesystem locations. GAZEFOCUS_HOME overrides %APPDATA%\\GazeFocus (used by tests)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    # src/gazefocus/paths.py -> parents[0]=gazefocus, [1]=src, [2]=repo root
    return Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    """Where the app's own files are: the repo, or inside a standalone (PyInstaller) build its bundle folder."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return repo_root()


def model_path() -> Path:
    return bundle_dir() / "models" / "face_landmarker.task"


def app_dir() -> Path:
    override = os.environ.get("GAZEFOCUS_HOME")
    base = Path(override) if override else Path(os.environ["APPDATA"]) / "GazeFocus"
    base.mkdir(parents=True, exist_ok=True)
    return base
