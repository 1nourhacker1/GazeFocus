# gazefocus/dock/geometry.py
Verified against: GazeFocus@e017b50 · 2026-09-30

Sizes and placement (spec §8.1, §8.4, §9), in Qt logical px. Pure.
- **Collapsed pill:** `BASE` (44 × 20) × `dock.scale`. The default of 2.625 (1.75 × 1.5, the user's size) gives **115.5 × 52.5**.
- **Panels** (`PANELS`, each a `PanelSize(w, h, r, glyph_w, content_top)`):
  - `status`, the hover panel: 300 × 158, radius 26, the glyph 77 px wide, content from 41 px. `PANEL` and `PANEL_RADIUS` are its size.
  - `intro`: 300 × 150, radius 24; `result`: 372 × 200, radius 26. Both have a small 36 px glyph and content from 24 px (mockup 03).
  - `mix(a, b, t)` is a panel part-way between two (the pill morphing from the hover panel to the intro).
- **The window** is sized once, for the largest panel plus a 16 px shadow margin, and never moves: 404 × 220. The pill is drawn inside it.
- `placement(work, scale)`: the window at the top centre of a work area (left, top, right, bottom).
- `pill_at(openness, scale, window_w, panel=status)` interpolates size and radius toward the given panel (openness overshoots with the spring; the window still fits it). The pill stays anchored 4 px below the top.
- `glyph_origin(openness, scale, pill, panel=status)`: collapsed, the 88 × 40 glyph fills the pill; open, it stays centred at the top at the panel's `glyph_w`, as in the mockups.
- `Pill.sdf/contains` is the rounded box's signed distance, used for hit tests. `to_viewbox` maps a click into glyph units.
