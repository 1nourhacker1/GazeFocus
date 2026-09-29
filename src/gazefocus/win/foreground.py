"""Most-recently-used window per monitor, and who moved focus (spec §7.2).

ForegroundHook is an out-of-context WinEvent hook: Windows queues the event to our thread and
Qt's loop delivers it, so nothing runs inside other processes. Our own windows are skipped
(WINEVENT_SKIPOWNPROCESS), so GazeFocus UI never enters the MRU lists.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Callable

from gazefocus.win import _api

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OURS_WINDOW_S = 0.3
MRU_LIMIT = 20
log = logging.getLogger("gazefocus")


class MruTracker:
    """Pure: MRU windows per monitor device; a change GazeFocus did not announce is manual."""

    def __init__(self, ours_window_s: float = OURS_WINDOW_S) -> None:
        self.ours_window_s = ours_window_s
        self._order: dict[str, list[int]] = {}
        self._expected: tuple[int, float] | None = None
        self.last_manual_t: float | None = None
        self.last_app_window: int | None = None

    def expect(self, hwnd: int, t: float) -> None:
        """GazeFocus is about to focus `hwnd`; its foreground event must not count as manual."""
        self._expected = (hwnd, t)

    def on_foreground(self, t: float, hwnd: int, device: str | None, is_target: bool = True) -> bool:
        """Record a foreground change; returns True when it was ours."""
        ours = self._expected is not None and self._expected[0] == hwnd and t - self._expected[1] <= self.ours_window_s
        if ours:
            self._expected = None
        else:
            self.last_manual_t = t
        if is_target and device is not None:
            self.forget(hwnd)  # it may have moved to another monitor
            lst = self._order.setdefault(device, [])
            lst.insert(0, hwnd)
            del lst[MRU_LIMIT:]
            self.last_app_window = hwnd
        return ours

    def order(self, device: str) -> list[int]:
        return list(self._order.get(device, []))

    def forget(self, hwnd: int) -> None:
        for lst in self._order.values():
            if hwnd in lst:
                lst.remove(hwnd)


class ForegroundHook:
    def __init__(self, on_change: Callable[[int], None]) -> None:
        self._on_change = on_change
        self._proc = _api.WINEVENTPROC(self._callback)  # keep a reference for the hook's lifetime
        self._hook = _api.user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._proc, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def _callback(self, hook, event, hwnd, id_object, id_child, thread, ms) -> None:
        if hwnd:
            try:
                self._on_change(hwnd)
            except Exception:
                log.exception("foreground handler failed")

    def close(self) -> None:
        if self._hook:
            _api.user32.UnhookWinEvent(self._hook)
            self._hook = None
