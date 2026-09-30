import pytest

from gazefocus.app.state import Status
from gazefocus.dock.scene import BIG, SMALL, TILES, GlyphScene
from gazefocus.dock.view import ALERT, IDLE, PAUSED, TRACKING, DockView, view_for
from gazefocus.types import Decision, HeadSample, Zone

LG, LAP = Zone.LG, Zone.LAPTOP


def tracking(focus=LG, **kw):
    return DockView(TRACKING, focus, **kw)


def settle(scene, start, limit=5.0):
    """The first time after `start` at which nothing moves any more."""
    t = start
    while scene.busy(t) and t < start + limit:
        t += 0.05
    return t


def scene_at(view, t=0.0):
    s = GlyphScene(seed=1)
    s.update(view, t)
    return s


def test_the_first_view_appears_without_animating():
    s = scene_at(tracking(LG))
    f = s.frame(0.0)
    assert f.tiles[LG].fill == 1.0 and f.tiles[LAP].fill == 0.0
    assert f.tiles[LG].scale == BIG and f.tiles[LAP].scale == SMALL
    assert not s.busy(0.0)


def test_switch_flows_the_water_to_the_other_tile():
    s = scene_at(tracking(LG))
    s.update(tracking(LAP), 1.0)
    mid = s.frame(1.29)
    assert mid.tiles[LG].fill == pytest.approx(0.0, abs=1e-6)  # the source drained in 290 ms
    assert mid.drops  # droplets in flight
    end = s.frame(1.64)
    assert end.tiles[LAP].fill == pytest.approx(1.0) and not end.drops
    assert s.frame(2.0).tiles[LAP].scale == pytest.approx(BIG, abs=0.01)
    assert s.frame(2.0).tiles[LG].scale == pytest.approx(SMALL)


def test_nothing_moves_once_a_switch_has_settled():
    s = scene_at(tracking(LG))
    s.update(tracking(LAP), 1.0)
    done = settle(s, 1.0)
    assert done < 3.0
    assert not s.busy(done + 5.0)  # no idle animation, ever


def test_typing_closes_the_lid_and_turns_the_water_amber():
    s = scene_at(tracking(LG))
    s.update(tracking(LG, last_key_t=1.0), 1.0)
    f = s.frame(1.18)
    assert f.tiles[LG].lid == pytest.approx(0.95) and f.tiles[LAP].lid == 0.0
    assert f.amber == pytest.approx(1.0)


def test_steady_typing_never_moves_the_lid():
    s = scene_at(tracking(LG))
    t = 1.0
    for _ in range(20):  # a key every 150 ms
        s.update(tracking(LG, last_key_t=t), t)
        t += 0.15
    assert s.frame(t).tiles[LG].lid == pytest.approx(0.95)
    assert not s.busy(t - 0.1)  # holding: no frames needed
    assert s.wake_at(t - 0.1) == pytest.approx(t - 0.15 + 0.3)  # the melt starts after the hold


def test_the_lid_melts_after_the_hold_and_is_gone_when_the_freeze_ends():
    s = scene_at(tracking(LG))
    s.update(tracking(LG, last_key_t=1.0), 1.0)
    assert s.frame(1.29).tiles[LG].lid == pytest.approx(0.95)  # holding
    assert s.frame(1.9).tiles[LG].lid == pytest.approx(0.95 * 0.5)  # halfway through the 1.2 s melt
    assert s.frame(2.5).tiles[LG].lid == 0.0 and s.frame(2.5).amber == 0.0
    assert s.melting(1.9) and not s.melting(2.6)


def test_a_blocked_glance_while_typing_wobbles_the_water():
    s = scene_at(tracking(LG))
    s.update(tracking(LG, last_key_t=1.0), 1.0)
    s.update(tracking(LG, last_key_t=1.0, blocked=True), 1.05)
    assert s.frame(1.06).tiles[LG].amp > 0.5
    assert s.frame(2.5).tiles[LG].amp < 0.02


