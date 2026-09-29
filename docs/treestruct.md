# GazeFocus docs

Webcam "focus follows gaze" for a two-monitor Windows setup, with a Liquid Glass status dock under the laptop camera.
This root index is hand-written. Sub-indexes appear once `reference/` exists.

## Trust table

| Area | Status | Verified against |
|---|---|---|
| `superpowers/specs/` | **Design, not code-verified.** No source exists yet. | — |
| `superpowers/mockups/` | Approved interactive mockups; the reference for visuals and timings | — |
| `reference/gazefocus/` | Mirror docs, one per source file; each carries its own `Verified against` sha | per file |
| `spikes/` | Hardware spike results, pasted from real runs | per file |

## Contents

- [Design spec (2026-09-29)](superpowers/specs/2026-09-29-gazefocus-design.md): behaviour, architecture, dock, calibration, config, testing, spikes.
- Mockups (open in a browser):
  - [01: dock style options](superpowers/mockups/01-dock-style-options.html) (superseded)
  - [02: liquid dock](superpowers/mockups/02-dock-liquid-approved.html) (**approved**)
  - [03: calibration flow](superpowers/mockups/03-calibration-approved.html) (**approved**)

## Reference docs

- [gazefocus/types.py](reference/gazefocus/types.md)
- [gazefocus/paths.py](reference/gazefocus/paths.md)
- [gazefocus/vision/pose.py](reference/gazefocus/vision/pose.md)
