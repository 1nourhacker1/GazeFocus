"""Audible calibration cues: 1 beep = look at the LG, 2 = look at the laptop, 3 = done.

450 ms tones: idle laptop audio needs ~200-300 ms to wake, so shorter ones get swallowed
(desk session). Sound only plays from the user's own session, not from a sandboxed shell.
"""

from __future__ import annotations

BEEPS = {"LG": 1, "LAPTOP": 2, "DONE": 3}


def beep(name: str) -> None:
    import winsound

    for _ in range(BEEPS.get(name, 0)):
        winsound.Beep(1046 if name == "DONE" else 880, 450)
