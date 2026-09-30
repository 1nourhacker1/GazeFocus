import numpy as np
import pytest
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtTest import QTest

from gazefocus.config import DockCfg
from gazefocus.dock import geometry
from gazefocus.dock.panel import BUTTONS
from gazefocus.dock.scene import GREEN
from gazefocus.dock.view import PAUSED, TRACKING, DockView
from gazefocus.dock.window import DockWindow
from gazefocus.types import HeadSample, Zone

CFG = DockCfg()


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class ManualTicker(QObject):
    tick = Signal()

    def __init__(self):
        super().__init__()
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def handled(self):
        pass

    def close(self):
        pass


class FakeGrabber:
    colour = (200, 200, 200)

    def __init__(self, w, h):
        self.w, self.h, self.grabs = w, h, 0

    def grab(self, x, y):
        self.grabs += 1
        img = np.zeros((self.h, self.w, 3), np.uint8)
        img[:] = FakeGrabber.colour
        return img

    def close(self):
        pass


@pytest.fixture
def dock(qapp):
    FakeGrabber.colour = (200, 200, 200)
    clock, ticker, calls = FakeClock(), ManualTicker(), []
    d = DockWindow(CFG, on_toggle_pause=lambda: calls.append("pause"), on_recalibrate=lambda: calls.append("recal"),
                   on_panel=lambda o: calls.append(("panel", o)), native=False, grabber_factory=FakeGrabber,
                   ticker=ticker, clock=clock, seed=1)
    d.place((0, 0, 1707, 1067))
    d.show()
    d._refresh_backdrop()
    yield d, clock, ticker, calls
    d.close()


def run_ticks(d, clock, ticker, seconds, dt=1 / 240):
    end = clock.t + seconds
    while clock.t < end and ticker.running:
        clock.t += dt
        ticker.tick.emit()


def pixel(d, x, y):
    c = d.img.pixelColor(int(x), int(y))
    return c.red(), c.green(), c.blue(), c.alpha()


def closed_pill(d):
    return geometry.pill_at(0.0, CFG.scale, d.width())


def test_the_first_frame_is_a_pill_with_transparent_surroundings(dock):
    d, clock, ticker, _ = dock
    p = closed_pill(d)
    assert pixel(d, p.cx, p.cy)[3] == 255
    assert pixel(d, 2, d.height() - 2)[3] == 0
    assert not ticker.running  # nothing moves: no frames


def test_a_switch_animates_then_stops_drawing(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(TRACKING, Zone.LG))
    run_ticks(d, clock, ticker, 2.0)
    d.set_view(DockView(TRACKING, Zone.LAPTOP))
    assert ticker.running
    before = d.frames
    run_ticks(d, clock, ticker, 3.0)
    assert not ticker.running and d.frames - before > 100  # at the display's rate while it moved
    x0, y0, k = geometry.glyph_origin(0.0, CFG.scale, closed_pill(d))
    r, g, b, _ = pixel(d, x0 + 59 * k, y0 + 22 * k)  # the laptop tile now holds the water
    assert abs(g - GREEN[False][1]) < 30 and r < 90


def test_an_unchanged_backdrop_costs_no_frames(dock):
    d, clock, ticker, _ = dock
    before = d.frames
    for _ in range(10):
        d._refresh_backdrop()
    assert d.frames == before and d._grabber.grabs >= 11


def test_a_new_backdrop_redraws_once_and_can_flip_the_theme(dock):
    d, clock, ticker, _ = dock
    FakeGrabber.colour = (10, 10, 10)
    before = d.frames
    d._refresh_backdrop()
    assert d.frames == before + 1 and d.dark


