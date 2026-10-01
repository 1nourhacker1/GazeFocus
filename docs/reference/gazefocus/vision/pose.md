# gazefocus/vision/pose.py
Verified against: GazeFocus@9340308 · 2026-09-29

Pure geometry, no MediaPipe import.

- `yaw_pitch_roll(matrix)`: degrees from a 3×3 or 4×4 matrix, using `R = Ry(yaw)·Rx(pitch)·Rz(roll)`:
  `pitch = asin(-R[1,2])`, `yaw = atan2(R[0,2], R[2,2])`, `roll = atan2(R[1,0], R[1,1])`.
  Uniform scale is divided out (MediaPipe's facial transformation matrix can carry scale) and translation is ignored.
- `iris_offsets(landmarks)`: `(iris_h, iris_v)` in [-1, 1], averaged over both eyes.
  - Horizontal: the iris position between the eye corners.
  - Vertical: the iris position between the lids.
  - A span under 1e-4 (a blink) gives 0 for that axis, so it's never NaN.
- Landmark indices: right eye `33, 133, 159, 145, iris 468`; left eye `362, 263, 386, 374, iris 473`.
- The yaw sign's physical meaning is recorded in the M0 spike notes (not published).
