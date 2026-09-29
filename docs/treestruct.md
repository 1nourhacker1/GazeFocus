# GazeFocus docs

Webcam "focus follows gaze" for a two-monitor Windows setup, with a Liquid Glass status dock under the laptop camera.
This root index is hand-written. Sub-indexes appear once `reference/` exists.

## Trust table

| Area | Status | Verified against |
|---|---|---|
| `superpowers/specs/` | Design. §6, §7.4, §8.5, §10 and §15 were amended after Plan 1; §5, §7.1, §7.4, §12.3 and §15 again after Plan 2, and the header, §4.5, §9 and §15 after its final review (2026-09-29). §4 and §7 are implemented and unit-tested, but desk acceptance is pending; §8 and §9 (the dock and overlay) wait for Plan 3 | — |
| `superpowers/mockups/` | Approved interactive mockups; the reference for visuals and timings | — |
| `reference/gazefocus/` | Code-verified per file (see each `Verified against`) | per file |
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
- [gazefocus/vision/camera.py](reference/gazefocus/vision/camera.md)
- [gazefocus/win/camera_usage.py](reference/gazefocus/win/camera_usage.md)
- [M0-D: camera sharing](spikes/m0d-camera-sharing.md)
- [gazefocus/vision/tracker.py](reference/gazefocus/vision/tracker.md)
- [gazefocus/probe.py](reference/gazefocus/probe.md)
- [gazefocus/viewer.py](reference/gazefocus/viewer.md)
- [M0-A: tracking](spikes/m0a-tracking.md)
- [M0-C: glass pill dock](spikes/m0c-glass-dock.md)
- [gazefocus/config.py](reference/gazefocus/config.md)
- [gazefocus/logic/classifier.py](reference/gazefocus/logic/classifier.md)
- [gazefocus/logic/decider.py](reference/gazefocus/logic/decider.md)
- [gazefocus/win/monitors.py](reference/gazefocus/win/monitors.md)
- [gazefocus/storage.py](reference/gazefocus/storage.md)
- [gazefocus/replay.py](reference/gazefocus/replay.md)
- [gazefocus/runtime.py](reference/gazefocus/runtime.md)
- [gazefocus/__main__.py](reference/gazefocus/__main__.md)
- [Plan 1 desk session](spikes/plan1-desk-session.md)
- [gazefocus/win/_api.py](reference/gazefocus/win/_api.md)
- [gazefocus/win/msgwindow.py](reference/gazefocus/win/msgwindow.md)
- [gazefocus/win/windows.py](reference/gazefocus/win/windows.md)
- [gazefocus/win/focus.py](reference/gazefocus/win/focus.md)
- [M0-B: focus switch (pending)](spikes/m0b-focus-switch.md)
- [gazefocus/win/rawinput.py](reference/gazefocus/win/rawinput.md)
- [gazefocus/win/foreground.py](reference/gazefocus/win/foreground.md)
- [gazefocus/win/system.py](reference/gazefocus/win/system.md)
- [gazefocus/app/state.py](reference/gazefocus/app/state.md)
- [gazefocus/app/decision_log.py](reference/gazefocus/app/decision_log.md)
- [gazefocus/app/controller.py](reference/gazefocus/app/controller.md)
- [gazefocus/calibration.py](reference/gazefocus/calibration.md)
- [gazefocus/cues.py](reference/gazefocus/cues.md)
- [gazefocus/app/workers.py](reference/gazefocus/app/workers.md)
- [gazefocus/app/tray.py](reference/gazefocus/app/tray.md)
- [gazefocus/app/main.py](reference/gazefocus/app/main.md)
- [Plan 2 acceptance (pending)](spikes/plan2-acceptance.md)
