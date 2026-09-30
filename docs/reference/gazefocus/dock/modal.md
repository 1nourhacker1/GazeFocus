# gazefocus/dock/modal.py
Verified against: GazeFocus@e017b50 · 2026-09-30

The calibration's panels in the dock (spec §9, mockup 03): the intro, and the result with its scatter. They're modal: `DockWindow` keeps them open until a button is pressed. The layout is the mockup's, relative to the panel's top-left in logical px: content from 16 px in and 24 px down, under a small glyph.

- **Intro** (300 × 150), `draw_intro(p, left, top, opacity, dark)`:
  - "Calibrate GazeFocus", 14 px bold.
  - "Sit the way you normally do. Follow the drop with your eyes and turn your head naturally. It takes about 15 seconds.", 12 px at rgba(60,60,67,.8), wrapped to 268 px.
  - `INTRO_BUTTONS`: **Start** (primary: #0a84ff with white text) and **Not now**, at y 108.
- **Result** (372 × 200), `draw_result(p, left, top, result, opacity, dark)`:
  - **Scatter** (`SCATTER`, 160 × 110 at (16, 24), radius 12, rgba(0,0,0,.05)):
    - Every sample as a dot, r 1.6 at .75: LG #0a84ff, laptop #bf5af2.
    - The axes where zero is in view.
    - The **model's own boundary** (margin 0, at the screens' mean iris position) as a dashed line.
    - "LG" and "Laptop" labels beside the means.
  - `plot_map(result)`: (yaw, pitch) → a point in the plot. Both axes fit the samples, with a 15 % margin and at least ±5°. Yaw is flipped when needed so that the **LG is always on the left** (the user's LG yaw is positive; the mockup's was negative). Pitch up is up.
  - **Text column** from x 188, 168 wide:
    - `result.title`, 14 px bold.
    - Saveable results: the mono stats ("yaw / pitch", "LG +29° / −4°", "Laptop …", `fmt_deg` is the mockup's `fm`). Otherwise `result.message` in their place.
    - With a model: "Separation **Xσ · quality**" and a 6 px green (#28a745) meter, min(1, sep/8) wide.
    - Saveable results: the hint (`result.message`, "Look at each screen: the water should follow.").
  - `result_buttons(can_save)`: **Save** (primary) and **Redo** at y 162, or only Redo when it can't be saved.
- `modal_button_at(kind, x, y, left, top, result)`: the button under a point, or None. Save is only a button when the result can be saved.
- Both panels fade in, sliding 8 px, like the hover panel (`dock/panel.py`, whose colours and fonts they share).
