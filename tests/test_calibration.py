import json

from gazefocus.calibration import SAMPLES_FILE, commit_calibration, load_samples, save_samples
from gazefocus.logic.classifier import ZoneModel
from gazefocus.storage import load_calibration
from gazefocus.types import HeadSample
from gazefocus.win.monitors import MonitorInfo

LAP = MonitorInfo(r"\\.\DISPLAY1", "id-lap", (0, 0, 2560, 1600), (0, 0, 2560, 1552), True)
EXTERNAL = MonitorInfo(r"\\.\DISPLAY5", "id-ext", (-1920, -302, 0, 778), (-1920, -302, 0, 738), False)
GOOD = ZoneModel(w=(-0.07, 0.0, 0.0), b=0.9, separation=12.0, mean_external=(28, 3, 0.2), mean_laptop=(-1, 9, 0), sd=(2.0, 1.0, 0.1))
CLOSE = ZoneModel(w=(0.1, 0.0, 0.0), b=0.0, separation=1.2, mean_external=(5, 8, 0), mean_laptop=(0, 8, 0), sd=(4.0, 4.0, 0.1))
SAMPLES = {"EXTERNAL": [HeadSample(0.1, True, 28.0, 3.0, 0.2)], "LAPTOP": [HeadSample(0.2, True, -1.0, 9.0, 0.0), HeadSample(0.3, False)]}


def commit(model, path, force=False, samples=SAMPLES):
    return commit_calibration(
        model, {"EXTERNAL": 1, "LAPTOP": 1}, samples, monitors=[LAP, EXTERNAL], dock_monitor="primary",
        camera={"index": 0}, force=force, path=path,
    )


def test_good_calibration_is_saved_with_zones_and_samples(tmp_path):
    p = tmp_path / "calibration.json"
    r = commit(GOOD, p)
    assert r.saved and "12.0 sigma" in r.message and "excellent" in r.message
    cal, warn = load_calibration(p)
    assert warn is None and cal.zone_monitors == {"LAPTOP": "id-lap", "EXTERNAL": "id-ext"}
    assert len((tmp_path / SAMPLES_FILE).read_text(encoding="utf-8").splitlines()) == 3


def test_too_close_keeps_the_previous_calibration(tmp_path):
    p = tmp_path / "calibration.json"
    commit(GOOD, p)
    before = p.read_text(encoding="utf-8")
    r = commit(CLOSE, p)
    assert not r.saved and "too close" in r.message and "kept" in r.message
    assert p.read_text(encoding="utf-8") == before


def test_force_replaces_and_backs_up(tmp_path):
    p = tmp_path / "calibration.json"
    commit(GOOD, p)
    before = p.read_text(encoding="utf-8")
    assert commit(CLOSE, p, force=True).saved
    assert (tmp_path / "calibration.prev.json").read_text(encoding="utf-8") == before
    assert json.loads(p.read_text(encoding="utf-8"))["model"]["separation"] == 1.2


def test_samples_round_trip(tmp_path):
    p = tmp_path / "s.jsonl"
    save_samples(p, SAMPLES)
    assert load_samples(p) == SAMPLES


def test_saved_samples_never_hold_face_positions(tmp_path):
    p = tmp_path / "s.jsonl"
    save_samples(p, {"EXTERNAL": [HeadSample(t=1.0, face=True, yaw=30.0, box=(0.1, 0.2, 0.3, 0.4), nose=(0.2, 0.3))]})
    assert "box" not in p.read_text(encoding="utf-8")
    assert load_samples(p)["EXTERNAL"][0].yaw == 30.0


def test_samples_saved_before_the_rename_still_load(tmp_path):
    p = tmp_path / SAMPLES_FILE
    p.write_text('{"screen": "LG", "t": 1.0, "face": true, "yaw": 30.0}\n', encoding="utf-8")
    assert load_samples(p)["EXTERNAL"][0].yaw == 30.0
