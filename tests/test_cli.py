import pytest

from gazefocus.__main__ import main
from gazefocus.logic.classifier import ZoneModel
from gazefocus.logic.decider import Context
from gazefocus.replay import Recorder
from gazefocus.storage import Calibration, calibration_path, now_iso, save_calibration
from gazefocus.types import HeadSample, Zone
from gazefocus.vision.camera import CameraSource
from gazefocus.win import camera_usage
from gazefocus.win.camera_usage import CameraUser
from gazefocus.win.monitors import MonitorInfo

TOY = ZoneModel(w=(1 / 15, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 0, 0), mean_laptop=(0, 0, 0), sd=(10.0, 5.0, 0.1))


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    # argparse prints the sub-commands as "{probe,live,...}"; match names exactly
    # (a bare substring check passed "run" via watch's "dry run" help text)
    commands = set(out[out.index("{") + 1 : out.index("}")].split(","))
    for cmd in ("probe", "calibrate-cli", "watch", "bench", "replay", "live", "run", "diag", "dock-demo"):
        assert cmd in commands


def test_cli_camera_busy(monkeypatch, capsys):  # Review Focus #1
    monkeypatch.setattr(CameraSource, "open", lambda self: False)
    chrome = CameraUser(r"C:\Program Files\Google\Chrome\Application\chrome.exe", False)
    monkeypatch.setattr(camera_usage, "apps_using_camera", lambda entries=None, exclude=(): [chrome])
    assert main(["bench", "--minutes", "0.01"]) == 2
    assert "Possibly in use by: chrome.exe" in capsys.readouterr().err


def test_watch_without_calibration_exits_3(capsys):
    assert main(["watch", "--seconds", "0.1"]) == 3
    assert "calibrate-cli" in capsys.readouterr().err


def save_toy_calibration():
    lap = MonitorInfo(r"\\.\DISPLAY1", "id-lap", (0, 0, 2560, 1600), (0, 0, 2560, 1552), True)
    save_calibration(
        Calibration(now_iso(), "fp", (lap,), {"LAPTOP": "id-lap", "LG": None}, {"index": 0}, TOY, {"LG": 60, "LAPTOP": 60}),
        calibration_path(),
    )


def test_replay_command(tmp_path, capsys):
    save_toy_calibration()
    rec = tmp_path / "r.jsonl"
    with Recorder(rec) as r:
        for i in range(45):
            t = i / 15
            yaw = 0.0 if t < 1.0 else -30.0
            r.write(HeadSample(t, True, yaw=yaw), Context(t=t, focus_zone=Zone.LAPTOP))
    assert main(["replay", str(rec)]) == 0
    out = capsys.readouterr().out
    assert "SWITCH" in out and "45 frames, 1 switches" in out


def test_replay_missing_file_exits_1(tmp_path, capsys):
    save_toy_calibration()
    assert main(["replay", str(tmp_path / "missing.jsonl")]) == 1
    assert "replay failed" in capsys.readouterr().err


def test_live_camera_busy(monkeypatch, capsys):
    monkeypatch.setattr(CameraSource, "open", lambda self: False)
    monkeypatch.setattr(camera_usage, "apps_using_camera", lambda entries=None, exclude=(): [])
    assert main(["live"]) == 2
    assert "Could not open the camera" in capsys.readouterr().err


# --- final review (Minor #10, re-graded Important): a bad calibration must not replace a good one ---
from types import SimpleNamespace

import gazefocus.__main__ as cli

CLOSE = ZoneModel(w=(0.1, 0.0, 0.0), b=0.0, separation=1.2, mean_lg=(5, 8, 0), mean_laptop=(0, 8, 0), sd=(4.0, 4.0, 0.1))
GOOD = ZoneModel(w=(-0.07, 0.0, 0.0), b=0.9, separation=12.0, mean_lg=(28, 3, 0.2), mean_laptop=(-1, 9, 0), sd=(2.0, 1.0, 0.1))


