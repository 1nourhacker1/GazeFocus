import math
import random

import pytest

from gazefocus.calib.path import at
from gazefocus.calib.session import (
    CUES,
    LOST_CARD_S,
    PHASES,
    STALE_S,
    Card,
    CalibrationSession,
)
from gazefocus.types import HeadSample

LG = (-1920.0, -302.0, 1920.0, 1080.0)
LAP = (0.0, 0.0, 1706.67, 1066.67)
DOCK = (860.0, 20.0)
FACE = {"LG": 30.0, "LAPTOP": 0.0}

# Phase start times with a face always in view: start .42, travel 1.1, card 1.3, tour 5.2, travel 1.1,
# card 1.2, tour 5.2, return .7, outro .6
STARTS = {"start": 0.0, "lg_travel": 0.42, "lg_card": 1.52, "lg_tour": 2.82, "lap_travel": 8.02,
          "lap_card": 9.12, "lap_tour": 10.32, "return": 15.52, "outro": 16.22, "done": 16.82}


def session():
    s = CalibrationSession(LG, LAP, DOCK)
    s.start(0.0)
    return s


def run(s, t0, t1, *, face=lambda t, s: True, yaw=None, rng=None, fps=15.0, frame_hz=60.0):
    """Drive the session from t0 to t1: frames at frame_hz, a camera sample at fps."""
    rng = rng or random.Random(1)
    frames, t, next_sample = [], t0, t0
    while t <= t1 + 1e-9:
        frames.append(s.frame(t))
        if t >= next_sample - 1e-9:
            if face(t, s):
                target = "LAPTOP" if s.phase.startswith("lap") else "LG"
                y = (yaw or FACE)[target]
                s.on_sample(HeadSample(t=t, face=True, yaw=y + rng.gauss(0, 2), pitch=rng.gauss(0, 2), iris_h=0.0))
            else:
                s.on_sample(HeadSample(t=t, face=False))
            next_sample += 1.0 / fps
        t += 1.0 / frame_hz
    return frames


def test_the_phases_follow_the_mockup_timeline():
    assert [p for p, _ in PHASES] == list(STARTS)[:-1]
    s = session()
    for name, t in STARTS.items():
        if t > 0:
            run(s, s.last_now + 1 / 60, t - 0.02)
            assert s.phase != name, name
        run(s, s.last_now + 1 / 60, t + 0.02)
        assert s.phase == name, name


def test_the_dims_darken_the_screen_you_are_not_looking_at():
    s = session()
    frames = {f.phase: f for f in run(s, 0.0, 17.0)}
    assert frames["start"].dims == {"LG": 0.0, "LAPTOP": 0.0}
    for p in ("lg_travel", "lg_card", "lg_tour"):
        assert frames[p].dims == {"LG": 0.25, "LAPTOP": 0.62}
    for p in ("lap_travel", "lap_card", "lap_tour", "return"):
        assert frames[p].dims == {"LG": 0.62, "LAPTOP": 0.25}
    assert frames["outro"].dims == frames["done"].dims == {"LG": 0.0, "LAPTOP": 0.0}


def test_the_drop_travels_from_the_dock_to_the_lg_and_fades_in():
    s = session()
    run(s, 0.0, 0.42)
    f = s.frame(0.421)
    assert f.phase == "lg_travel" and math.dist((f.drop.x, f.drop.y), DOCK) < 1
    assert f.drop.opacity == pytest.approx(0, abs=0.01)
    assert s.frame(0.42 + 0.125).drop.opacity == pytest.approx(0.5)
    f = s.frame(1.52)
    assert math.dist((f.drop.x, f.drop.y), at(LG, 0.5, 0.5)) < 1 and f.drop.opacity == 1


def test_the_drop_stretches_along_its_motion():
    s = session()
    run(s, 0.0, 0.97)
    f = s.frame(0.97)  # mid-travel toward the LG, which is to the left
    assert f.drop.along > 1.2 and f.drop.across < 1
    assert abs(abs(f.drop.angle) - 180) < 60  # heading left
    held = s.frame(2.0)  # the card: the drop waits at the centre
    assert held.drop.along == pytest.approx(1.0)


def test_the_ring_shows_the_tour_progress():
    s = session()
    frames = run(s, 0.0, 17.0)  # frame i is at t = i / 60
    assert frames[round((2.82 + 2.6) * 60)].ring == pytest.approx(0.5, abs=0.01)
    assert all(f.ring is None for f in frames if not f.phase.endswith("tour"))


