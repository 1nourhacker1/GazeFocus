"""Monitor enumeration (physical pixels, per-monitor DPI v2) and a stable layout fingerprint."""

from __future__ import annotations

import ctypes
import hashlib
from ctypes import wintypes
from dataclasses import dataclass
from typing import Sequence

MONITORINFOF_PRIMARY = 1
EDD_GET_DEVICE_INTERFACE_NAME = 1
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4


@dataclass(frozen=True)
class MonitorInfo:
    device: str  # e.g. \\.\DISPLAY1 (can change between boots)
    id: str  # device interface path (stable); falls back to `device`
    rect: tuple[int, int, int, int]  # left, top, right, bottom
    work: tuple[int, int, int, int]
    primary: bool


def layout_fingerprint(monitors: Sequence[MonitorInfo]) -> str:
    key = sorted((m.id, tuple(m.rect), m.primary) for m in monitors)
    return hashlib.sha1(repr(key).encode("utf-8")).hexdigest()[:16]


def zone_monitors(monitors: Sequence[MonitorInfo], laptop: str = "primary") -> dict[str, str | None]:
    lap = next((m for m in monitors if (m.primary if laptop == "primary" else m.device == laptop)), None)
    others = [m for m in monitors if m is not lap]
    return {"LAPTOP": lap.id if lap else None, "EXTERNAL": others[0].id if len(others) == 1 else None}


def ensure_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
    except (AttributeError, OSError):
        pass  # already set (e.g. by Qt) or unavailable


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class _DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)


def _monitor_id(device: str) -> str:
    dd = _DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(dd)
    if ctypes.windll.user32.EnumDisplayDevicesW(device, 0, ctypes.byref(dd), EDD_GET_DEVICE_INTERFACE_NAME):
        return dd.DeviceID or device
    return device


def enumerate_monitors() -> list[MonitorInfo]:
    ensure_dpi_awareness()
    user32 = ctypes.windll.user32
    found: list[MonitorInfo] = []

    def on_monitor(hmon, _hdc, _rect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r, w = info.rcMonitor, info.rcWork
            found.append(
                MonitorInfo(
                    device=info.szDevice,
                    id=_monitor_id(info.szDevice),
                    rect=(r.left, r.top, r.right, r.bottom),
                    work=(w.left, w.top, w.right, w.bottom),
                    primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
        return True

    callback = _MONITORENUMPROC(on_monitor)  # keep a reference for the duration of the call
    user32.EnumDisplayMonitors(None, None, callback, 0)
    return found
