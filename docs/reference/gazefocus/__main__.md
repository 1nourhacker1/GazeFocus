# gazefocus/__main__.py
Verified against: GazeFocus@9a6a614 · 2026-09-29

The console script is `gazefocus` (from `[project.scripts]`). Every command loads `config.toml` first, writing the defaults if it's missing, and prints any config warnings to stderr.

| Command | Needs | Exit codes |
|---|---|---|
| `probe` | camera | 0, 2 |
| `live` | camera (opens a mirrored preview window; q quits) | 0, 2 |
| `calibrate-cli [--seconds 6]` | camera | 0, 2, 3 (too few samples or indistinguishable screens) |
| `watch [--record FILE] [--seconds S]` | a calibration matching the **current** monitor layout, and the camera | 0, 2, 3 |
| `bench [--minutes 10]` | camera | 0, 2 |
| `replay FILE` | any calibration (no layout check) | 0, 1 (bad file), 3 |

- Exit 2 prints `camera_busy_message`, which names the app that "possibly" holds the camera.
- `calibrate-cli` **beeps** as each phase starts: 1 beep = look at the LG, 2 = the laptop, 3 = done.
  - The tones are 450 ms, because shorter ones were swallowed while the laptop's audio woke up.
  - The beeps only play when the user runs the command in their own terminal; the assistant's sandbox has no audio.
- `watch` is a dry run, with simulated focus and no input data. Ctrl+C stops it cleanly.
- In **cmd**, write recording paths as `"%APPDATA%\GazeFocus\recordings\x.jsonl"`. A bash-style `$APPDATA` creates a literal `$APPDATA` folder in the current directory; this happened once during the desk session.
