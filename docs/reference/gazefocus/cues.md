# gazefocus/cues.py
Verified against: GazeFocus@7fdf407 · 2026-09-29

`beep(name)`: `LG` gives 1 beep, `LAPTOP` 2, `DONE` 3, as 450 ms `winsound.Beep` tones.
- The tones are long because idle laptop audio swallows shorter ones.
- They're only audible from the user's own session, not from a sandboxed shell.
- Used by `calibrate-cli` and the app's Recalibrate.
