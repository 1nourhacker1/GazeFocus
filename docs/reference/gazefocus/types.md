# gazefocus/types.py
Verified against: GazeFocus@beaa5d8 · 2026-09-30

Value types shared by every layer. All frozen dataclasses.

| Type | Fields | Notes |
|---|---|---|
| `Zone` | `LAPTOP`, `LG`, `UNKNOWN` | UNKNOWN never triggers a switch |
| `HeadSample` | `t` (monotonic s), `face`, `yaw`, `pitch` (deg), `iris_h`, `iris_v` (-1..1), `box`, `nose` (0..1 camera coordinates, **only for the dock's live preview**) | One per processed frame |
| `Decision` | `t`, `zone`, `margin`, `action` (`none`/`switch`/`blocked`), `reason`, `target` | `target` is a Zone; the app maps it to a monitor via the calibration's `zone_monitors` |

`recordable(sample)`: the dict that recordings and calibration samples write, without `box` and `nose`.
