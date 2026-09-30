from types import SimpleNamespace

import numpy as np
import pytest

from gazefocus import paths
from gazefocus.vision.tracker import HeadTracker, next_timestamp_ms, sample_from_result


def test_timestamps_strictly_increase():  # Review Focus #6
    assert next_timestamp_ms(None, 1.0) == 1000
    assert next_timestamp_ms(1000, 1.0) == 1001  # same millisecond
    assert next_timestamp_ms(1001, 0.5) == 1002  # clock went backwards
    assert next_timestamp_ms(1000, 1.25) == 1250


def test_no_face_result():
    r = SimpleNamespace(face_landmarks=[], facial_transformation_matrixes=[])
    s = sample_from_result(r, 3.0)
    assert s.t == 3.0 and s.face is False


def test_face_result_extracts_angles():
    lm = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(478)]
    r = SimpleNamespace(face_landmarks=[lm], facial_transformation_matrixes=[np.eye(4)])
    s = sample_from_result(r, 1.5)
    assert s.face is True
    assert (s.yaw, s.pitch) == pytest.approx((0.0, 0.0))
    assert (s.iris_h, s.iris_v) == (0.0, 0.0)  # degenerate eye spans -> 0, never NaN


def test_real_model_on_black_frame_sees_no_face():
    tracker = HeadTracker(paths.model_path())
    try:
        s = tracker.process(np.zeros((480, 640, 3), np.uint8), 0.1)
        s2 = tracker.process(np.zeros((480, 640, 3), np.uint8), 0.1)  # same t must not raise
    finally:
        tracker.close()
    assert s.face is False and s2.face is False


def test_detect_returns_the_raw_result():
    tracker = HeadTracker(paths.model_path())
    try:
        raw = tracker.detect(np.zeros((480, 640, 3), np.uint8), 0.2)
    finally:
        tracker.close()
    assert raw.face_landmarks == [] and raw.facial_transformation_matrixes == []


def test_missing_model_says_how_to_fetch_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_model.py"):
        HeadTracker(tmp_path / "nope.task")


def test_face_result_carries_the_face_box_and_nose_for_the_preview():
    lm = [SimpleNamespace(x=0.3 + 0.001 * i, y=0.2 + 0.001 * i, z=0.0) for i in range(478)]
    r = SimpleNamespace(face_landmarks=[lm], facial_transformation_matrixes=[np.eye(4)])
    s = sample_from_result(r, 1.0)
    assert s.box == pytest.approx((0.3, 0.2, 0.3 + 0.477, 0.2 + 0.477))
    assert s.nose == pytest.approx((0.301, 0.201))  # landmark 1 is the nose tip