def test_each_screen_gets_its_card_before_its_tour():
    s = session()
    frames = {f.phase: f for f in run(s, 0.0, 17.0)}
    assert frames["lg_card"].card == Card("LG", "Look at this screen", "Follow the drop with your eyes")
    assert frames["lap_card"].card == Card("LAPTOP", "Now this screen", "Follow the drop")
    assert frames["lg_tour"].card is None and frames["lap_travel"].card is None


def test_the_drop_reaches_the_laptop_where_its_tour_begins():
    s = session()
    run(s, 0.0, 10.32)
    f = s.frame(10.32)
    assert math.dist((f.drop.x, f.drop.y), at(LAP, 0.5, 0.5)) < 1


def test_samples_come_only_from_the_tours_after_the_first_400_ms():
    s = session()
    run(s, 0.0, 17.0)
    r = s.result()
    assert r.counts == {"LG": len(r.samples["LG"]), "LAPTOP": len(r.samples["LAPTOP"])}
    assert 70 <= r.counts["LG"] <= 74 and 70 <= r.counts["LAPTOP"] <= 74  # 4.8 s x 15 fps
    assert min(x.t for x in r.samples["LG"]) >= 2.82 + 0.4 - 1e-6
    assert max(x.t for x in r.samples["LG"]) <= 8.02 + 1e-6
    assert min(x.t for x in r.samples["LAPTOP"]) >= 10.32 + 0.4 - 1e-6


def test_the_tour_waits_while_no_face_is_seen():
    s = session()
    away = lambda t, s: not (5.42 <= t < 7.42)  # two seconds out of view, mid-way through the LG tour
    frames = run(s, 0.0, 10.5, face=away)
    ring = {round(i / 60, 2): f.ring for i, f in enumerate(frames)}
    assert ring[7.4] == pytest.approx(ring[5.5], abs=0.02)  # the tour clock stood still
    assert s.phase == "lap_travel"  # the rest of the timeline shifted by the two seconds
    assert all(x.t < 5.42 or x.t >= 7.42 for x in s.result().samples["LG"])


def test_after_a_moment_without_a_face_the_card_asks_what_is_wrong():
    s = session()
    run(s, 0.0, 5.0)
    s.on_sample(HeadSample(t=5.0, face=False))
    assert s.frame(5.0 + LOST_CARD_S - 0.05).card is None
    f = s.frame(5.0 + LOST_CARD_S + 0.05)
    assert f.card == Card("LG", "Can't see you", "Is the room too dark?") and f.waiting
    s.on_sample(HeadSample(t=5.5, face=True, yaw=30.0))
    assert s.frame(5.5).card is None and not s.frame(5.5).waiting


def test_a_camera_that_stops_sending_counts_as_no_face():
    s = session()
    run(s, 0.0, 5.0)  # the last sample arrives at ~5.0
    assert not s.frame(5.0 + STALE_S - 0.05).waiting
    assert s.frame(5.0 + STALE_S + 0.1).waiting


def test_too_few_samples_on_a_screen_cannot_be_saved():
    s = session()
    run(s, 0.0, 17.0, fps=5.0)  # a slow camera: the tour can't wait for samples that never come
    r = s.result()
    assert r.counts["LAPTOP"] < 40 and not r.can_save and r.model is None
    assert r.title == "Too few samples"


def test_screens_that_look_alike_are_too_close_to_save():
    s = session()
    run(s, 0.0, 17.0, yaw={"LG": 1.0, "LAPTOP": 0.0})
    r = s.result()
    assert not r.can_save and r.quality in ("too close", None)
    assert r.title == "Too close"
    assert r.message == "Too close. Turn your head a little more, or move the LG closer to the laptop."


def test_a_normal_run_fits_a_model_that_can_be_saved():
    s = session()
    run(s, 0.0, 17.0)
    assert s.phase == "done"
    r = s.result()
    assert r.can_save and r.quality == "excellent" and r.title == "Calibrated ✓"
    assert r.model.separation > 8 and r.model.mean_lg[0] == pytest.approx(30, abs=1.5)


def test_start_again_is_a_redo_from_scratch():
    s = session()
    run(s, 0.0, 17.0)
    s.start(20.0)
    assert s.phase == "start" and s.result().counts == {"LG": 0, "LAPTOP": 0}


def test_cancel_clears_the_screens():
    s = session()
    run(s, 0.0, 4.0)
    s.cancel()
    f = s.frame(4.1)
    assert s.phase == "cancelled" and f.dims == {"LG": 0.0, "LAPTOP": 0.0} and f.drop.opacity == 0


def test_beeps_mark_each_screen_and_the_end():
    assert CUES == {"lg_travel": "LG", "lap_travel": "LAPTOP", "done": "DONE"}
