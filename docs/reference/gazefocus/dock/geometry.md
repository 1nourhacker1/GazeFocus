# gazefocus/dock/geometry.py
Verified against: GazeFocus@2fa5fb5 · 2026-09-30

Sizes and placement (spec §8.1, §8.4), in Qt logical px. Pure.
- **Collapsed pill:** `BASE` (44 × 20) × `dock.scale`. The default of 2.625 (1.75 × 1.5, the user's size) gives **115.5 × 52.5**.
- **Open panel:** 300 × 158, radius 26.
- **The window** is sized once, for the panel plus a 16 px shadow margin, and never moves: 332 × 178. The pill is drawn inside it.
- `placement(work, scale)`: the window at the top centre of a work area (left, top, right, bottom).
- `pill_at(openness, …)` interpolates size and radius (openness overshoots with the spring; the window still fits it). The pill stays anchored 4 px below the top.
- `glyph_origin(openness, …)`: collapsed, the 88 × 40 glyph fills the pill; open, it stays centred at the top at 77 px wide, with the content 6 px below it, as in the mockup.
- `Pill.sdf/contains` is the rounded box's signed distance, used for hit tests. `to_viewbox` maps a click into glyph units.
