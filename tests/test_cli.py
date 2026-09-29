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

TOY = ZoneModel(w=(1 / 15, 0.0, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 0, 0, 0), mean_laptop=(0, 0, 0, 0))


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ("probe", "calibrate-cli", "watch", "bench", "replay", "live"):
        assert cmd in out


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
