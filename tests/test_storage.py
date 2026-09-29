import json

from gazefocus.logic.classifier import ZoneModel
from gazefocus.storage import (
    Calibration,
    calibration_path,
    load_calibration,
    load_if_matches,
    now_iso,
    save_calibration,
)
from gazefocus.win.monitors import MonitorInfo

LAP = MonitorInfo(r"\\.\DISPLAY1", "id-lap", (0, 0, 2560, 1600), (0, 0, 2560, 1552), True)
MODEL = ZoneModel(w=(0.05, -0.02, 0.4, 0.0), b=0.9, separation=6.5, mean_lg=(-34, 7, -0.3, 0), mean_laptop=(-3, -8, 0.1, 0))


def cal(fp="abc123"):
    return Calibration(
        created=now_iso(),
        layout_fingerprint=fp,
        monitors=(LAP,),
        zone_monitors={"LAPTOP": "id-lap", "LG": None},
        camera={"index": 0, "width": 640, "height": 480, "backend": "MSMF"},
        model=MODEL,
        samples={"LG": 72, "LAPTOP": 75},
    )


def test_round_trip_and_atomic_write(tmp_path):
    p = tmp_path / "calibration.json"
    c = cal()
    save_calibration(c, p)
    assert load_calibration(p) == (c, None)
    assert not (tmp_path / "calibration.tmp").exists()


def test_missing_file(tmp_path):
    assert load_calibration(tmp_path / "none.json") == (None, None)


def test_corrupt_calibration_returns_none(tmp_path):  # Review Focus #5
    p = tmp_path / "calibration.json"
    p.write_text("{not json", encoding="utf-8")
    c, warn = load_calibration(p)
    assert c is None and "unreadable" in warn
    save_calibration(cal(), p)
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["model"]["w"]
    p.write_text(json.dumps(d), encoding="utf-8")
    c, warn = load_calibration(p)
    assert c is None and "unreadable" in warn


def test_non_finite_model_rejected(tmp_path):
    p = tmp_path / "calibration.json"
    save_calibration(cal(), p)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["model"]["b"] = float("nan")
    p.write_text(json.dumps(d), encoding="utf-8")
    c, warn = load_calibration(p)
    assert c is None and "non-finite" in warn


def test_version_mismatch(tmp_path):
    p = tmp_path / "calibration.json"
    save_calibration(cal(), p)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["version"] = 99
    p.write_text(json.dumps(d), encoding="utf-8")
    c, warn = load_calibration(p)
    assert c is None and "version" in warn


def test_layout_must_match(tmp_path):
    p = tmp_path / "calibration.json"
    save_calibration(cal("abc123"), p)
    assert load_if_matches(p, "abc123")[0] is not None
    c, warn = load_if_matches(p, "zzz999")
    assert c is None and "layout changed" in warn


def test_calibration_path_is_in_app_dir(_isolated_home):
    assert calibration_path() == _isolated_home / "calibration.json"
