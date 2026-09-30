# gazefocus/dock/motion.py
Verified against: GazeFocus@14dbe6f · 2026-09-30

Time-based animation primitives: every value is a pure function of `now`, so effects look the same at 60 or 240 Hz and tests need no clock.
The approved mockup animated per frame at 60 Hz; its per-frame factors convert as f^60 per second (0.955 → e^(−2.76 t), 0.962 → e^(−2.33 t), 0.9 → e^(−6.32 t)).

- **Easings:** `lin`, `ease_in`, `ease_out`, `ease_in_out` (cubic), `spring` (1 − e^(−5.5x)·cos 9x, overshoots then settles), `cubic_bezier(x1, y1, x2, y2)`.
  - `EXPAND` = cubic-bezier(.3, 1.45, .5, 1), the panel's spring; it peaks at about 1.067.
- **`Channel`:** a scalar tween. `to(target, now, seconds, ease, delay)` always starts from the current value, so retargeting never jumps. `get`, `busy`, `set`, `target`.
- **`Wave`:** the water's slosh amplitude. `kick(a, at, rate)` can be scheduled for later. Kicks decay at `CALM` (2.76/s) or `FROZEN` (6.32/s, under a closed lid).
- **Particles**, each with `at(now)`, which returns a tuple, or None before it starts and once it's gone:
  - `Stream`: the 6 "Flow" droplets on a quadratic arc (580 ms)
  - `Steam`: rises, drifts, grows and fades (about 1.4 s)
  - `Drop`: falls with gravity until `until`
  - `Ripple`: the click ring (about 0.5 s)
