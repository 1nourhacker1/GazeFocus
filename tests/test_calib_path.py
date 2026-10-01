import math

import pytest

from gazefocus.calib.path import (
    LAPTOP_TOUR,
    EXTERNAL_TOUR,
    catmull_rom,
    mockup_velocity,
    squash,
    stretch,
    tour_points,
    travel,
)

EXTERNAL = (-1920.0, -302.0, 1920.0, 1080.0)  # the user's EXTERNAL in logical px: x, y, w, h


def close(p, q, tol=1e-6):
    return math.dist(p, q) < tol


def test_tour_points_map_the_waypoints_into_the_screen():
    pts = tour_points(EXTERNAL)
    assert close(pts[0], (-960.0, 238.0))  # the centre
    assert close(pts[1], (-1920 + 0.1 * 1920, -302 + 0.14 * 1080))
    assert len(pts) == len(EXTERNAL_TOUR) == 6 and close(pts[-1], pts[0])


def test_the_laptop_tour_keeps_its_top_waypoints_clear_of_the_dock():
    assert [v for _, v in LAPTOP_TOUR[1:3]] == [0.24, 0.24]
    pts = tour_points((0.0, 0.0, 1706.67, 1066.67), laptop=True)
    assert pts[1][1] == pytest.approx(0.24 * 1066.67)


def test_the_spline_passes_through_each_waypoint_at_its_segment_end():
    pts = tour_points(EXTERNAL)
    n = len(pts) - 1
    for k in range(n):
        assert close(catmull_rom(pts, k / n), pts[k])
    assert close(catmull_rom(pts, 1.0), pts[-1], tol=1e-3)
    assert close(catmull_rom(pts, 0.0), pts[0])


def test_the_drop_lingers_near_the_corners():
    pts = tour_points(EXTERNAL)
    n = len(pts) - 1
    d = 0.004
    near = math.dist(catmull_rom(pts, 1 / n), catmull_rom(pts, 1 / n + d))  # leaving a corner
    mid = math.dist(catmull_rom(pts, 1.5 / n), catmull_rom(pts, 1.5 / n + d))  # mid-edge
    assert near < 0.1 * mid


def test_travel_arcs_over_the_higher_end():
    p0, p1 = (0.0, 100.0), (200.0, 300.0)
    assert close(travel(p0, p1, 0.0), p0) and close(travel(p0, p1, 1.0), p1)
    # control point (100, 100 - 60); eased t = .5 -> .25 p0 + .5 c + .25 p1
    assert close(travel(p0, p1, 0.5), (100.0, 120.0))
    flat = travel((0.0, 50.0), (100.0, 50.0), 0.5)
    assert close(flat, (50.0, 20.0))  # a level trip rises 30 px at its middle


def test_stretch_follows_the_mockup_and_saturates():
    assert stretch(0.0) == 0.0
    assert stretch(4.0) == pytest.approx(0.2)
    assert stretch(100.0) == 0.55
    assert squash(0.2) == pytest.approx((1.2, 1 - 0.2 * 0.55))


def test_velocity_is_measured_in_mockup_px_per_60hz_frame():
    # 1200 px/s across a 1920 px screen is 20 px per frame, which the mockup's 500 px screen sees as ~5.2
    assert mockup_velocity(12.0, 0.01, 1920.0) == pytest.approx(1200 / 60 * 500 / 1920)
    assert mockup_velocity(5.0, 0.0, 1920.0) == 0.0
