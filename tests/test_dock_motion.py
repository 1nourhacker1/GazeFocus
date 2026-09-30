import math

import pytest

from gazefocus.dock.motion import (
    CALM,
    EXPAND,
    FROZEN,
    Channel,
    Drop,
    Ripple,
    Steam,
    Stream,
    Wave,
    cubic_bezier,
    ease_in,
    ease_in_out,
    ease_out,
    lin,
    spring,
)


@pytest.mark.parametrize("ease", [lin, ease_in, ease_out, ease_in_out, spring, EXPAND])
def test_every_easing_starts_at_0_and_ends_at_1(ease):
    assert ease(0.0) == pytest.approx(0.0, abs=1e-9)
    assert ease(1.0) == pytest.approx(1.0, abs=1e-9)


def test_the_panel_spring_overshoots_like_the_css_curve():
    peak = max(EXPAND(i / 200) for i in range(201))
    assert 1.05 < peak < 1.08  # cubic-bezier(.3,1.45,.5,1) peaks at about 1.067
    assert cubic_bezier(0.42, 0, 0.58, 1)(0.5) == pytest.approx(0.5, abs=1e-6)  # symmetric ease-in-out


def test_spring_overshoots_then_settles():
    assert max(spring(i / 100) for i in range(100)) > 1.0
    assert spring(1.0) == 1.0


def test_channel_tweens_from_its_current_value():
    c = Channel(0.0)
    c.to(1.0, now=10.0, seconds=1.0, ease=lin)
    assert c.get(10.5) == pytest.approx(0.5)
    c.to(0.0, now=10.5, seconds=1.0, ease=lin)  # retarget mid-way: no jump
    assert c.get(10.5) == pytest.approx(0.5)
    assert c.get(11.0) == pytest.approx(0.25)
    assert c.busy(11.0) and not c.busy(11.5)


def test_channel_delay_holds_the_old_value():
    c = Channel(0.2)
    c.to(1.0, now=0.0, seconds=0.5, ease=lin, delay=0.3)
    assert c.get(0.2) == pytest.approx(0.2)
    assert c.get(0.55) == pytest.approx(0.6)
    assert c.busy(0.1) and c.get(0.9) == 1.0


def test_wave_kicks_decay_and_future_kicks_wait():
    w = Wave()
    w.kick(1.8, at=1.0)
    assert w.get(0.5) == 0.0 and w.busy(0.5)  # scheduled: still busy
    assert w.get(1.0) == pytest.approx(1.8)
    assert w.get(2.0) == pytest.approx(1.8 * math.exp(-CALM))  # "decays over about 1 s"
    assert not w.busy(3.0)


def test_wave_under_a_closed_lid_decays_faster():
    calm, frozen = Wave(), Wave()
    calm.kick(0.9, at=0.0)
    frozen.kick(0.9, at=0.0, rate=FROZEN)
    assert frozen.get(0.3) < calm.get(0.3) / 2


def test_stream_has_up_to_six_drops_on_its_arc_only_while_active():
    s = Stream((29.0, 20.0), (44.0, 4.0), (59.0, 22.7), t0=0.0)
    assert s.drops(0.0) == [] and s.drops(0.58) == []
    mid = s.drops(0.29)
    assert 1 <= len(mid) <= 6
    assert all(y < 22.7 for _, y, _ in mid)  # above the target: in flight
    assert s.active(0.3) and not s.active(0.6)


def test_steam_rises_grows_and_fades_out():
    s = Steam(x=50.0, y=20.0, r=1.0, vy=-0.15, seed=1.0, t0=0.0)
    x0, y0, r0, o0 = s.at(0.0)
    _, y1, r1, o1 = s.at(0.5)
    assert y1 < y0 and r1 > r0 and o1 < o0
    assert s.at(-0.1) is None and s.at(2.0) is None  # not yet / faded (o < 0.03 after ~1.4 s)


def test_drop_falls_until_it_reaches_the_water():
    d = Drop(x=60.0, y=10.0, vx=0.0, vy=0.2, r=1.25, until=22.4, t0=0.0)
    assert d.at(0.1)[1] > 10.0
    assert d.at(1.0) is None


def test_ripple_grows_and_fades():
    r = Ripple(x=44.0, y=20.0, t0=0.0)
    assert r.at(0.1)[2] > r.at(0.0)[2]
    assert r.at(1.0) is None