def fake_calibration_run(monkeypatch, model):
    cam = SimpleNamespace(backend="MSMF", read=lambda: None, release=lambda: None)
    monkeypatch.setattr(cli, "_open_camera", lambda cfg: cam)
    monkeypatch.setattr(cli, "_tracker", lambda: SimpleNamespace(process=None, close=lambda: None))
    monkeypatch.setattr("gazefocus.runtime.calibrate", lambda *a, **k: (model, {"LG": 60, "LAPTOP": 60}))


def test_too_close_calibration_keeps_the_previous_one(monkeypatch, capsys):
    save_toy_calibration()
    before = calibration_path().read_text(encoding="utf-8")
    fake_calibration_run(monkeypatch, CLOSE)
    assert main(["calibrate-cli"]) == 3
    assert calibration_path().read_text(encoding="utf-8") == before
    err = capsys.readouterr().err
    assert "too close" in err and "--force" in err


def test_force_saves_and_backs_up_the_previous(monkeypatch):
    save_toy_calibration()
    before = calibration_path().read_text(encoding="utf-8")
    fake_calibration_run(monkeypatch, CLOSE)
    assert main(["calibrate-cli", "--force"]) == 0
    assert calibration_path().with_name("calibration.prev.json").read_text(encoding="utf-8") == before
    assert '"separation": 1.2' in calibration_path().read_text(encoding="utf-8")


def test_good_calibration_is_saved(monkeypatch):
    fake_calibration_run(monkeypatch, GOOD)
    assert main(["calibrate-cli"]) == 0
    assert '"separation": 12.0' in calibration_path().read_text(encoding="utf-8")


# --- Plan 2: diag ---
import io
import sys

from gazefocus.win import windows as win_windows
from gazefocus.win.windows import WindowFacts


def test_diag_monitors_prints_the_layout(capsys):
    assert main(["diag", "monitors"]) == 0
    out = capsys.readouterr().out
    assert "fingerprint" in out and "DISPLAY" in out


def test_diag_windows_survives_unicode_titles_on_a_cp1252_console(monkeypatch):  # Review Focus #5
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setattr(win_windows, "top_level_windows", lambda: [77])
    monkeypatch.setattr(win_windows, "window_facts", lambda h, own_pid=None: WindowFacts(
        77, True, visible=True, class_name="CASCADIA_HOSTING_WINDOW_CLASS", title="◐ Eye tracking", device=r"\\.\DISPLAY1"))
    assert main(["diag", "windows"]) == 0
    sys.stdout.flush()
    assert b"Eye tracking" in raw.getvalue()


def test_diag_focus_with_no_window_on_that_screen(monkeypatch, capsys):
    monkeypatch.setattr(win_windows, "choose_target", lambda *a, **k: None)
    assert main(["diag", "focus", "LG", "--delay", "0"]) == 1
    assert "no window" in capsys.readouterr().out


def test_run_refuses_a_second_instance(capsys):
    from gazefocus.app.main import instance_name
    from gazefocus.win.system import SingleInstance

    holder = SingleInstance(instance_name())
    try:
        assert main(["run", "--seconds", "0.1"]) == 4
    finally:
        holder.close()
    assert "already running" in capsys.readouterr().err


def test_a_windowless_launcher_starts_the_app(monkeypatch):
    """`gazefocus-app.exe` (a uv gui-script: no console window) runs the background app."""
    import importlib
    import pathlib
    import tomllib

    scripts = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["gui-scripts"]
    module, func = scripts["gazefocus-app"].split(":")
    entry = getattr(importlib.import_module(module), func)
    calls = []
    monkeypatch.setattr("gazefocus.app.main.run_app", lambda **kw: calls.append(kw) or 0)
    assert entry() == 0 and calls == [{}]


def test_without_a_console_the_log_does_not_go_to_stderr(monkeypatch, tmp_path):
    import logging

    from gazefocus.app.main import log_to_stderr

    monkeypatch.setattr("sys.stderr", None)  # what pythonw gives a windowless app
    assert log_to_stderr() is False
