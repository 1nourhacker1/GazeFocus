"""When did the user last type or use the mouse? (spec §7.1)

Raw Input with RIDEV_INPUTSINK delivers *copies* of keyboard and mouse events to our hidden
window after the system has handled them, so it cannot add latency. It is never a hook.
Injected events (SendInput, e.g. our own focus nudge) arrive with hDevice == NULL and are ignored.

Mouse *buttons held* is read live with GetAsyncKeyState on every frame instead of being tracked
from events: a missed button-up (UAC prompt, secure desktop) must never freeze switching forever.
"""

from __future__ import annotations

import ctypes
import math
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from gazefocus.win import _api
from gazefocus.win.msgwindow import MessageWindow

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
RI_KEY_BREAK = 0x0001
USAGE_PAGE_GENERIC, USAGE_MOUSE, USAGE_KEYBOARD = 0x01, 0x02, 0x06
HEADER_SIZE = ctypes.sizeof(_api.RAWINPUTHEADER)
VK_MOUSE_BUTTONS = (0x01, 0x02, 0x04, 0x05, 0x06)  # left, right, middle, X1, X2
VK_ESCAPE = 0x1B


@dataclass(frozen=True)
class RawEvent:
    kind: str  # "key" or "mouse"
    injected: bool
    key_down: bool = False
    moved: bool = False
    button_flags: int = 0  # RI_MOUSE_* bits: buttons and wheel
    vkey: int = 0  # keyboard only: the virtual-key code


def parse_raw_input(buf: bytes) -> RawEvent | None:
    if len(buf) < HEADER_SIZE:
        return None
    header = _api.RAWINPUTHEADER.from_buffer_copy(buf[:HEADER_SIZE])
    injected = not header.hDevice
    body = buf[HEADER_SIZE:]
    if header.dwType == RIM_TYPEKEYBOARD and len(body) >= ctypes.sizeof(_api.RAWKEYBOARD):
        kb = _api.RAWKEYBOARD.from_buffer_copy(body[: ctypes.sizeof(_api.RAWKEYBOARD)])
        return RawEvent("key", injected, key_down=not (kb.Flags & RI_KEY_BREAK), vkey=kb.VKey)
    if header.dwType == RIM_TYPEMOUSE and len(body) >= ctypes.sizeof(_api.RAWMOUSE):
        m = _api.RAWMOUSE.from_buffer_copy(body[: ctypes.sizeof(_api.RAWMOUSE)])
        return RawEvent("mouse", injected, moved=bool(m.lLastX or m.lLastY), button_flags=m.usButtonFlags)
    return None


class InputTracker:
    """Pure bookkeeping of the last real key press and mouse activity.

    `on_key(vkey)` hears every real key-down (calibration's Esc). It only listens: the key still
    reaches the focused app.
    """

    def __init__(self, on_key: Callable[[int], None] | None = None) -> None:
        self.last_key_t: float | None = None
        self.last_mouse_t: float | None = None
        self.events = 0
        self.ignored = 0
        self.on_key = on_key

    def on_event(self, t: float, ev: RawEvent) -> None:
        self.events += 1
        if ev.injected:
            self.ignored += 1
            return
        if ev.kind == "key" and ev.key_down:
            self.last_key_t = t
            if self.on_key is not None:
                self.on_key(ev.vkey)
        elif ev.kind == "mouse" and (ev.moved or ev.button_flags):
            self.last_mouse_t = t

    def idle_s(self, now: float, which: str = "any") -> float:
        stamps = {"key": [self.last_key_t], "mouse": [self.last_mouse_t], "any": [self.last_key_t, self.last_mouse_t]}[which]
        known = [s for s in stamps if s is not None]
        return now - max(known) if known else math.inf


class InputWatcher:
    """Registers Raw Input on a MessageWindow and feeds an InputTracker."""

    def __init__(self, window: MessageWindow, tracker: InputTracker, clock: Callable[[], float] = time.perf_counter) -> None:
        self.window, self.tracker, self.clock = window, tracker, clock
        devices = (_api.RAWINPUTDEVICE * 2)(
            _api.RAWINPUTDEVICE(USAGE_PAGE_GENERIC, USAGE_KEYBOARD, RIDEV_INPUTSINK, window.hwnd),
            _api.RAWINPUTDEVICE(USAGE_PAGE_GENERIC, USAGE_MOUSE, RIDEV_INPUTSINK, window.hwnd),
        )
        if not _api.user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(_api.RAWINPUTDEVICE)):
            raise ctypes.WinError(ctypes.get_last_error())
        window.on(WM_INPUT, self._on_input)

    def _on_input(self, wparam: int, lparam: int) -> None:
        size = wintypes.UINT(0)
        handle = wintypes.HANDLE(lparam)
        _api.user32.GetRawInputData(handle, RID_INPUT, None, ctypes.byref(size), HEADER_SIZE)
        if size.value:
            buf = ctypes.create_string_buffer(size.value)
            if _api.user32.GetRawInputData(handle, RID_INPUT, buf, ctypes.byref(size), HEADER_SIZE) == size.value:
                ev = parse_raw_input(buf.raw)
                if ev is not None:
                    self.tracker.on_event(self.clock(), ev)
        return None  # DefWindowProc must still run for WM_INPUT

    def close(self) -> None:
        devices = (_api.RAWINPUTDEVICE * 2)(
            _api.RAWINPUTDEVICE(USAGE_PAGE_GENERIC, USAGE_KEYBOARD, RIDEV_REMOVE, None),
            _api.RAWINPUTDEVICE(USAGE_PAGE_GENERIC, USAGE_MOUSE, RIDEV_REMOVE, None),
        )
        _api.user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(_api.RAWINPUTDEVICE))


def buttons_down() -> bool:
    """Any mouse button physically held right now (live, never cached)."""
    return any(_api.user32.GetAsyncKeyState(vk) & 0x8000 for vk in VK_MOUSE_BUTTONS)
