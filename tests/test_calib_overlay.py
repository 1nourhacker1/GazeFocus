import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from gazefocus.calib.overlay import DROP_WINDOW, Overlay, draw_drop
from gazefocus.calib.session import Card, DropState, OverlayFrame
from gazefocus.win.capture import keep_on_top

LG = (-1920.0, -302.0, 1920.0, 1080.0)
LAP = (0.0, 0.0, 1706.0, 1066.0)
DIMS = {"LG": 0.25, "LAPTOP": 0.62}


class FakeGrabber:
    made = []

    def __init__(self, w, h):
        self.w, self.h, self.closed = w, h, False
        FakeGrabber.made.append(self)

    def grab(self, x, y):
        return np.full((self.h, self.w, 3), 120, np.uint8)

    def close(self):
        self.closed = True


def frame(dims=DIMS, drop=DropState(100.0, 200.0, 1.0), ring=None, card=None, phase="lg_tour"):
    return OverlayFrame(phase, dict(dims), drop, ring, card)


@pytest.fixture
def overlay(qapp):
    FakeGrabber.made = []
    o = Overlay({"LG": LG, "LAPTOP": LAP}, native=False, grabber_factory=FakeGrabber)
    o.open()
    yield o
    o.hide()


def windows(o):
    return [*o.dims.values(), o.drop, *o.cards.values()]


def test_every_overlay_window_is_click_through_and_never_takes_focus(overlay):
    for w in windows(overlay):
        flags = w.windowFlags()
        for flag in (Qt.WindowTransparentForInput, Qt.WindowDoesNotAcceptFocus, Qt.WindowStaysOnTopHint, Qt.Tool):
            assert flags & flag, (type(w).__name__, flag)
        assert w.testAttribute(Qt.WA_ShowWithoutActivating)
        assert w.isVisible()


def test_each_dim_covers_its_screen_and_fades_to_the_frame(overlay):
    assert overlay.dims["LG"].geometry().getRect() == (-1920, -302, 1920, 1080)
    overlay.show(frame(), 10.0)
    assert overlay.dims["LG"].windowOpacity() == pytest.approx(0.0, abs=0.01)
    overlay.show(frame(), 10.3)
    assert 0.05 < overlay.dims["LG"].windowOpacity() < 0.25
    overlay.show(frame(), 10.61)
    assert overlay.dims["LG"].windowOpacity() == pytest.approx(0.25, abs=0.01)
    assert overlay.dims["LAPTOP"].windowOpacity() == pytest.approx(0.62, abs=0.01)
    assert not overlay.busy(10.61)


def test_the_drop_window_is_centred_on_the_drop(overlay):
    overlay.show(frame(drop=DropState(-500.4, 300.7, 1.0)), 1.0)
    g = overlay.drop.geometry()
    half = DROP_WINDOW // 2
    assert (g.x() + half + overlay.drop.frac[0], g.y() + half + overlay.drop.frac[1]) == pytest.approx((-500.4, 300.7))
    assert (g.width(), g.height()) == (DROP_WINDOW, DROP_WINDOW)


def test_the_drop_is_a_glowing_green_bead_with_a_progress_ring(qapp):
    img = QImage(DROP_WINDOW, DROP_WINDOW, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    c = DROP_WINDOW / 2
    draw_drop(p, c, c, DropState(0, 0, 1.0), progress=0.25, ring_alpha=1.0)
    p.end()
    centre = img.pixelColor(int(c), int(c) + 3)
    assert centre.green() > 150 and centre.green() > centre.red() + 40 and centre.alpha() == 255
    ring_top_right = img.pixelColor(int(c + 17 * 0.7071), int(c - 17 * 0.7071))  # 45°: inside the 25 % arc
    ring_left = img.pixelColor(int(c - 17), int(c))  # 270°: the track only
    assert ring_top_right.alpha() > ring_left.alpha() > 0
    assert img.pixelColor(1, 1).alpha() == 0


def test_a_hidden_drop_draws_nothing(qapp):
    img = QImage(DROP_WINDOW, DROP_WINDOW, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    draw_drop(p, 35, 35, DropState(0, 0, 0.0), progress=0.0, ring_alpha=0.0)
    p.end()
    assert all(img.pixelColor(x, y).alpha() == 0 for x in range(0, 70, 5) for y in range(0, 70, 5))


def test_the_card_appears_on_its_screen_with_its_text(overlay):
    card = Card("LG", "Look at this screen", "Follow the drop with your eyes")
    overlay.show(frame(card=card), 5.0)
    w = overlay.cards["LG"]
    assert w.card == card and overlay.cards["LAPTOP"].card is None
    g = w.geometry()
    assert g.center().x() == pytest.approx(-960, abs=2)
    assert -302 < g.y() < -302 + 0.31 * 1080 < g.y() + g.height()
    overlay.show(frame(card=card), 5.5)
    assert w.windowOpacity() == pytest.approx(1.0, abs=0.01)
    overlay.show(frame(card=None), 5.6)
    overlay.show(frame(card=None), 6.0)
    assert w.windowOpacity() == pytest.approx(0.0, abs=0.01)
    assert FakeGrabber.made and all((g.w, g.h) == (w.width(), w.height()) for g in FakeGrabber.made[:1])


def test_hide_closes_every_window_and_releases_the_grabbers(overlay):
    overlay.show(frame(card=Card("LAPTOP", "Now this screen", "Follow the drop")), 1.0)
    ws = windows(overlay)
    overlay.hide()
    assert not any(w.isVisible() for w in ws)
    assert FakeGrabber.made and all(g.closed for g in FakeGrabber.made)
    overlay.hide()  # twice is harmless


def test_keep_on_top_refuses_a_missing_window():
    assert keep_on_top(0) is False


def test_each_card_window_starts_on_its_own_screen(overlay):
    """So its first render already has that screen's pixel ratio (the laptop is 150 %, the LG 100 %)."""
    for name, (x, y, w, h) in (("LG", LG), ("LAPTOP", LAP)):
        c = overlay.cards[name].geometry().center()
        assert x <= c.x() < x + w and y <= c.y() < y + h, name
