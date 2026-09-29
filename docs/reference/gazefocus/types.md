# gazefocus/types.py
Verified against: GazeFocus@42223e4 · 2026-09-29

Value types shared by every layer. All frozen dataclasses.

| Type | Fields | Notes |
|---|---|---|
| `Zone` | `LAPTOP`, `LG`, `UNKNOWN` | UNKNOWN never triggers a switch |
| `HeadSample` | `t` (monotonic s), `face`, `yaw`, `pitch` (deg), `iris_h`, `iris_v` (-1..1) | One per processed frame |
| `Decision` | `t`, `zone`, `margin`, `action` (`none`/`switch`/`blocked`), `reason`, `target` | `target` is a Zone; the app maps it to a monitor via the calibration's `zone_monitors` |
