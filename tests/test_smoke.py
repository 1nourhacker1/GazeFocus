import dataclasses
import hashlib

import pytest

from gazefocus import paths
from gazefocus.types import Decision, HeadSample, Zone

MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


def test_types_are_frozen_and_defaulted():
    s = HeadSample(t=1.0, face=True)
    assert (s.yaw, s.pitch, s.iris_h, s.iris_v) == (0.0, 0.0, 0.0, 0.0)
    d = Decision(t=1.0, zone=Zone.LG, margin=-0.9, action="switch", reason="dwell met", target=Zone.LG)
    assert d.target is Zone.LG
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.t = 2.0  # type: ignore[misc]


def test_app_dir_honours_env(_isolated_home):
    d = paths.app_dir()
    assert d == _isolated_home and d.is_dir()


def test_mediapipe_tasks_api_available():
    from mediapipe.tasks.python import vision

    assert hasattr(vision, "FaceLandmarker")
    assert "VIDEO" in vision.RunningMode.__members__


def test_opencv_has_msmf():
    import cv2

    assert hasattr(cv2, "CAP_MSMF")


def test_model_present_and_verified():
    p = paths.model_path()
    assert p.is_file(), "run: uv run python scripts/fetch_model.py"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == MODEL_SHA256
