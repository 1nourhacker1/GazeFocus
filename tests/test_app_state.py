import logging

import pytest

from gazefocus.app.decision_log import DecisionLogger, setup_logging
from gazefocus.app.state import MAX_TRACKER_FAILURES, AppState, Status
from gazefocus.types import Decision, Zone
from gazefocus.win.focus import SwitchResult


def ready_state():
    s = AppState()
    s.calibration = "ok"
    return s


def test_ready_state_runs_and_wants_the_camera():
    s = ready_state()
    assert s.status is Status.RUNNING and s.camera_wanted and s.switching


def test_fresh_state_is_not_calibrated_and_camera_off():
    s = AppState()
    assert s.status is Status.NOT_CALIBRATED and not s.camera_wanted


@pytest.mark.parametrize(
    "attr,value,status",
    [
        ("paused", True, Status.PAUSED),
        ("locked", True, Status.LOCKED),
        ("suspended", True, Status.SUSPENDED),
        ("calibrating", True, Status.CALIBRATING),
        ("calibration", "layout_changed", Status.LAYOUT_CHANGED),
        ("calibration", "unsupported", Status.UNSUPPORTED),
        ("tracker_failures", MAX_TRACKER_FAILURES, Status.TRACKER_FAILED),
    ],
)
def test_each_reason_stops_switching_and_releases_the_camera(attr, value, status):
    s = ready_state()
    setattr(s, attr, value)
    assert s.status is status and not s.switching and not s.camera_wanted


def test_camera_wait_keeps_retrying_but_does_not_switch():
    s = ready_state()
    s.camera_ok = False
    assert s.status is Status.CAMERA_WAIT and s.camera_wanted and not s.switching


def test_priority_lock_beats_pause_beats_calibration():
    s = AppState()  # not calibrated
    s.paused = True
    assert s.status is Status.PAUSED
    s.locked = True
    assert s.status is Status.LOCKED
    s.calibrating = True
    assert s.status is Status.CALIBRATING


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def logger_with_list():
    log = logging.getLogger("test.decisions")
    log.handlers.clear()
    log.propagate = False
    log.setLevel(logging.INFO)
    h = ListHandler()
    log.addHandler(h)
    return log, h


def d(action, reason, zone=Zone.LG, target=Zone.LG, margin=-0.8):
    return Decision(t=0.0, zone=zone, margin=margin, action=action, reason=reason, target=target)


def test_decision_logger_collapses_blocked_runs_and_skips_none():
    log, h = logger_with_list()
    dl = DecisionLogger(log)
    for r in ("typing 0.2s", "typing 0.3s", "typing 0.4s"):
        dl.decision(d("blocked", r))
    dl.decision(d("none", "dwell 100/500", target=None))
    dl.decision(d("blocked", "typing 0.1s"))
    dl.decision(d("switch", "dwell met"))
    assert h.lines == [
        "zone=LG margin=-0.80 -> BLOCKED(typing 0.2s)",
        "zone=LG margin=-0.80 -> BLOCKED(typing 0.1s)",
        "zone=LG margin=-0.80 -> SWITCH LG",
    ]


def test_outcomes_are_logged_with_titles():
    log, h = logger_with_list()
    dl = DecisionLogger(log)
    dl.outcome("LG", "Notepad", SwitchResult(True, "direct", 12.0))
    dl.outcome("LG", "Task Manager", SwitchResult(False, "failed", 520.0, "refused (elevated window or focus lock)"))
    assert h.lines[0] == "   focused 'Notepad' on LG via direct in 12 ms"
    assert h.lines[1].startswith("   FAIL 'Task Manager' on LG: refused")


def test_setup_logging_writes_both_files(tmp_path):
    app_log, dec_log = setup_logging(tmp_path, to_stderr=False)
    app_log.info("hello")
    dec_log.info("world")
    for h in app_log.handlers + dec_log.handlers:
        h.flush()
    assert "hello" in (tmp_path / "gazefocus.log").read_text(encoding="utf-8")
    assert "world" in (tmp_path / "decisions.log").read_text(encoding="utf-8")
    for h in app_log.handlers + dec_log.handlers:
        h.close()
