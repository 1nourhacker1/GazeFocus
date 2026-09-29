"""Bring a window to the foreground from a process that has no focus of its own (spec §7.3).

1. Nudge: SendInput one zero-motion mouse move, so our process "received the last input event"
   (the PowerToys FancyZones trick); Raw Input sees it with hDevice == NULL and ignores it.
2. SetForegroundWindow, then confirm within 50 ms.
3. Fallback on a worker thread: AttachThreadInput to the foreground thread, BringWindowToTop +
   SetForegroundWindow, detach. The worker is abandoned after 500 ms because AttachThreadInput
   can deadlock against a hung foreground thread.
4. Give up: the caller logs one FAIL and does not retry (elevated windows end up here).
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

from gazefocus.win import _api

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
PM_NOREMOVE = 0x0000


@dataclass(frozen=True)
class SwitchResult:
    ok: bool
    method: str  # "already", "direct", "attach", "failed", "none"
    ms: float
    detail: str = ""


def nudge_input() -> bool:
    inp = _api.INPUT(type=INPUT_MOUSE)
    inp.mi = _api.MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MOVE, 0, 0)
    return _api.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_api.INPUT)) == 1


def is_foreground(hwnd: int) -> bool:
    return bool(hwnd) and _api.user32.GetForegroundWindow() == hwnd


def _wait_for(hwnd: int, seconds: float) -> bool:
    end = time.perf_counter() + seconds
    while True:
        if is_foreground(hwnd):
            return True
        if time.perf_counter() >= end:
            return False
        time.sleep(0.005)


def _attach_and_raise(hwnd: int, done: threading.Event) -> None:
    u, k = _api.user32, _api.kernel32
    try:
        msg = wintypes.MSG()
        u.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)  # a thread needs a queue to attach
        me = k.GetCurrentThreadId()
        fg_thread = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        attached = bool(fg_thread and fg_thread != me and u.AttachThreadInput(me, fg_thread, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(me, fg_thread, False)
    finally:
        done.set()


def bring_to_front(hwnd: int, *, direct_wait_s: float = 0.05, fallback_timeout_s: float = 0.5) -> SwitchResult:
    t0 = time.perf_counter()

    def result(ok: bool, method: str, detail: str = "") -> SwitchResult:
        return SwitchResult(ok, method, (time.perf_counter() - t0) * 1000.0, detail)

    if not hwnd or not _api.user32.IsWindow(hwnd):
        return result(False, "none", "window is gone")
    if is_foreground(hwnd):
        return result(True, "already")
    nudge_input()
    if _api.user32.SetForegroundWindow(hwnd) and _wait_for(hwnd, direct_wait_s):
        return result(True, "direct")
    done = threading.Event()
    threading.Thread(target=_attach_and_raise, args=(hwnd, done), name="gazefocus-attach", daemon=True).start()
    finished = done.wait(fallback_timeout_s)
    if _wait_for(hwnd, 0.05):
        return result(True, "attach")
    detail = "refused (elevated window or focus lock)" if finished else "fallback timed out (hung window?)"
    return result(False, "failed", detail)


def clamp_point(p: tuple[int, int], rect: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = rect
    return min(max(p[0], left), right - 1), min(max(p[1], top), bottom - 1)


def window_center(hwnd: int) -> tuple[int, int] | None:
    r = wintypes.RECT()
    if not _api.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def cursor_pos() -> tuple[int, int]:
    p = wintypes.POINT()
    _api.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def warp_cursor(p: tuple[int, int]) -> bool:
    return bool(_api.user32.SetCursorPos(int(p[0]), int(p[1])))
