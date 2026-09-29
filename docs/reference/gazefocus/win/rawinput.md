# gazefocus/win/rawinput.py
Verified against: GazeFocus@a48a5b3 · 2026-09-29

- **Raw Input, never a hook.**
  - `InputWatcher` registers the keyboard (usage 6) and mouse (usage 2) with `RIDEV_INPUTSINK` on the MessageWindow.
  - `WM_INPUT` delivers copies *after* the system has handled the input, so it adds no latency.
  - `GetRawInputData(RID_INPUT)` feeds `parse_raw_input`.
- **Injected input** (`hDevice == NULL`, i.e. `SendInput`, including our own focus nudge) is counted in `.ignored` and never counts as the user.
- `InputTracker.last_key_t` updates on every key *down* (repeats and modifiers included; spec §4.1 "every key counts"). `last_mouse_t` updates on movement, buttons or the wheel.
- **Buttons held:** `buttons_down()` reads `GetAsyncKeyState` for left, right, middle, X1 and X2 **live on every frame**. Nothing is cached, so a missed button-up (a UAC prompt, the secure desktop) can't freeze switching.
- Struct sizes (x64): header 24, RAWMOUSE 24, RAWKEYBOARD 16.
