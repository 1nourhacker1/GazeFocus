# gazefocus/dock/glass.py
Verified against: GazeFocus@8db716d · 2026-09-30

The Liquid Glass material (spec §8.1, M0-C2), rendered on the CPU from the pixels behind the dock. Pure numpy/OpenCV.
- **`prepare(shot, dpr, refraction)`** runs once per change of the backdrop:
  - `heavy`: blur(20px) saturate(1.7), done as a quarter-size Gaussian that's then scaled up
  - `light`: a light blur, for the lens only
- **`luminance` + `pick_dark`:** the theme switches at 0.45 / 0.55 (hysteresis).
- **`render(...)`** writes premultiplied BGRA for one pill shape into the window-sized `out`. It works only on the pill's bounding box (plus the shadow's room), and `step=2` renders at half resolution and scales up.
  - The edge: a signed-distance field with a 1.25 px antialiasing ramp and an analytic outward normal.
  - **Lens rim** (when `refraction` is on): within 18 px of the edge, the lightly blurred backdrop is sampled up to 20 px outward along the normal, with less tint. What's under the edge appears to bend around it.
  - **Tint:** white .36 → .74 as it opens (light), rgb(58,58,64) at .32 → .70 (dark).
  - **Highlights:** the top specular line, a hairline rim, the bottom inner glow, the top-left sheen, and the top-left/bottom-right rim lights. They're composed as 1 − ∏(1 − aᵢ) in one pass. Each is a smooth falloff, never thinner than the sampling (the user's anti-aliasing feedback in M0-C2).
  - **Shadow:** two analytic box-shadows (0 5px 16px .22, 0 1px 2px .2), each a logistic of the offset box's distance.
  - Anything fainter than `INVISIBLE` (8/255) is made fully transparent, colour included: Windows passes clicks through alpha 0 only, and the invisible ring reached ~25 px below the pill, over the browser tabs (final-review fix).
