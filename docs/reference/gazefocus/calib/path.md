# gazefocus/calib/path.py
Verified against: GazeFocus@98abf9d · 2026-09-30

Where the calibration drop is (spec §9). Pure geometry, ported from the approved mockup's JS (`docs/superpowers/mockups/03-calibration-approved.html`).
Points are (x, y) in Qt logical px of the virtual desktop; a screen `Rect` is (x, y, w, h).

- **Tours:** `LG_TOUR` = (.5,.5) → (.1,.14) → (.9,.14) → (.9,.86) → (.1,.86) → (.5,.5).
  - `LAPTOP_TOUR` lowers the top waypoints to y .24 (x .12/.88), clear of the dock under the camera.
  - `tour_points(rect, laptop=False)` maps them into a screen; `at(rect, u, v)` maps one fraction.
- **`catmull_rom(points, t)`:** the mockup's `spline`. For t in [0, 1], segment i = ⌊t·n⌋, and the fraction within it is eased in and out (cubic), so the drop slows into each waypoint and lingers in the corners. At t = k/n it is exactly on waypoint k.
- **`travel(p0, p1, t)`:** a trip between screens. A quadratic Bézier with its control point at (mid x, min(y₀, y₁) − `ARC_LIFT` 60 px), with t eased in and out. A level trip rises 30 px at its middle.
- **Stretch:**
  - `mockup_velocity(dist, dt, screen_w)` converts a real move into the mockup's units: px per 60 Hz frame on a `MOCKUP_SCREEN_W` (500 px) screen. The mockup's LG was about 500 px wide, so without this the real drop (4× the speed on a 1920 px screen) would sit at the maximum stretch for the whole tour.
  - `stretch(v)` = min(.55, v · 0.05), as in the mockup.
  - `squash(st)` = (1 + st, 1 − st · .55): the drop's scale along and across the motion.
