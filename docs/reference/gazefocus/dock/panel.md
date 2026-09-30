# gazefocus/dock/panel.py
Verified against: GazeFocus@4241da5 · 2026-09-30

The open panel's content (spec §8.4), in the approved mockup's layout. Positions are relative to the panel's top-left, at openness 1:
- **Preview** `PREVIEW` (12, 41, 112 × 105), radius 12.
  - The camera frame is **mirrored** (like `gazefocus live`), cover-fitted, with the face box (green) and the head-direction ray (blue, from the nose, 28 px long).
  - With no frame (paused, camera off), it shows the mockup's dark gradient. A caption sits bottom-left.
- **Info column** from x 135: the title (13 px semibold), then the detail (10.5 px mono: yaw, pitch, margin, time since the last key).
- **Buttons** `BUTTONS`: Pause/Resume (135, 120, 62 × 24) and Recalibrate (203, 120, 85 × 24), in var(--btn) with a .5 px border.
- **Colours** follow the theme: var(--text), var(--sub), var(--btn) for light and dark.

- `button_at(x, y, left, top)` is the hit test.
- `preview_image(bgr)` copies the frame into a QImage that owns its pixels (the camera thread reuses its buffer).
- `draw_panel(..., opacity)` fades the content in and slides it 8 px into place.