def test_losing_the_face_evaporates_and_finding_it_condenses():
    s = scene_at(tracking(LG))
    s.update(tracking(LG, face=False), 1.0)
    assert s.frame(1.3).steam  # steam rises
    assert s.frame(1.6).tiles[LG].fill == pytest.approx(0.0)
    s.update(tracking(LG, face=True), 3.0)
    assert s.frame(3.1).parts  # drops fall in
    assert s.frame(3.7).tiles[LG].fill == pytest.approx(1.0)


def test_pause_drains_dims_and_shows_the_bars():
    s = scene_at(tracking(LG))
    s.update(DockView(PAUSED, LG), 1.0)
    f = s.frame(1.5)
    assert f.tiles[LG].fill == pytest.approx(0.0) and f.pause == pytest.approx(1.0)
    assert f.tiles[LG].scale == pytest.approx(1.0) and f.tiles[LAP].scale == pytest.approx(1.0)
    assert f.outline == pytest.approx(0.28)


def test_resume_springs_back_and_refills():
    s = scene_at(DockView(PAUSED, LG))
    s.update(tracking(LG), 1.0)
    f = s.frame(2.0)
    assert f.pause == pytest.approx(0.0) and f.tiles[LG].fill == pytest.approx(1.0)
    assert f.tiles[LG].scale == pytest.approx(BIG, abs=0.01)


def test_alert_shows_the_exclamation_over_empty_tiles():
    s = scene_at(tracking(LG))
    s.update(DockView(ALERT, LG), 1.0)
    f = s.frame(1.6)
    assert f.alert == pytest.approx(1.0) and f.tiles[LG].fill == pytest.approx(0.0)


def test_a_focus_change_without_water_still_moves_the_big_tile():
    s = scene_at(tracking(LG, face=False))
    s.update(tracking(LAP, face=False), 1.0)
    f = s.frame(2.0)
    assert f.tiles[LAP].scale == pytest.approx(BIG, abs=0.01) and f.tiles[LAP].fill == 0.0


def test_title_and_detail_changes_do_not_animate():
    s = scene_at(tracking(LG, title="Focus: LG", detail="a"))
    s.update(tracking(LG, title="Focus: LG", detail="b"), 1.0)
    assert not s.busy(1.0)


def test_a_click_ripples_briefly():
    s = scene_at(tracking(LG))
    s.ripple(44.0, 20.0, 1.0)
    assert s.frame(1.1).ripples and s.busy(1.1)
    assert not s.busy(2.0)


@pytest.mark.parametrize(
    "status, mode, title",
    [
        (Status.PAUSED, PAUSED, "Paused"),
        (Status.LOCKED, PAUSED, "Screen locked"),
        (Status.CALIBRATING, IDLE, "Calibrating…"),
        (Status.CAMERA_WAIT, ALERT, "Camera unavailable"),
        (Status.NOT_CALIBRATED, ALERT, "Not calibrated"),
    ],
)
def test_view_for_maps_every_status(status, mode, title):
    v = view_for(status, focus=LG, face=True, last_key_t=None, decision=None, sample=None, now=0.0, freeze_s=1.5)
    assert v.mode == mode and v.title == title


def test_view_for_running_reads_face_typing_and_blocked():
    blocked = Decision(t=5.0, zone=Zone.LAPTOP, margin=0.8, action="blocked", reason="typing 0.4s", target=LAP)
    sample = HeadSample(5.0, True, yaw=-27.9, pitch=3.1)
    v = view_for(Status.RUNNING, focus=LG, face=True, last_key_t=4.6, decision=blocked, sample=sample, now=5.0, freeze_s=1.5)
    assert v.mode == TRACKING and v.blocked and v.title == "Frozen while typing"
    assert "yaw -27.9°" in v.detail and "margin +0.80" in v.detail and "key 0.4 s ago" in v.detail
    gone = view_for(Status.RUNNING, focus=LG, face=False, last_key_t=None, decision=None, sample=None, now=5.0, freeze_s=1.5)
    assert gone.title == "No face, holding LG" and not gone.blocked


def test_tile_geometry_matches_the_mockup():
    assert TILES[LG] == (18.0, 10.0, 22.0, 14.0) and TILES[LAP] == (48.0, 14.0, 22.0, 14.0)
