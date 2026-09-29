# gazefocus/vision/camera.py
Verified against: GazeFocus@ebc532b · 2026-09-29

`CameraSource(index, width, height)` wraps `cv2.VideoCapture`.
- `open()` tries **MSMF**, then **DirectShow**, and only counts a backend as open after one successful `read()`. The winning backend is stored in `.backend`.
- `read()` returns a BGR frame or `None`. `grab()` takes a frame without decoding it, used to drop frames cheaply when the camera runs faster than the configured FPS.
- `release()` is idempotent. Frames are never written to disk.
