# gazefocus/app/decision_log.py
Verified against: GazeFocus@b887938 · 2026-10-01

`setup_logging(%APPDATA%\GazeFocus\logs)` writes `gazefocus.log` (and stderr) plus `decisions.log`, each rotating at 5 × 1 MB.

`DecisionLogger` writes one line per decision that matters, never 15 a second:
- `zone=EXTERNAL margin=-0.82 -> SWITCH EXTERNAL`
- `zone=EXTERNAL margin=-0.80 -> BLOCKED(typing 0.4s)`: logged once per run of the same `reason_category`
- `   focused 'Notepad' on EXTERNAL via direct in 12 ms`, or `   FAIL 'Task Manager' on EXTERNAL: refused … (510 ms)`
- `   <note>`, e.g. "no window to focus on external monitor"
