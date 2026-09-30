"""What is behind the dock, without the dock (spec §8.5, M0-C2), plus the dock's window styles and vsync.

`exclude_from_capture` sets WDA_EXCLUDEFROMCAPTURE: every capture API, GDI included, then sees
straight through the window (M0-C2: 12,248 red test pixels captured before, 0 after). The dock can
therefore grab the screen under itself and render its own glass from it.
"""

from __future__ import annotations

import ctypes

import numpy as np

from gazefocus.win import _api

WDA_EXCLUDEFROMCAPTURE = 0x11
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x08000000, 0x00000080, 0x00000008
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010


class Grabber:
    """The screen's pixels in a fixed-size rect (physical px), through one reusable DIB section.

    A grab costs 4-6 ms whatever the size (M0-C2), so the dock grabs a few times a second at most.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self._screen = _api.user32.GetDC(None)
        self._mem = _api.gdi32.CreateCompatibleDC(self._screen)
        bits = ctypes.c_void_p()
        bmi = _api.BITMAPINFOHEADER(ctypes.sizeof(_api.BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        self._bitmap = _api.gdi32.CreateDIBSection(self._screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        self._old = _api.gdi32.SelectObject(self._mem, self._bitmap)
        self._view = np.ctypeslib.as_array((ctypes.c_uint8 * (w * h * 4)).from_address(bits.value)).reshape(h, w, 4)

    def grab(self, x: int, y: int) -> np.ndarray:
        """A BGR copy (h x w x 3) of the screen at (x, y); the dock itself is excluded from it."""
        _api.gdi32.BitBlt(self._mem, 0, 0, self.w, self.h, self._screen, x, y, SRCCOPY | CAPTUREBLT)
        return self._view[..., :3].copy()

    def close(self) -> None:
        if self._mem:
            _api.gdi32.SelectObject(self._mem, self._old)
            _api.gdi32.DeleteObject(self._bitmap)
            _api.gdi32.DeleteDC(self._mem)
            _api.user32.ReleaseDC(None, self._screen)
            self._mem = None


def exclude_from_capture(hwnd: int) -> bool:
    return bool(_api.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


def make_noactivate(hwnd: int) -> None:
    """The dock must never become the foreground window (spec §8.5)."""
    ex = _api.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    _api.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def keep_on_top(hwnd: int) -> bool:
    """Lift a topmost window above the topmost windows shown after it (the dock above the calibration overlay)."""
    return bool(_api.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


def dwm_flush() -> None:
    """Block until the desktop compositor's next frame: the display's refresh (240 Hz on this laptop)."""
    _api.dwmapi.DwmFlush()