def test_hover_opens_the_panel_and_asks_for_the_camera(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    assert ("panel", True) in calls and d.panel_open
    run_ticks(d, clock, ticker, 1.0)
    assert d.openness.get(clock.t) == pytest.approx(1.0)
    d.set_preview(np.zeros((120, 160, 3), np.uint8), HeadSample(clock.t, True))
    assert d.preview is not None


def test_leaving_closes_the_panel_and_drops_the_preview(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    d.set_preview(np.zeros((120, 160, 3), np.uint8), HeadSample(clock.t, True))
    d._leave.timeout.emit()
    assert ("panel", False) in calls and d.preview is None and not d.panel_open
    d.set_preview(np.zeros((120, 160, 3), np.uint8), HeadSample(clock.t, True))
    assert d.preview is None  # frames are refused while closed


def test_clicking_the_pill_toggles_pause_but_the_shadow_does_nothing(dock):
    d, clock, ticker, calls = dock
    p = closed_pill(d)
    QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.cx), int(p.cy)))
    assert calls == ["pause"] and ticker.running  # the ripple
    QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.cx), int(p.cy + p.hh + 8)))
    assert calls == ["pause"]


def test_the_open_panel_buttons(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    pill = geometry.pill_at(1.0, CFG.scale, d.width())
    left = pill.cx - geometry.PANEL[0] / 2
    for name, want in (("recalibrate", "recal"), ("pause", "pause")):
        c = BUTTONS[name].center()
        QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(left + c.x()), int(pill.top + c.y())))
        assert calls[-1] == want


def test_text_changes_redraw_only_while_the_panel_is_open(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(TRACKING, Zone.LG, title="Focus: LG", detail="a"))
    run_ticks(d, clock, ticker, 2.0)
    before = d.frames
    d.set_view(DockView(TRACKING, Zone.LG, title="Focus: LG", detail="b"))
    assert d.frames == before
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    before = d.frames
    d.set_view(DockView(TRACKING, Zone.LG, title="Focus: LG", detail="c"))
    assert d.frames == before + 1


def test_hidden_means_no_grabs_and_no_frames(dock):
    d, clock, ticker, _ = dock
    d.set_hidden(True)
    grabs = d._grabber.grabs
    d._refresh_backdrop()
    assert not d.isVisible() and d._grabber.grabs == grabs
    d.set_hidden(False)
    assert d.isVisible()


def test_the_lid_wakes_the_clock_after_the_hold(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(TRACKING, Zone.LG))
    run_ticks(d, clock, ticker, 2.0)
    d.set_view(DockView(TRACKING, Zone.LG, last_key_t=clock.t))
    run_ticks(d, clock, ticker, 0.25)  # the lid closes (180 ms), then holds
    assert not ticker.running and d._wake.isActive()  # asleep, with the melt's start scheduled


def test_slow_animations_are_capped_at_60_fps(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(TRACKING, Zone.LG))
    run_ticks(d, clock, ticker, 2.0)
    key_t = clock.t
    d.set_view(DockView(TRACKING, Zone.LG, last_key_t=key_t))
    run_ticks(d, clock, ticker, 0.25)
    clock.t = key_t + 0.4  # past the 0.3 s hold: the lid is melting
    d._kick()
    assert ticker.running
    before = d.frames
    run_ticks(d, clock, ticker, 0.5)  # 120 ticks at 240 Hz
    assert 20 <= d.frames - before <= 40  # about 30 frames: 60 fps


def test_paused_shows_resume_and_no_camera(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(PAUSED, Zone.LG, title="Paused"))
    c = d._content()
    assert c.pause_label == "Resume" and c.preview is None and c.caption == "camera off"


def test_a_new_typing_freeze_reaches_the_lid(dock):
    d, clock, ticker, _ = dock
    d.set_freeze(0.8)
    assert d.scene.freeze_s == 0.8


