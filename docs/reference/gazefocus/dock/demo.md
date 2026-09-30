# gazefocus/dock/demo.py
Verified against: GazeFocus@c85c304 · 2026-09-30

`gazefocus dock-demo`: the real dock on the primary screen, cycling through every state with no camera. It uses the user's `dock` settings from config.toml.
- `STEPS` is a table of (offset, printed line, view), repeating every `CYCLE_S` (32 s):
  - tracking LG, then a switch to the laptop
  - typing (a key every 150 ms for 2 s), the lid's hold and melt, a blocked glance (wobble)
  - no face (evaporate), face back (condense)
  - paused, resumed, camera unavailable ("!"), back to tracking
- Hovering opens the panel. Clicks print what GazeFocus would do. Ctrl+C or `--seconds` ends it.
- The 2026-09-30 planning run measured one cycle at 7.1 % of one core (0.30 % of the machine), 89 MB RSS.
