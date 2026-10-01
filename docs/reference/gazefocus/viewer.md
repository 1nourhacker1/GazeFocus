# gazefocus/viewer.py
Verified against: GazeFocus@b887938 · 2026-10-01

Live mirrored camera window with a head-pose overlay. Run `uv run python -m gazefocus.viewer` (Task 12 adds `gazefocus live`). Added at the user's request during Task 4.
- The overlay shows: a face box, eye corners (white), iris centres (orange), a head-direction arrow (yellow), and text with yaw, pitch, iris offsets and fps.
- `facing_label(yaw)`: over +12° is `LEFT (EXTERNAL side)`, under −12° is `RIGHT`, anything else is `CENTER (laptop)`. This is display only; the real decision uses the calibrated classifier.
- `arrow_tip` is in mirrored coordinates, so the arrow points where the head points (yaw + means your left, pitch + means down).
- `render(frame, result, fps)` returns a new image; the input frame is never modified. Frames never touch disk.
- If the camera won't open it exits with **2** and prints `camera_busy_message`. **q**, Esc or closing the window quits.
