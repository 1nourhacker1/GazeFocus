# GazeFocus docs

Webcam "focus follows gaze" for a two-monitor Windows setup, with a Liquid Glass status dock under the laptop camera.
This root index is hand-written. The hardware spike notes and build plans behind the design are not published; their results are summarised in the spec and the reference docs.

## Trust table

| Area | Status | Verified against |
|---|---|---|
| `superpowers/specs/` | Design. §9 is implemented and accepted at the desk (Plan 4, 2026-09-30; §9 item 9 records it as built, §15 amended). §8 is implemented (Plan 3; §8.2, §8.4, §8.5 and §15 amended). §8 amended with the M0-C2 result, and §7.3 and §12 with M0-B (2026-09-30). §6, §7.4, §8.5, §10 and §15 were amended after Plan 1; §5, §7.1, §7.4, §12.3 and §15 again after Plan 2, and the header, §4.5, §9 and §15 after its final review (2026-09-29). §4 and §7 are implemented, unit-tested and accepted at the desk (2026-09-30); §8 (the dock) was accepted at the desk on 2026-09-30 | — |
| `superpowers/mockups/` | Approved interactive mockups; the reference for visuals and timings | — |
| `reference/gazefocus/` | Code-verified per file (see each `Verified against`) | per file |

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
- [gazefocus/vision/tracker.py](reference/gazefocus/vision/tracker.md)
- [gazefocus/probe.py](reference/gazefocus/probe.md)
- [gazefocus/viewer.py](reference/gazefocus/viewer.md)
- [gazefocus/config.py](reference/gazefocus/config.md)
- [gazefocus/logic/classifier.py](reference/gazefocus/logic/classifier.md)
- [gazefocus/logic/decider.py](reference/gazefocus/logic/decider.md)
- [gazefocus/win/monitors.py](reference/gazefocus/win/monitors.md)
- [gazefocus/storage.py](reference/gazefocus/storage.md)
- [gazefocus/replay.py](reference/gazefocus/replay.md)
- [gazefocus/runtime.py](reference/gazefocus/runtime.md)
- [gazefocus/__main__.py](reference/gazefocus/__main__.md)
- [gazefocus/win/_api.py](reference/gazefocus/win/_api.md)
- [gazefocus/win/msgwindow.py](reference/gazefocus/win/msgwindow.md)
- [gazefocus/win/windows.py](reference/gazefocus/win/windows.md)
- [gazefocus/win/focus.py](reference/gazefocus/win/focus.md)
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
- [gazefocus/dock/motion.py](reference/gazefocus/dock/motion.md)
- [gazefocus/dock/view.py](reference/gazefocus/dock/view.md)
- [gazefocus/dock/scene.py](reference/gazefocus/dock/scene.md)
- [gazefocus/dock/geometry.py](reference/gazefocus/dock/geometry.md)
- [gazefocus/dock/glass.py](reference/gazefocus/dock/glass.md)
- [gazefocus/dock/glyph.py](reference/gazefocus/dock/glyph.md)
- [gazefocus/dock/panel.py](reference/gazefocus/dock/panel.md)
- [gazefocus/win/capture.py](reference/gazefocus/win/capture.md)
- [gazefocus/dock/ticker.py](reference/gazefocus/dock/ticker.md)
- [gazefocus/dock/window.py](reference/gazefocus/dock/window.md)
- [gazefocus/dock/demo.py](reference/gazefocus/dock/demo.md)
- [gazefocus/calib/path.py](reference/gazefocus/calib/path.md)
- [gazefocus/calib/session.py](reference/gazefocus/calib/session.md)
- [gazefocus/calib/overlay.py](reference/gazefocus/calib/overlay.md)
- [gazefocus/dock/modal.py](reference/gazefocus/dock/modal.md)
- [gazefocus/calib/run.py](reference/gazefocus/calib/run.md)
