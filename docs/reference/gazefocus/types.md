# gazefocus/types.py
Verified against: GazeFocus@b887938 · 2026-10-01

Value types shared by every layer. All frozen dataclasses.

| Type | Fields | Notes |
|---|---|---|
| `Zone` | `LAPTOP`, `EXTERNAL`, `UNKNOWN` | UNKNOWN never triggers a switch |
| `HeadSample` | `t` (monotonic s), `face`, `yaw`, `pitch` (deg), `iris_h`, `iris_v` (-1..1), `box`, `nose` (0..1 camera coordinates, **only for the dock's live preview**) | One per processed frame |
| `Decision` | `t`, `zone`, `margin`, `action` (`none`/`switch`/`blocked`), `reason`, `target` | `target` is a Zone; the app maps it to a monitor via the calibration's `zone_monitors` |

`recordable(sample)`: the dict that recordings and calibration samples write, without `box` and `nose`.
- **The external monitor was called "LG" until 2026-10-01** (the author's desk). `LEGACY_NAMES = {"LG": "EXTERNAL"}`, and `Zone._missing_` maps the old value, so `Zone("LG")` is `Zone.EXTERNAL` and old recordings still replay.
- `ZONE_NAMES`: what the user reads, `{EXTERNAL: "External", LAPTOP: "Laptop"}`. The app swaps in the external monitor's own name.
