# gazefocus/dock/scene.py
Verified against: GazeFocus@fd4a5d6 · 2026-09-30

The glyph's state machine: the approved mockup's animations (spec §8.2, §8.3), time-based and pure, in the mockup's viewBox units (88 × 40).
- Tiles: LG (18, 10, 22, 14) and laptop (48, 14, 22, 14). The focused tile is at 1.18, the other at 0.9, and both at 1.0 when not tracking.

**`update(view, now)`** turns a change into animations. The first view appears without animating, and a change of `title`/`detail` only does nothing.
| Change | Animation |
|---|---|
| The water moves to the other tile | **Flow**, 580 ms: the source drains (290 ms, ease-in) and shrinks; 6 droplets arc over; the target fills (319 ms, from 290 ms) and springs to 1.18 (435 ms, from 244 ms); a slosh of 1.8 |
| Water appears (face back, resume, alert cleared) | condense: 3 drops fall in (staggered 70 ms); fill 500 ms from 160 ms; slosh 1.1 |
| The face is lost | evaporate: 5 steam particles; fill → 0 over 560 ms |
| Paused / alert / idle | drain 440 ms; tiles → 1.0 over 420 ms. Paused also dims (380 ms) and shows the bars. Alert fades in the "!" (250 ms) |
| Resume | tiles spring back (640 ms, from 120 ms); undim 300 ms |
| A new typing burst | the lid closes (180 ms, ease-out) |
| `blocked` rises | a 0.9 wobble (it decays faster under a closed lid) |

**The lid:**
- `lid(now) = min(close, melt)`. `melt` stays 1 for `hold_s` (0.3 s) after the last key, then falls linearly to 0 exactly when the freeze ends.
- Amber = clamp(1.2·lid − 0.2).

**Sampling:**
- `frame(now)` returns a `GlyphFrame` for the renderer.
- `busy(now)` is True while anything moves (tweens, slosh, particles, the melt).
- `fast(now)` covers the quick ones, which get the display's full rate.
- `wake_at(now)` gives the time the melt will start (the window schedules a wake-up then).
- There's no idle animation: `busy` turns False after every transition.
