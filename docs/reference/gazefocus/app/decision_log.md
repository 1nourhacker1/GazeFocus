# gazefocus/app/decision_log.py
Verified against: GazeFocus@b322e17 · 2026-09-29

`setup_logging(%APPDATA%\GazeFocus\logs)` writes `gazefocus.log` (and stderr) plus `decisions.log`, each rotating at 5 × 1 MB.

`DecisionLogger` writes one line per decision that matters, never 15 a second:
- `zone=LG margin=-0.82 -> SWITCH LG`
- `zone=LG margin=-0.80 -> BLOCKED(typing 0.4s)`: logged once per run of the same `reason_category`
- `   focused 'Notepad' on LG via direct in 12 ms`, or `   FAIL 'Task Manager' on LG: refused … (510 ms)`
- `   <note>`, e.g. "no window to focus on LG"
