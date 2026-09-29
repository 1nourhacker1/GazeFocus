"""MediaPipe Face Landmarker (Tasks API, VIDEO mode) -> HeadSample."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from gazefocus.types import HeadSample
from gazefocus.vision.pose import iris_offsets, yaw_pitch_roll


def next_timestamp_ms(prev_ms: int | None, t: float) -> int:
    """VIDEO mode requires strictly increasing integer timestamps."""
    ms = int(t * 1000)
    if prev_ms is not None and ms <= prev_ms:
        ms = prev_ms + 1
    return ms


def sample_from_result(result, t: float) -> HeadSample:
    if not result.face_landmarks or not result.facial_transformation_matrixes:
        return HeadSample(t=t, face=False)
    yaw, pitch, _roll = yaw_pitch_roll(result.facial_transformation_matrixes[0])
    iris_h, iris_v = iris_offsets([(p.x, p.y) for p in result.face_landmarks[0]])
    return HeadSample(t=t, face=True, yaw=yaw, pitch=pitch, iris_h=iris_h, iris_v=iris_v)


class HeadTracker:
    def __init__(self, model_path: Path) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision

        self._mp = mp
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self._last_ms: int | None = None

    def process(self, bgr: np.ndarray, t: float) -> HeadSample:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        self._last_ms = next_timestamp_ms(self._last_ms, t)
        return sample_from_result(self._landmarker.detect_for_video(image, self._last_ms), t)

    def close(self) -> None:
        self._landmarker.close()