def move(d, x, y, enter=False):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent, QMouseEvent
    from PySide6.QtWidgets import QApplication

    p = QPointF(x, y)
    ev = QEnterEvent(p, p, p) if enter else QMouseEvent(QEvent.MouseMove, p, p, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(d, ev)


def test_the_hover_starts_only_over_the_pill_not_its_shadow(dock):
    """The shadow reaches ~25 px below the pill: approaching through it must not start the 350 ms hover."""
    d, clock, ticker, _ = dock
    p = closed_pill(d)
    move(d, p.cx, p.cy + p.hh + 10, enter=True)  # into the window, on the shadow
    assert not d._hover.isActive()
    move(d, p.cx, p.cy)  # onto the pill
    assert d._hover.isActive()
    move(d, p.cx, p.cy + p.hh + 10)  # back onto the shadow before it opened
    assert not d._hover.isActive()


def test_leaving_the_open_panel_onto_its_shadow_starts_closing(dock):
    d, clock, ticker, _ = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    pill = geometry.pill_at(1.0, CFG.scale, d.width())
    move(d, pill.cx, pill.cy + pill.hh + 6)
    assert d._leave.isActive()
    move(d, pill.cx, pill.cy)
    assert not d._leave.isActive()


def ok_result():
    import random

    from gazefocus.calib.session import CalibrationResult
    from gazefocus.logic.classifier import fit_zone_model

    rng = random.Random(2)
    lg = [HeadSample(i, True, 30 + rng.gauss(0, 2), rng.gauss(0, 2), 0.0) for i in range(50)]
    lap = [HeadSample(i, True, rng.gauss(0, 2), rng.gauss(0, 2), 0.0) for i in range(50)]
    return CalibrationResult(fit_zone_model(lg, lap), {"LG": lg, "LAPTOP": lap}, {"LG": 50, "LAPTOP": 50},
                             "excellent", "Calibrated ✓", "Look at each screen: the water should follow.")


def click_modal(d, clock, name, kind="intro", result=None):
    from gazefocus.dock.modal import INTRO_BUTTONS, result_buttons

    pill = geometry.pill_at(d.openness.get(clock.t), CFG.scale, d.width(), geometry.PANELS[kind])
    left = pill.cx - geometry.PANELS[kind].w / 2
    rects = INTRO_BUTTONS if kind == "intro" else result_buttons(True)
    c = rects[name].center()
    QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(left + c.x()), int(pill.top + c.y())))


def test_the_intro_is_modal_and_leaving_it_does_not_close_it(dock):
    d, clock, ticker, calls = dock
    d.show_intro(lambda: calls.append("start"), lambda: calls.append("cancel"))
    run_ticks(d, clock, ticker, 1.0)
    assert d.modal == "intro" and d.openness.get(clock.t) == pytest.approx(1.0)
    pill = geometry.pill_at(1.0, CFG.scale, d.width(), geometry.PANELS["intro"])
    assert (pill.hw * 2, pill.hh * 2) == pytest.approx((300.0, 150.0))
    move(d, pill.cx, pill.cy + pill.hh + 6)  # onto the shadow
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    QApplication.sendEvent(d, QEvent(QEvent.Leave))
    assert not d._leave.isActive() and d.openness.target == 1.0
    assert ("panel", True) not in calls  # no camera preview for the calibration's panels


def test_the_intro_buttons_start_and_cancel(dock):
    d, clock, ticker, calls = dock
    for name in ("start", "cancel"):
        d.show_intro(lambda: calls.append("start"), lambda: calls.append("cancel"))
        run_ticks(d, clock, ticker, 1.0)
        click_modal(d, clock, name)
        assert calls[-1] == name


def test_clicks_outside_the_modal_buttons_do_nothing(dock):
    d, clock, ticker, calls = dock
    d.show_intro(lambda: calls.append("start"), lambda: calls.append("cancel"))
    run_ticks(d, clock, ticker, 1.0)
    pill = geometry.pill_at(1.0, CFG.scale, d.width(), geometry.PANELS["intro"])
    QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(pill.cx), int(pill.cy - 20)))  # the paragraph
    assert calls == []  # not even a pause


def test_the_result_panel_saves_or_redoes(dock):
    d, clock, ticker, calls = dock
    d.show_result(ok_result(), lambda: calls.append("save"), lambda: calls.append("redo"))
    run_ticks(d, clock, ticker, 1.0)
    pill = geometry.pill_at(1.0, CFG.scale, d.width(), geometry.PANELS["result"])
    assert (pill.hw * 2, pill.hh * 2) == pytest.approx((372.0, 200.0))
    click_modal(d, clock, "save", "result")
    click_modal(d, clock, "redo", "result")
    assert calls == ["save", "redo"]


def test_close_modal_closes_and_the_hover_panel_works_again(dock):
    d, clock, ticker, calls = dock
    d.show_intro(lambda: None, lambda: None)
    run_ticks(d, clock, ticker, 1.0)
    d.close_modal()
    run_ticks(d, clock, ticker, 1.0)
    assert d.modal is None and d.openness.get(clock.t) == pytest.approx(0.0)
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    assert d.panel_open and ("panel", True) in calls
    pill = geometry.pill_at(1.0, CFG.scale, d.width())
    assert (pill.hw * 2, pill.hh * 2) == pytest.approx(geometry.PANEL)


