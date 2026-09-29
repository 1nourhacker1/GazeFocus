# gazefocus/probe.py
Verified against: GazeFocus@65ce39a · 2026-09-29

A guided measurement run: `uv run python -m gazefocus.probe` (in Task 11 this becomes `gazefocus probe`).
- The phases are `LAPTOP` (5 s), `LG` (5 s) and `PAST_LG` (4 s), each with a 2 s countdown.
- Per phase it reports frames, face %, yaw mean/min/max, pitch mean, iris_h mean, and processing ms p50/p95.
  It also reports process CPU as a share of all cores, the camera backend, and the yaw sign.
- `run_probe` takes injected `read_frame`, `track`, `clock`, `sleep` and `say`, so it's unit-tested with a fake clock.
- If the camera won't open it exits with **2** and prints `camera_busy_message`.
