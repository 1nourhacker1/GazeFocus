from types import SimpleNamespace

import numpy as np

from gazefocus.viewer import arrow_tip, facing_label, mirror_px, render


def test_facing_label_thresholds():
    assert facing_label(20.0) == "LEFT"
    assert facing_label(-20.0) == "RIGHT"
    assert facing_label(5.0) == "CENTER (laptop)"
    assert facing_label(12.0) == "CENTER (laptop)"  # boundary stays centre


def test_mirror_px():
    assert mirror_px((0.25, 0.5), 640, 480) == (480, 240)


def test_arrow_points_where_you_look_in_the_mirrored_view():
    nose = (320, 240)
    assert arrow_tip(nose, 0.0, 0.0) == nose
    left = arrow_tip(nose, 30.0, 0.0)  # yaw + = turned toward the external monitor (your left)
    assert left[0] < nose[0] and left[1] == nose[1]
    down = arrow_tip(nose, 0.0, 20.0)  # pitch + = looking down
    assert down[1] > nose[1]


def test_render_draws_face_and_no_face():
    frame = np.zeros((480, 640, 3), np.uint8)
    lm = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(478)]
    face = SimpleNamespace(face_landmarks=[lm], facial_transformation_matrixes=[np.eye(4)])
    out = render(frame, face, fps=15.0)
    assert out.shape == frame.shape and out.any()
    assert frame.sum() == 0  # the input frame is not modified
    none = render(frame, SimpleNamespace(face_landmarks=[], facial_transformation_matrixes=[]), fps=15.0)
    assert none.any()
