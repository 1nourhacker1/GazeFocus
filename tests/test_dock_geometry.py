import pytest

from gazefocus.dock.geometry import (
    MARGIN,
    PANEL,
    TOP_GAP,
    VIEWBOX,
    glyph_origin,
    pill_at,
    pill_size,
    placement,
    to_viewbox,
    window_size,
)
from gazefocus.dock.motion import EXPAND

SCALE = 2.625  # 1.75 x 1.5: the user's size (2026-09-30)


def test_the_collapsed_pill_is_115_by_52():
    assert pill_size(SCALE) == pytest.approx((115.5, 52.5))


def test_the_window_fits_the_panel_and_its_shadow():
    w, h = window_size(SCALE)
    assert w == PANEL[0] + 2 * MARGIN and h == TOP_GAP + PANEL[1] + MARGIN


def test_placement_is_top_centre_of_the_work_area():
    x, y, w, h = placement((0, 0, 1707, 1067), SCALE)  # the laptop at 150 %, logical
    assert y == 0 and abs((x + w / 2) - 1707 / 2) <= 1


def test_placement_on_a_screen_left_of_the_primary():
    x, y, w, h = placement((-1920, -302, 0, 778), SCALE)
    assert -1920 < x < 0 and y == -302


def test_pill_morphs_from_collapsed_to_panel():
    w, _ = window_size(SCALE)
    closed, open_ = pill_at(0.0, SCALE, w), pill_at(1.0, SCALE, w)
    assert (closed.hw * 2, closed.hh * 2) == pytest.approx((115.5, 52.5))
    assert closed.r == pytest.approx(52.5 / 2)  # a full pill
    assert (open_.hw * 2, open_.hh * 2) == pytest.approx(PANEL) and open_.r == pytest.approx(26.0)
    assert closed.top == pytest.approx(TOP_GAP) and open_.top == pytest.approx(TOP_GAP)  # anchored at the top


def test_the_spring_overshoot_still_fits_in_the_window():
    w, h = window_size(SCALE)
    peak = max(EXPAND(i / 200) for i in range(201))
    p = pill_at(peak, SCALE, w)
    assert p.left > 0 and p.cx + p.hw < w and p.cy + p.hh < h


def test_contains_follows_the_rounded_shape():
    w, _ = window_size(SCALE)
    p = pill_at(0.0, SCALE, w)
    assert p.contains(p.cx, p.cy)
    assert not p.contains(p.left + 1, p.top + 1)  # the rounded corner is outside
    assert not p.contains(p.cx, p.cy + p.hh + 2)


def test_the_glyph_fills_the_collapsed_pill_and_stays_centred_when_open():
    w, _ = window_size(SCALE)
    closed = pill_at(0.0, SCALE, w)
    x0, y0, k = glyph_origin(0.0, SCALE, closed)
    assert VIEWBOX[0] * k == pytest.approx(115.5) and x0 == pytest.approx(closed.left)
    opened = pill_at(1.0, SCALE, w)
    x1, y1, k1 = glyph_origin(1.0, SCALE, opened)
    assert VIEWBOX[0] * k1 == pytest.approx(77.0) and x1 + VIEWBOX[0] * k1 / 2 == pytest.approx(opened.cx)
    assert y1 + VIEWBOX[1] * k1 + 6 == pytest.approx(opened.top + 41)  # the panel's content starts 6 px below


def test_to_viewbox_inverts_the_glyph_origin():
    origin = (100.0, 4.0, 1.3125)
    assert to_viewbox(100.0 + 44 * 1.3125, 4.0 + 20 * 1.3125, origin) == pytest.approx((44.0, 20.0))
