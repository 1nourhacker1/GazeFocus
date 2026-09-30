# gazefocus/dock/ticker.py
Verified against: GazeFocus@03c76d8 · 2026-09-30

`VBlankTicker`: the dock's frame clock.
- Qt's animation timer runs at 60 Hz, which looked choppy on this 240 Hz laptop (the user, M0-C2).
- A daemon thread waits on `DwmFlush` while `start()`ed, and emits `tick` to the Qt thread.
- It never queues a second tick before the handler calls `handled()`, so a slow frame can't pile up a backlog.
- If the compositor returns at once (nothing to compose), it sleeps 2 ms instead of spinning.
- `stop()` idles the thread; `close()` ends it. The `wait` function can be injected, and tests use a sleep.
