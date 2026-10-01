# gazefocus/cues.py
Verified against: GazeFocus@b887938 · 2026-10-01

`beep(name)`: `EXTERNAL` gives 1 beep, `LAPTOP` 2, `DONE` 3, as 450 ms `winsound.Beep` tones.
- The tones are long because idle laptop audio swallows shorter ones.
- They're only audible from the user's own session, not from a sandboxed shell.
- Used by `calibrate-cli` and the app's Recalibrate.
