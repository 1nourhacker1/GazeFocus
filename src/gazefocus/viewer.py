"""Live mirrored camera view with a head-pose overlay (`gazefocus live`). Frames stay in memory."""

from __future__ import annotations

import math
import sys
import time

import cv2
import numpy as np

from gazefocus.vision.pose import LEFT_EYE, RIGHT_EYE, iris_offsets, yaw_pitch_roll

WINDOW = "GazeFocus live view (q to quit)"
SIDE_DEG = 12.0


def facing_label(yaw: float) -> str:
    if yaw > SIDE_DEG:
        return "LEFT"
    if yaw < -SIDE_DEG:
        return "RIGHT"
    return "CENTER (laptop)"


def mirror_px(pt: tuple[float, float], w: int, h: int) -> tuple[int, int]:
    return int(round((1.0 - pt[0]) * w)), int(round(pt[1] * h))


def arrow_tip(nose: tuple[int, int], yaw: float, pitch: float, length: float = 160.0) -> tuple[int, int]:
    """In the mirrored view the arrow points where the head points (yaw + = your left, pitch + = down)."""
    return (
        int(round(nose[0] - math.sin(math.radians(yaw)) * length)),
        int(round(nose[1] + math.sin(math.radians(pitch)) * length)),
    )


def _text(img: np.ndarray, lines: list[str], color: tuple[int, int, int]) -> None:
    for k, text in enumerate(lines):
        y = 36 + 34 * k
        cv2.putText(img, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(img, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)


def render(frame: np.ndarray, result, fps: float) -> np.ndarray:
    view = cv2.flip(frame, 1)  # a new, mirrored array; the input frame is left untouched
    h, w = view.shape[:2]
    if result.face_landmarks and result.facial_transformation_matrixes:
        pts = [(p.x, p.y) for p in result.face_landmarks[0]]
        yaw, pitch, _ = yaw_pitch_roll(result.facial_transformation_matrixes[0])
        iris_h, iris_v = iris_offsets(pts)
        px = [mirror_px(p, w, h) for p in pts]
        xs, ys = [p[0] for p in px], [p[1] for p in px]
        cv2.rectangle(view, (min(xs), min(ys)), (max(xs), max(ys)), (80, 200, 80), 2)
        for eye in (RIGHT_EYE, LEFT_EYE):
            for i in eye[:2]:
                cv2.circle(view, px[i], 3, (255, 255, 255), -1)
            cv2.circle(view, px[eye[4]], 4, (255, 160, 0), -1)
        tip = arrow_tip(px[1], yaw, pitch)
        if tip != px[1]:
            cv2.arrowedLine(view, px[1], tip, (0, 200, 255), 4, tipLength=0.25)
        lines = [
            f"yaw {yaw:+6.1f} deg   facing {facing_label(yaw)}",
            f"pitch {pitch:+6.1f} deg   iris_h {iris_h:+.2f}  iris_v {iris_v:+.2f}",
        ]
        color = (255, 255, 255)
    else:
        lines, color = ["NO FACE"], (60, 60, 255)
    lines.append(f"{fps:4.1f} fps   (mirrored view; q = quit)")
    _text(view, lines, color)
    return view


def main() -> int:
    from gazefocus.paths import model_path
    from gazefocus.vision.camera import CameraSource
    from gazefocus.vision.tracker import HeadTracker
    from gazefocus.win.camera_usage import camera_busy_message

    cam = CameraSource()
    if not cam.open():
        print(camera_busy_message(exclude=(sys.executable, getattr(sys, "_base_executable", ""))), file=sys.stderr)
        return 2
    tracker = HeadTracker(model_path())
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 960, 720)
    fps, prev = 0.0, time.perf_counter()
    try:
        while True:
            frame = cam.read()
            if frame is None:
                continue
            now = time.perf_counter()
            result = tracker.detect(frame, now)
            fps = 0.9 * fps + 0.1 / max(now - prev, 1e-6)
            prev = now
            cv2.imshow(WINDOW, render(frame, result, fps))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cam.release()
        tracker.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
