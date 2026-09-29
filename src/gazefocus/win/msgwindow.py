"""A hidden top-level window whose messages are dispatched by whatever pump runs on its thread.

GazeFocus runs Qt's event loop on the main thread; Qt's Windows dispatcher calls DispatchMessage
for every message of the thread, so this window's WNDPROC runs inside that loop (verified while
planning). It is a hidden *top-level* window, not HWND_MESSAGE, because message-only windows
never receive broadcasts such as WM_DISPLAYCHANGE.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes
from typing import Callable

from gazefocus.win import _api

CLASS_NAME = "GazeFocusMessageWindow"
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
ERROR_CLASS_ALREADY_EXISTS = 1410
PM_REMOVE = 0x0001

Handler = Callable[[int, int], "int | None"]
_windows: dict[int, "MessageWindow"] = {}
_class_registered = False
log = logging.getLogger("gazefocus")


@_api.WNDPROC
def _wndproc(hwnd, msg, wparam, lparam):
    win = _windows.get(hwnd)
    if win is not None:
        handler = win._handlers.get(msg)
        if handler is not None:
            try:
                result = handler(wparam, lparam)
            except Exception:  # a broken handler must never take the message loop down
                log.exception("handler for message 0x%04x failed", msg)
                result = None
            if result is not None:
                return result
    return _api.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _ensure_class() -> None:
    global _class_registered
    if _class_registered:
        return
    wc = _api.WNDCLASSW()
    wc.lpfnWndProc = _wndproc
    wc.hInstance = _api.kernel32.GetModuleHandleW(None)
    wc.lpszClassName = CLASS_NAME
    if not _api.user32.RegisterClassW(ctypes.byref(wc)):
        err = ctypes.get_last_error()
        if err != ERROR_CLASS_ALREADY_EXISTS:
            raise ctypes.WinError(err)
    _class_registered = True


class MessageWindow:
    def __init__(self, title: str = "GazeFocus") -> None:
        _ensure_class()
        hwnd = _api.user32.CreateWindowExW(
            WS_EX_TOOLWINDOW, CLASS_NAME, title, WS_POPUP, 0, 0, 0, 0,
            None, None, _api.kernel32.GetModuleHandleW(None), None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd: int = hwnd
        self._handlers: dict[int, Handler] = {}
        _windows[hwnd] = self

    def on(self, msg: int, handler: Handler) -> None:
        """handler(wparam, lparam) -> LRESULT, or None to fall through to DefWindowProc."""
        self._handlers[msg] = handler

    def post(self, msg: int, wparam: int = 0, lparam: int = 0) -> bool:
        return bool(_api.user32.PostMessageW(self.hwnd, msg, wparam, lparam))

    def close(self) -> None:
        if self.hwnd:
            _windows.pop(self.hwnd, None)
            _api.user32.DestroyWindow(self.hwnd)
            self.hwnd = 0


def pump_messages(seconds: float) -> None:
    """A bare Win32 message pump for tests and CLI diagnostics (the app uses Qt's loop)."""
    msg = wintypes.MSG()
    end = time.perf_counter() + seconds
    while True:
        while _api.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            _api.user32.TranslateMessage(ctypes.byref(msg))
            _api.user32.DispatchMessageW(ctypes.byref(msg))
        if time.perf_counter() >= end:
            return
        time.sleep(0.005)
