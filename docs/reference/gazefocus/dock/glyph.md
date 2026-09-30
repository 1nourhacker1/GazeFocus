# gazefocus/dock/glyph.py
Verified against: GazeFocus@ca037fd · 2026-09-30

Draws a `GlyphFrame` (from `scene.py`) with QPainter, in the mockup's viewBox units. `origin` = (x0, y0, k): where (0, 0) goes, and k logical px per unit.
- **Goo layer:** the water bodies, the flow's droplets and the falling drops are one signed-distance field, merged with a polynomial smooth minimum (`GOO_K` 1.2). Drops melt into the water, like the mockup's blur-and-threshold SVG filter (spec §8.1).
  - Each tile's water is its clip rect (inset 1.7, radius 2.2) intersected with the region below the wave surface `level + amp·sin(2.4π·x + phase)`, scaled with its tile.
  - The field is rasterised at the screen's resolution over `GOO_BOX`, and skipped when nothing is wet.
- **QPainter parts:**
  - outlines: radius 3.6, 1.3 wide, var(--glyph) × `outline`
  - highlights, and the lid line (1.25, round caps)
  - steam (water colour) and ripples (0.8 strokes)
  - pause bars at (40.2 | 45, 13.5, 2.8 × 10)
  - the amber "!" between the tiles
- **Colours:**
  - glyph rgba(28,28,32,.82) on light, rgba(255,255,255,.88) on dark
  - water green → amber by `frame.amber`
