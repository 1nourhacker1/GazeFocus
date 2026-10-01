# gazefocus/win/camera_usage.py
Verified against: GazeFocus@bf7feda · 2026-09-29

Reads `HKCU\…\CapabilityAccessManager\ConsentStore\webcam`.
- Packaged apps are direct subkeys. Classic apps are under `NonPackaged`, with `#` standing in for `\`.
- An app counts as "using" the camera when `LastUsedTimeStart > 0` and `LastUsedTimeStop == 0`.
- **Only a hint.** Records go stale when an app crashes, so it's consulted only after `CameraSource.open()` fails, and the message says "Possibly".
- `exclude=` drops our own interpreter paths, so a stale record from our own crash isn't reported.
- M0-D results: the M0 spike notes (not published).
- Unreadable subkeys are skipped. The 'nobody reported' message suggests another GazeFocus command may hold the camera.
