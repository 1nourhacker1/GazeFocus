"""Build the standalone download: dist/GazeFocus-<version>-windows-x64.zip (no Python or uv needed to run it).

    uv run --with pyinstaller==6.22.3 python scripts/build_standalone.py

It bundles the app, Python, Qt, MediaPipe, OpenCV and the face model with PyInstaller (one folder, windowless
GazeFocus.exe), runs the build's self-test (no window, no camera), and zips the folder.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD, DIST = ROOT / "build", ROOT / "dist"
MODEL = ROOT / "models" / "face_landmarker.task"


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def make_icon(path: Path) -> None:
    """The tray's two-tile icon at the sizes Windows uses."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtWidgets import QApplication

    from gazefocus.app.state import Status
    from gazefocus.app.tray import status_icon
    from gazefocus.types import Zone

    QApplication.instance() or QApplication([])
    image = status_icon(Status.RUNNING, Zone.LAPTOP, size=256).pixmap(256, 256).toImage()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), "ICO"):
        raise RuntimeError(f"could not write {path}")


def pyinstaller(icon: Path) -> Path:
    entry = BUILD / "entry.py"
    entry.write_text("from gazefocus.app.main import gui_main\n\nraise SystemExit(gui_main())\n", encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "GazeFocus", "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        "--paths", str(ROOT / "src"),
        "--add-data", f"{MODEL}{os.pathsep}models",
        "--collect-all", "mediapipe",  # its C library is loaded by path, which PyInstaller can't see
        "--exclude-module", "tkinter",
        str(entry),
    ], check=True)
    return DIST / "GazeFocus"


def selftest(app: Path) -> None:
    report = BUILD / "selftest.txt"
    report.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}  # the real Windows platform, not offscreen
    code = subprocess.run([str(app / "GazeFocus.exe"), "--selftest", str(report)], env=env, timeout=300).returncode
    text = report.read_text(encoding="utf-8") if report.exists() else "(no report)"
    print(text)
    if code != 0 or "RESULT: ok" not in text or "platform windows" not in text:
        raise SystemExit(f"the build's self-test failed (exit {code})")


def main() -> int:
    if not MODEL.is_file():
        raise SystemExit("the face model is missing: run  uv run python scripts/fetch_model.py")
    icon = BUILD / "gazefocus.ico"
    make_icon(icon)
    app = pyinstaller(icon)
    selftest(app)
    zip_base = DIST / f"GazeFocus-{version()}-windows-x64"
    archive = shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir="GazeFocus")
    size = Path(archive).stat().st_size / 1e6
    print(f"built {archive} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
