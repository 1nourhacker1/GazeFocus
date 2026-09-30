import numpy as np
import pytest
from PySide6.QtGui import QImage, QPainter, Qt

from gazefocus.dock.glyph import GOO_K, draw_glyph, goo_field, goo_image, smin
from gazefocus.dock.scene import AMBER, GREEN, GlyphScene
from gazefocus.dock.view import ALERT, PAUSED, TRACKING, DockView
from gazefocus.types import Zone

K, TOP = 4.0, 40.0  # 4 px per viewBox unit; room above for the flow's arc


def frame_of(*views, at=None):
    s = GlyphScene(seed=3)
    t = 0.0
    for v in views:
        s.update(v, t)
        t += 5.0  # let each transition finish
    return s.frame(at if at is not None else t)


def render(frame, dark=False):
    img = QImage(int(88 * K), int(TOP + 40 * K), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw_glyph(p, frame, (0.0, TOP, K), dark=dark, dpr=1.0)
    p.end()
    return img


def px(img, u, v):
    c = img.pixelColor(int(u * K), int(TOP + v * K))
    return c.red(), c.green(), c.blue(), c.alpha()


def near(rgba, rgb, tol=12):
    return all(abs(a - b) <= tol for a, b in zip(rgba[:3], rgb)) and rgba[3] > 240


def test_the_focused_tile_holds_green_water(qapp):
    img = render(frame_of(DockView(TRACKING, Zone.LG)))
    assert near(px(img, 29, 20), GREEN[False])
    assert px(img, 59, 22)[3] == 0  # the laptop tile is empty inside


def test_dark_backdrops_get_the_brighter_green(qapp):
    img = render(frame_of(DockView(TRACKING, Zone.LAPTOP)), dark=True)
    assert near(px(img, 59, 22), GREEN[True])


def test_frozen_water_is_amber_under_a_lid(qapp):
    frozen = render(frame_of(DockView(TRACKING, Zone.LG), DockView(TRACKING, Zone.LG, last_key_t=5.0), at=5.2))
    water = px(frozen, 29, 21)
    assert near(water, AMBER[False], tol=16)
    lid_v = 17 + (12.5 - 17) * 1.18  # the lid line (tile y + 2.5), scaled 1.18 about the tile's centre
    assert sum(px(frozen, 29, lid_v)[:3]) < sum(water[:3]) - 150  # a dark line across the amber water


def test_paused_shows_the_bars_and_no_water(qapp):
    img = render(frame_of(DockView(TRACKING, Zone.LG), DockView(PAUSED, Zone.LG)))
    assert px(img, 41.6, 18.5)[3] > 150 and px(img, 46.4, 18.5)[3] > 150
    assert px(img, 29, 20)[3] == 0


def test_alert_shows_an_amber_exclamation(qapp):
    img = render(frame_of(DockView(TRACKING, Zone.LG), DockView(ALERT, Zone.LG)))
    assert near(px(img, 44, 16), AMBER[False], tol=16) and near(px(img, 44, 23.4), AMBER[False], tol=16)


def test_outlines_are_drawn_even_with_no_water(qapp):
    img = render(frame_of(DockView(TRACKING, Zone.LG, face=False)))
    edge = px(img, 18 - 0.4, 17)  # the LG outline's left side (scaled 1.18 about x = 29)
    assert max(px(img, 29 - 11 * 1.18, 17)[3], edge[3]) > 60


def test_the_flow_draws_droplets_between_the_tiles(qapp):
    s = GlyphScene(seed=3)
    s.update(DockView(TRACKING, Zone.LG), 0.0)
    s.update(DockView(TRACKING, Zone.LAPTOP), 1.0)
    f = s.frame(1.3)
    assert f.drops
    x, y, r = max(f.drops, key=lambda d: d[2])
    assert px(render(f), x, y)[3] > 200


def test_smooth_union_melts_nearby_shapes_together(qapp):
    a = b = np.array([0.25], np.float32)  # a point just outside two shapes 0.5 apart...
    assert smin(a, b, GOO_K)[0] < 0  # ...is inside their gooey union (bridges gaps up to k/2)
    assert smin(np.array([5.0]), np.array([-1.0]), GOO_K)[0] == pytest.approx(-1.0)  # far apart: a plain min


def test_goo_is_skipped_when_there_is_nothing_wet(qapp):
    f = frame_of(DockView(TRACKING, Zone.LG), DockView(PAUSED, Zone.LG))
    assert goo_field(f, 4.0) is None and goo_image(f, 4.0, (0, 0, 0)) is None
