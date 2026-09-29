# gazefocus/__main__.py
Verified against: GazeFocus@a0e7f5a · 2026-09-29

The console script is `gazefocus` (from `[project.scripts]`). Every command loads `config.toml` first, writing the defaults if it's missing, and prints any config warnings to stderr.

| Command | Needs | Exit codes |
|---|---|---|
| `probe` | camera | 0, 2 |
| `live` | camera (opens a mirrored preview window; q quits) | 0, 2 |
| `calibrate-cli [--seconds 6] [--force]` | camera | 0, 2, 3 (too few samples, indistinguishable screens, or **too close**: the previous calibration is kept unless `--force`; a replaced one is saved as `calibration.prev.json`) |
| `watch [--record FILE] [--seconds S]` | a calibration matching the **current** monitor layout, and the camera | 0, 2, 3 |
| `bench [--minutes 10]` | camera | 0, 2 |
| `replay FILE` | any calibration (no layout check) | 0, 1 (bad file), 3 |
| `diag monitors \| windows [--all] \| focus {LAPTOP,LG} [--delay 3]` | nothing (focus: a window on that screen) | 0, 1 |

- Exit 2 prints `camera_busy_message`, which names the app that "possibly" holds the camera.
- `calibrate-cli` **beeps** as each phase starts: 1 beep = look at the LG, 2 = the laptop, 3 = done.
  - The tones are 450 ms, because shorter ones were swallowed while the laptop's audio woke up.
  - The beeps only play when the user runs the command in their own terminal; the assistant's sandbox has no audio.
- `watch` is a dry run, with simulated focus and no input data. Ctrl+C stops it cleanly.
- In **cmd**, write recording paths as `"%APPDATA%\GazeFocus\recordings\x.jsonl"`. A bash-style `$APPDATA` creates a literal `$APPDATA` folder in the current directory; this happened once during the desk session.
- `main()` calls `configure_console()` so window titles with characters outside the console code page print as `?` instead of crashing.
- `calibrate-cli` saves through `calibration.commit_calibration` (too-close guard, `.prev` backup, raw samples).
- `run [--seconds S]`: the background app (see `app/main.md`). Needs the camera and a calibration for the current layout. Exit codes: 0, 4 (already running), 5 (no model).
