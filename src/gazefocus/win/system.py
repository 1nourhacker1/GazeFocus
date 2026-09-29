"""Single instance, global hotkey, fullscreen/battery state, and lock/sleep/display events (spec §7.4)."""

from __future__ import annotations

import ctypes
from typing import Callable

from gazefocus.win import _api
from gazefocus.win.msgwindow import MessageWindow

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
WM_HOTKEY = 0x0312
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK, WTS_SESSION_UNLOCK = 0x7, 0x8
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND, PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC = 0x4, 0x7, 0x12
WM_DISPLAYCHANGE = 0x007E
NOTIFY_FOR_THIS_SESSION = 0
DEVICE_NOTIFY_WINDOW_HANDLE = 0
ERROR_ALREADY_EXISTS = 183
QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE = 2, 3, 4

_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+G' -> (MOD_CONTROL | MOD_ALT, ord('G')). At least one modifier is required."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    mods, key = 0, None
    for p in parts:
        if p in _MODIFIERS:
            mods |= _MODIFIERS[p]
        elif key is None and len(p) == 1 and p.isalnum():
            key = ord(p.upper())
        elif key is None and p[0] == "f" and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            key = 0x70 + int(p[1:]) - 1
        else:
            raise ValueError(f"cannot parse hotkey {text!r}: unexpected {p!r}")
    if key is None or not mods:
        raise ValueError(f"hotkey {text!r} needs at least one modifier and one key, e.g. Ctrl+Alt+G")
    return mods, key


class Hotkey:
    def __init__(self, window: MessageWindow, text: str, on_press: Callable[[], None], hotkey_id: int = 1) -> None:
        mods, vk = parse_hotkey(text)
        self.window, self.hotkey_id = window, hotkey_id
        self.registered = bool(_api.user32.RegisterHotKey(window.hwnd, hotkey_id, mods | MOD_NOREPEAT, vk))
        window.on(WM_HOTKEY, lambda w, l: (on_press() if w == hotkey_id else None) or 0)

    def close(self) -> None:
        if self.registered:
            _api.user32.UnregisterHotKey(self.window.hwnd, self.hotkey_id)
            self.registered = False


class SingleInstance:
    def __init__(self, name: str = "Local\\GazeFocus") -> None:
        self._handle = _api.kernel32.CreateMutexW(None, False, name)
        self.acquired = bool(self._handle) and ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle:
            _api.kernel32.CloseHandle(self._handle)
            self._handle = None


def fullscreen_busy() -> bool:
    """A fullscreen game, a presentation, or "busy" (spec §4.1 freeze)."""
    state = ctypes.c_int(0)
    if _api.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE)


def on_battery() -> bool:
    status = _api.SYSTEM_POWER_STATUS()
    if not _api.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False
    return status.ACLineStatus == 0


class SystemEvents:
    """Session lock/unlock, suspend/resume and display changes, delivered on the MessageWindow."""

    def __init__(
        self,
        window: MessageWindow,
        *,
        on_lock: Callable[[], None],
        on_unlock: Callable[[], None],
        on_suspend: Callable[[], None],
        on_resume: Callable[[], None],
        on_display_change: Callable[[], None],
    ) -> None:
        self.window = window
        self._session = bool(_api.wtsapi32.WTSRegisterSessionNotification(window.hwnd, NOTIFY_FOR_THIS_SESSION))
        self._power = _api.user32.RegisterSuspendResumeNotification(window.hwnd, DEVICE_NOTIFY_WINDOW_HANDLE)
        session = {WTS_SESSION_LOCK: on_lock, WTS_SESSION_UNLOCK: on_unlock}
        power = {PBT_APMSUSPEND: on_suspend, PBT_APMRESUMESUSPEND: on_resume, PBT_APMRESUMEAUTOMATIC: on_resume}

        def session_change(w, l):
            if w in session:
                session[w]()
            return 0

        def power_change(w, l):
            if w in power:
                power[w]()
            return 1  # TRUE: never veto

        window.on(WM_WTSSESSION_CHANGE, session_change)
        window.on(WM_POWERBROADCAST, power_change)
        window.on(WM_DISPLAYCHANGE, lambda w, l: on_display_change() or 0)

    def close(self) -> None:
        if self._session:
            _api.wtsapi32.WTSUnRegisterSessionNotification(self.window.hwnd)
            self._session = False
        if self._power:
            _api.user32.UnregisterSuspendResumeNotification(self._power)
            self._power = None
