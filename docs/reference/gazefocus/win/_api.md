# gazefocus/win/_api.py
Verified against: GazeFocus@5177339 · 2026-09-30

The **only** place Win32 prototypes are declared.
- Private `ctypes.WinDLL(..., use_last_error=True)` instances for `user32`, `kernel32`, `dwmapi`, `shell32` and `wtsapi32`. Setting `argtypes` here never clashes with other modules' `ctypes.windll`.
- Structs: `WNDCLASSW`, `MONITORINFOEXW`, `INPUT`/`MOUSEINPUT` (sizeof(INPUT) = 40 on x64), `RAWINPUTDEVICE`, `RAWINPUTHEADER` (24 bytes), `RAWMOUSE` (24; with a pad field for the 4-byte-aligned union), `RAWKEYBOARD` (16) and `SYSTEM_POWER_STATUS`.
- Callback types: `WNDPROC`, `WNDENUMPROC` and `WINEVENTPROC`.
- Adding a Win32 call means adding its prototype here first.
- Plan 3: `gdi32` and `BITMAPINFOHEADER`; `SetWindowLongPtrW`, `SetWindowDisplayAffinity`, `IsZoomed`, `GetDC`/`ReleaseDC`, the DIB and `BitBlt` calls, and `DwmFlush` (for `win/capture.py`).
- Plan 4: `SetWindowPos` (for `capture.keep_on_top`).
