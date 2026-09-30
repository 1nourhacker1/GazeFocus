import numpy as np
import pytest

from gazefocus.dock.geometry import pill_at, window_size
from gazefocus.dock.glass import Grid, luminance, pick_dark, prepare, render

DPR, SCALE = 1.5, 2.625
W, H = (round(v * DPR) for v in window_size(SCALE))


def backdrop(value):
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = value
    return img


def glass(img, openness=0.0, dark=None, refraction=True, step=1):
    bd = prepare(img, DPR, refraction)
    pill = pill_at(openness, SCALE, W / DPR).scaled(DPR)
    if dark is None:
        dark = pick_dark(luminance(bd, pill), False)
    out = np.zeros((H, W, 4), np.uint8)
    render(bd, pill, dpr=DPR, dark=dark, openness=openness, refraction=refraction, step=step, grid=Grid(W, H), out=out)
    return out, pill


def test_inside_is_opaque_and_the_far_corner_transparent():
    out, pill = glass(backdrop((128, 128, 128)))
    assert out[int(pill.cy), int(pill.cx), 3] == 255
    assert out[H - 1, 0, 3] == 0 and out[0, W - 1, 3] == 0


def test_a_soft_shadow_falls_below_the_pill():
    out, pill = glass(backdrop((200, 200, 200)))
    below = out[int(pill.cy + pill.hh + 6 * DPR), int(pill.cx), 3]
    assert 5 < below < 80


def test_the_edge_is_antialiased_not_stepped():
    out, pill = glass(backdrop((128, 128, 128)))
    row = out[int(pill.cy), :, 3].astype(int)
    edge = int(pill.cx - pill.hw)
    ramp = row[edge - 3: edge + 4]
    assert any(40 < v < 215 for v in ramp)  # at least one partial pixel on the edge
    assert all(b >= a - 60 for a, b in zip(ramp, ramp[1:]))  # rising into the pill (shadow aside)


def test_the_theme_follows_the_backdrop_with_hysteresis():
    bd_dark, bd_light = prepare(backdrop((20, 20, 20)), DPR, False), prepare(backdrop((240, 240, 240)), DPR, False)
    pill = pill_at(0.0, SCALE, W / DPR).scaled(DPR)
    assert pick_dark(luminance(bd_dark, pill), False) and not pick_dark(luminance(bd_light, pill), False)
    assert pick_dark(0.5, was_dark=True) and not pick_dark(0.5, was_dark=False)  # the 0.45..0.55 band keeps the theme


def test_a_dark_backdrop_gets_the_dark_tint_and_a_light_one_the_white_tint():
    dark, pill = glass(backdrop((10, 10, 10)))
    light, _ = glass(backdrop((245, 245, 245)))
    c = (int(pill.cy), int(pill.cx))
    assert 20 < int(dark[c][:3].mean()) < 110  # grey glass over black
    assert int(light[c][:3].mean()) > 220  # white glass over white


def test_the_open_panel_is_more_opaque():
    img = backdrop((10, 10, 10))
    closed, pill = glass(img, openness=0.0, dark=False)
    opened, _ = glass(img, openness=1.0, dark=False)
    c = (int(pill.cy), int(pill.cx))
    assert int(opened[c][:3].mean()) > int(closed[c][:3].mean()) + 40  # white .74 against .36


def test_refraction_bends_the_outside_into_the_rim_but_leaves_the_centre_alone():
    pill = pill_at(0.0, SCALE, W / DPR).scaled(DPR)
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (0, 170, 250)  # orange all around...
    img[int(pill.cy - pill.hh):int(pill.cy + pill.hh), int(pill.cx - pill.hw):int(pill.cx + pill.hw)] = 0  # ...black under
    on, _ = glass(img, refraction=True, dark=True)
    off, _ = glass(img, refraction=False, dark=True)
    centre = (int(pill.cy), int(pill.cx))
    assert np.abs(on[centre].astype(int) - off[centre].astype(int)).max() <= 3
    rim = (int(pill.cy), int(pill.cx - pill.hw + 4 * DPR))  # just inside the left end
    assert int(on[rim][2]) > int(off[rim][2]) + 20  # more orange: the lens pulls in what is outside


def test_half_resolution_looks_almost_the_same():
    img = backdrop((128, 128, 128))
    full, _ = glass(img, openness=0.5)
    half, _ = glass(img, openness=0.5, step=2)
    assert np.abs(full[..., 3].astype(int) - half[..., 3].astype(int)).mean() < 3


def test_prepare_keeps_the_shape_and_skips_the_lens_blur_when_off():
    bd = prepare(backdrop((1, 2, 3)), DPR, refraction=False)
    assert bd.heavy.shape == (H, W, 3) and bd.heavy.dtype == np.float32 and bd.light is None
    assert prepare(backdrop((1, 2, 3)), DPR, refraction=True).light.shape == (H, W, 3)


def test_luminance_is_between_0_and_1():
    pill = pill_at(0.0, SCALE, W / DPR).scaled(DPR)
    assert luminance(prepare(backdrop((255, 255, 255)), DPR, False), pill) == pytest.approx(1.0, abs=0.01)
    assert luminance(prepare(backdrop((0, 0, 0)), DPR, False), pill) == pytest.approx(0.0, abs=0.01)
