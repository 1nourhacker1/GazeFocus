# gazefocus/dock/view.py
Verified against: GazeFocus@b887938 · 2026-10-01

What the dock should show (spec §8.2), derived from the app's state. Pure.

`DockView(mode, focus, face, last_key_t, blocked, title, detail)`:
- `mode`: `TRACKING`, `PAUSED`, `ALERT` or `IDLE`. `focus` is the tile that gets the water.
- `last_key_t` drives the typing lid. `blocked` means a switch is held back while typing, so the water wobbles.
- `title` and `detail` are the open panel's text. `glyph_key()` leaves them out, so text changes never animate the glyph.

`view_for(status, *, focus, face, last_key_t, decision, sample, now, freeze_s, names=ZONE_NAMES)`: `names` is what each screen is called (the app passes the external monitor's own name, e.g. "LG FHD"):
| Status | Mode | Title |
|---|---|---|
| RUNNING | tracking | "No face, holding <name>", "Frozen while typing" (inside the freeze) or "Focus: <name>" (e.g. "Focus: LG FHD", "Focus: Laptop") |
| PAUSED / LOCKED / SUSPENDED | paused | "Paused" / "Screen locked" / "Asleep" |
| CALIBRATING | idle | "Calibrating…" / "follow the drop · Esc cancels" |
| CAMERA_WAIT, NOT_CALIBRATED, LAYOUT_CHANGED, UNSUPPORTED, TRACKER_FAILED | alert | "Camera unavailable", "Not calibrated", … |

- `blocked` = the decision is `blocked` for the reason category "typing".
- `detail` reads: yaw and pitch, the margin, and the time since the last key.
