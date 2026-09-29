import math

import numpy as np
import pytest

from gazefocus.vision.pose import LEFT_EYE, RIGHT_EYE, iris_offsets, yaw_pitch_roll


def rot(yaw, pitch, roll):
    a, b, c = (math.radians(v) for v in (yaw, pitch, roll))
    ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return ry @ rx @ rz


def as4x4(r, scale=1.0, t=(0.0, 0.0, 0.0)):
    m = np.eye(4)
    m[:3, :3] = r * scale
    m[:3, 3] = t
    return m


def test_identity_is_zero():
    assert yaw_pitch_roll(np.eye(4)) == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


@pytest.mark.parametrize("angles", [(30, -10, 5), (-45, 12, -3), (70, 0, 0), (0, -25, 0)])
def test_recovers_known_angles(angles):
    assert yaw_pitch_roll(as4x4(rot(*angles))) == pytest.approx(angles, abs=1e-6)


def test_ignores_scale_and_translation():
    m = as4x4(rot(-34, 7, 2), scale=2.5, t=(3.0, -1.0, -40.0))
    assert yaw_pitch_roll(m) == pytest.approx((-34, 7, 2), abs=1e-6)


def test_accepts_3x3():
    assert yaw_pitch_roll(rot(10, 5, 0)) == pytest.approx((10, 5, 0), abs=1e-6)


def test_rejects_bad_shape_and_degenerate():
    with pytest.raises(ValueError):
        yaw_pitch_roll(np.eye(2))
    with pytest.raises(ValueError):
        yaw_pitch_roll(np.zeros((4, 4)))


def eye_landmarks(iris_frac_x=0.5, iris_frac_y=0.5, lid_gap=0.02, swap_corners=False):
    """478 landmarks; both eyes 0.04 wide; iris placed at the given fraction of the opening."""
    lm = [(0.5, 0.5)] * 478
    for (c1, c2, up, lo, iris), x0 in ((RIGHT_EYE, 0.40), (LEFT_EYE, 0.56)):
        a, b = (x0, 0.45), (x0 + 0.04, 0.45)
        if swap_corners:
            a, b = b, a
        lm[c1], lm[c2] = a, b
        lm[up], lm[lo] = (x0 + 0.02, 0.45 - lid_gap / 2), (x0 + 0.02, 0.45 + lid_gap / 2)
        lm[iris] = (x0 + 0.04 * iris_frac_x, 0.45 - lid_gap / 2 + lid_gap * iris_frac_y)
    return lm


def test_centred_iris_is_zero():
    assert iris_offsets(eye_landmarks()) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_iris_at_right_corner_is_plus_one():
    h, _ = iris_offsets(eye_landmarks(iris_frac_x=1.0))
    assert h == pytest.approx(1.0)


def test_corner_order_does_not_matter():
    assert iris_offsets(eye_landmarks(0.25, 0.7, swap_corners=True)) == pytest.approx(
        iris_offsets(eye_landmarks(0.25, 0.7))
    )


def test_values_are_clamped():
    h, v = iris_offsets(eye_landmarks(iris_frac_x=1.6, iris_frac_y=-0.8))
    assert h == 1.0 and v == -1.0


def test_closed_eye_gives_finite_values():  # Review Focus #3
    h, v = iris_offsets(eye_landmarks(iris_frac_x=0.8, lid_gap=0.0))
    assert math.isfinite(h) and math.isfinite(v)
    assert v == 0.0


def test_too_few_landmarks():
    assert iris_offsets([(0.5, 0.5)] * 468) == (0.0, 0.0)