def test_the_intro_replacing_the_hover_panel_stops_the_preview(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    d.set_preview(np.zeros((120, 160, 3), np.uint8), HeadSample(clock.t, True))
    d.show_intro(lambda: None, lambda: None)
    assert calls[-1] == ("panel", False) and d.preview is None
    run_ticks(d, clock, ticker, 1.0)
    assert d.panel_size(clock.t) == geometry.PANELS["intro"]  # morphed from the hover panel's size


def test_a_pill_click_goes_to_on_pill_when_the_app_gives_one(qapp):
    calls = []
    d = DockWindow(CFG, on_toggle_pause=lambda: calls.append("pause"), on_recalibrate=lambda: None,
                   on_pill=lambda: calls.append("pill"), native=False, grabber_factory=FakeGrabber,
                   ticker=ManualTicker(), clock=FakeClock(), seed=1)
    try:
        d.place((0, 0, 1707, 1067))
        d.show()
        p = closed_pill(d)
        QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.cx), int(p.cy)))
        assert calls == ["pill"]
    finally:
        d.close()


def test_the_pill_centre_is_where_the_drop_leaves_from(dock):
    d, clock, ticker, calls = dock
    p = closed_pill(d)
    assert d.pill_centre() == pytest.approx((d.x() + p.cx, d.y() + p.cy))
    assert d.raise_to_top() is False  # not a native window on the test platform


def test_a_double_click_on_the_pill_is_one_click(dock):
    d, clock, ticker, calls = dock
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    p = closed_pill(d)
    at = QPointF(p.cx, p.cy)
    # what Windows sends for a double-click: WM_LBUTTONDOWN, UP, DBLCLK (Qt: a press and a double-click), UP
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonPress,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        held = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        QApplication.sendEvent(d, QMouseEvent(kind, at, at, Qt.LeftButton, held, Qt.NoModifier))
    assert calls.count("pause") == 1


def test_closing_the_dock_stops_its_timers_and_reports_the_panel_closed(qapp):
    calls = []
    d = DockWindow(CFG, on_toggle_pause=lambda: None, on_recalibrate=lambda: None,
                   on_panel=lambda o: calls.append(o), native=False, grabber_factory=FakeGrabber,
                   ticker=ManualTicker(), clock=FakeClock(), seed=1)
    d.place((0, 0, 1707, 1067))
    d.show()
    d._hover.timeout.emit()
    d._leave.start()
    d._wake.start(5000)
    d.close()
    assert calls == [True, False]  # the app turns the camera preview off again
    assert not (d._hover.isActive() or d._leave.isActive() or d._wake.isActive())


def test_showing_again_redraws_what_changed_while_hidden(dock):
    d, clock, ticker, _ = dock
    d.set_view(DockView(TRACKING, Zone.LG))
    run_ticks(d, clock, ticker, 2.0)
    d.set_hidden(True)
    d.set_view(DockView(TRACKING, Zone.LAPTOP))  # changes while hidden: nothing is drawn
    clock.t += 5.0
    d.set_hidden(False)
    before = d.frames
    d._refresh_backdrop()  # the grab after showing: the same backdrop as before
    assert d.frames > before


def test_hiding_closes_the_open_panel(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    d.set_hidden(True)
    assert not d.panel_open and calls[-1] == ("panel", False)


def test_a_click_while_the_panel_closes_is_still_a_panel_click(dock):
    d, clock, ticker, calls = dock
    d._hover.timeout.emit()
    run_ticks(d, clock, ticker, 1.0)
    d._leave.timeout.emit()  # closing: 380 ms
    clock.t += 0.05
    assert d.openness.get(clock.t) > 0.5
    pill = geometry.pill_at(d.openness.get(clock.t), CFG.scale, d.width())
    QTest.mouseClick(d, Qt.LeftButton, Qt.NoModifier, QPoint(int(pill.cx), int(pill.cy)))  # on the panel, no button
    assert "pause" not in calls
