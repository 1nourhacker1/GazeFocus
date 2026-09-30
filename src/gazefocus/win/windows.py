"""Which top-level windows may receive focus, and which one to pick on a monitor (spec §4.2).

`window_facts` never sends a message to the other window (InternalGetWindowText, not
GetWindowText), so a hung application cannot block GazeFocus.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Sequence

from gazefocus.win import _api

SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
DWMWA_CLOAKED = 14
GA_ROOT = 2
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2


@dataclass(frozen=True)
class WindowFacts:
    hwnd: int
    exists: bool
    visible: bool = False
    minimized: bool = False
    cloaked: bool = False  # hidden by DWM: on another virtual desktop, or a suspended UWP app
    hung: bool = False
    tool_window: bool = False
    own_process: bool = False
    top_level: bool = True
    class_name: str = ""
    title: str = ""
    device: str | None = None  # monitor device name (e.g. \\.\DISPLAY5), None when off-screen


def is_switch_target(f: WindowFacts) -> tuple[bool, str]:
    """(ok, reason). Cloaked covers "on another virtual desktop", so no COM call is needed."""
    checks = (
        (not f.exists, "gone"),
        (not f.visible, "hidden"),
        (f.minimized, "minimized"),
        (f.cloaked, "cloaked"),
        (f.hung, "not responding"),
        (f.own_process, "GazeFocus itself"),
        (f.class_name in SHELL_CLASSES, "shell"),
        (not f.top_level, "not top-level"),
        (f.tool_window, "tool window"),
        (f.device is None, "off-screen"),
    )
    for failed, reason in checks:
        if failed:
            return False, reason
    return True, "ok"


def device_of_monitor(hmon) -> str | None:
    if not hmon:
        return None
    info = _api.MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    if not _api.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    return info.szDevice


def device_of_window(hwnd: int) -> str | None:
    return device_of_monitor(_api.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL))


def device_of_point(x: int, y: int) -> str | None:
    return device_of_monitor(_api.user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST))


def window_facts(hwnd: int, own_pid: int | None = None) -> WindowFacts:
    u = _api.user32
    if not hwnd or not u.IsWindow(hwnd):
        return WindowFacts(hwnd=hwnd or 0, exists=False)
    pid = wintypes.DWORD(0)
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    cloaked = wintypes.DWORD(0)
    _api.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    ex_style = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    cls = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, cls, 256)
    title = ctypes.create_unicode_buffer(256)
    u.InternalGetWindowText(hwnd, title, 256)
    return WindowFacts(
        hwnd=hwnd,
        exists=True,
        visible=bool(u.IsWindowVisible(hwnd)),
        minimized=bool(u.IsIconic(hwnd)),
        cloaked=bool(cloaked.value),
        hung=bool(u.IsHungAppWindow(hwnd)),
        tool_window=bool(ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW),
        own_process=pid.value == (own_pid if own_pid is not None else _api.kernel32.GetCurrentProcessId()),
        top_level=u.GetAncestor(hwnd, GA_ROOT) == hwnd,
        class_name=cls.value,
        title=title.value,
        device=device_of_window(hwnd),
    )


def top_level_windows() -> list[int]:
    """All top-level windows in Z-order, topmost first."""
    found: list[int] = []

    def collect(hwnd, _lparam):
        found.append(hwnd)
        return True

    _api.user32.EnumWindows(_api.WNDENUMPROC(collect), 0)
    return found


def choose_target(
    device: str,
    mru: Sequence[int],
    facts: Callable[[int], WindowFacts],
    zorder: Callable[[], Sequence[int]],
) -> int | None:
    """The most recently used valid window on `device`; else the topmost valid one there."""
    seen: set[int] = set()
    for source in (mru, None):
        for hwnd in (source if source is not None else zorder()):
            if hwnd in seen:
                continue
            seen.add(hwnd)
            f = facts(hwnd)
            if f.device == device and is_switch_target(f)[0]:
                return hwnd
    return None


def covers(rect: tuple[int, int, int, int], monitor: tuple[int, int, int, int]) -> bool:
    return rect[0] <= monitor[0] and rect[1] <= monitor[1] and rect[2] >= monitor[2] and rect[3] >= monitor[3]


def is_fullscreen(f: WindowFacts, rect: tuple[int, int, int, int], monitor: tuple[int, int, int, int],
                  device: str, zoomed: bool) -> bool:
    """A game, a video, a presentation or F11 covering `device`. Maximized windows don't count:
    with an auto-hiding taskbar they cover the whole monitor too."""
    if not f.exists or f.own_process or f.class_name in SHELL_CLASSES or f.device != device or zoomed:
        return False
    return covers(rect, monitor)


def fullscreen_app_on(device: str, monitor: tuple[int, int, int, int]) -> bool:
    hwnd = _api.user32.GetForegroundWindow() or 0
    f = window_facts(hwnd)
    r = wintypes.RECT()
    if not f.exists or not _api.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    return is_fullscreen(f, (r.left, r.top, r.right, r.bottom), monitor, device, bool(_api.user32.IsZoomed(hwnd)))
