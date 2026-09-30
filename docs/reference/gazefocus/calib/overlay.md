# gazefocus/calib/overlay.py
Verified against: GazeFocus@362439b · 2026-09-30

The calibration overlay (spec §9): dimmed screens, the drop and its progress ring, and the cards. The session (`calib/session.py`) decides where everything is; this module only draws an `OverlayFrame`, with the mockup's CSS transitions turned into time-based fades.

- **Every window:**
  - frameless `Tool | WindowStaysOnTopHint | WindowDoesNotAcceptFocus | WindowTransparentForInput`, with `WA_ShowWithoutActivating`, so it's click-through and never takes focus
  - `make_noactivate` when native (never on the offscreen test platform)
  - Windows are shown in z-order (dims, then cards, then the drop). The app then lifts the dock above them with `capture.keep_on_top`.
- **`DimWindow(rect)`**, one per screen:
  - plain black over the whole screen (logical rect, floor/ceil to cover it)
  - Only its window opacity changes, which the compositor applies for free: no per-pixel repaint.
  - `set_target(alpha, now)` fades over 0.6 s with CSS `ease`.
  - Not excluded from capture, so the dock's and the card's glass show the dimmed screen.
- **`DropWindow`:**
  - 70 × 70 logical px (`DROP_WINDOW`), per-pixel alpha, excluded from capture
  - `set_frame(drop, ring, now)` moves it so its centre is the drop. The sub-pixel remainder (`frac`) is drawn inside, not rounded away.
  - The ring fades in and out over 0.25 s.
- **`draw_drop(p, cx, cy, drop, progress, ring_alpha)`:**
  - **Ring:** r 17, stroke 2. The track is white at .25; the arc is white with a round cap, from 12 o'clock, clockwise.
  - **Drop:** r 9, rotated to the motion and scaled (along, across).
    - Glow: 0 0 14px rgba(48,209,88,.65) and 0 0 3px rgba(0,0,0,.3), as radial gradients.
    - Body: radial gradient at (34 %, 30 %), reaching the box's farthest corner: #e9fff0 0–14 %, #6ee58f 32 %, #30d158 55 %, #1c8f3f 100 %.
    - An inset bottom shade (rgba(0,60,20,.35)).
- **`CardWindow(screen)`**, one per screen, excluded from capture:
  - **Layout:** centred at (0.5, 0.31) of its screen, at least 220 px wide, padding 14/18.
  - **Text:** white, the title 15 px bold, the subtitle 12 px at .8, 3 px apart.
  - **Glass:** a grab of what's behind it, rendered as dark glass by `glass.render(dark=True, openness=0.26)`: a tint of about .42, the mockup's rgba(40,40,48,.42). Radius 20.
  - **Animation:** it fades in over 0.35 s while rising from translate −44 % and scale .96 to −50 % and 1, with a 0.5 s spring (cubic-bezier(.3,1.4,.5,1)). It fades out in reverse.
  - Each card window is created centred on its own screen, so its first render already has that screen's pixel ratio (laptop 150 %, LG 100 %; final-review fix).
  - A new card on a visible window swaps its content in place. `close()` releases the grabber.
- **`Overlay(screens, native, grabber_factory, refraction)`:**
  - `open()` creates and shows every window.
  - `show(frame, now)` applies a frame. Each screen's card is the frame's card if it names that screen.
  - `busy(now)`: a fade is still running.
  - `hide()` closes everything; calling it twice is harmless.
