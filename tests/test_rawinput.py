import math

from gazefocus.win import _api
from gazefocus.win.focus import nudge_input
from gazefocus.win.msgwindow import MessageWindow, pump_messages
from gazefocus.win.rawinput import (
    RI_KEY_BREAK,
    RIM_TYPEKEYBOARD,
    RIM_TYPEMOUSE,
    VK_ESCAPE,
    InputTracker,
    InputWatcher,
    RawEvent,
    buttons_down,
    parse_raw_input,
)


def raw(kind, device, body):
    size = _api.ctypes.sizeof(_api.RAWINPUTHEADER) + _api.ctypes.sizeof(body)
    return bytes(_api.RAWINPUTHEADER(dwType=kind, dwSize=size, hDevice=device, wParam=0)) + bytes(body)


def test_parse_key_down_and_up():
    down = parse_raw_input(raw(RIM_TYPEKEYBOARD, 0x1234, _api.RAWKEYBOARD(VKey=0x41, Flags=0)))
    up = parse_raw_input(raw(RIM_TYPEKEYBOARD, 0x1234, _api.RAWKEYBOARD(VKey=0x41, Flags=RI_KEY_BREAK)))
    assert down == RawEvent("key", injected=False, key_down=True, vkey=0x41)
    assert up == RawEvent("key", injected=False, key_down=False, vkey=0x41)


def test_parse_mouse_move_and_injected_flag():
    ev = parse_raw_input(raw(RIM_TYPEMOUSE, None, _api.RAWMOUSE(lLastX=3, lLastY=0)))
    assert ev.kind == "mouse" and ev.moved and ev.injected


def test_parse_rejects_short_or_unknown_buffers():
    assert parse_raw_input(b"\x00" * 4) is None
    assert parse_raw_input(raw(2, 0x1, _api.RAWKEYBOARD())) is None  # RIM_TYPEHID


def test_tracker_ignores_injected_and_key_releases():
    t = InputTracker()
    t.on_event(1.0, RawEvent("mouse", injected=True, moved=True))
    t.on_event(2.0, RawEvent("key", injected=False, key_down=False))
    assert t.last_mouse_t is None and t.last_key_t is None and t.ignored == 1
    t.on_event(3.0, RawEvent("key", injected=False, key_down=True))
    t.on_event(4.0, RawEvent("mouse", injected=False, button_flags=0x0400))  # wheel counts as mouse use
    assert (t.last_key_t, t.last_mouse_t) == (3.0, 4.0)


def test_tracker_reports_real_key_downs_to_on_key():
    keys = []
    t = InputTracker(on_key=keys.append)
    t.on_event(1.0, RawEvent("key", injected=False, key_down=True, vkey=VK_ESCAPE))
    t.on_event(1.1, RawEvent("key", injected=False, key_down=False, vkey=VK_ESCAPE))  # the release
    t.on_event(1.2, RawEvent("mouse", injected=False, moved=True))
    assert keys == [VK_ESCAPE]


def test_tracker_ignores_an_injected_escape():
    keys = []
    t = InputTracker(on_key=keys.append)
    t.on_event(1.0, RawEvent("key", injected=True, key_down=True, vkey=VK_ESCAPE))
    assert keys == [] and t.last_key_t is None


def test_idle_seconds():
    t = InputTracker()
    assert t.idle_s(10.0) == math.inf
    t.on_event(4.0, RawEvent("key", injected=False, key_down=True))
    t.on_event(7.0, RawEvent("mouse", injected=False, moved=True))
    assert (t.idle_s(10.0, "key"), t.idle_s(10.0, "mouse"), t.idle_s(10.0)) == (6.0, 3.0, 3.0)


def test_live_raw_input_sees_our_nudge_as_injected():
    win = MessageWindow()
    tracker = InputTracker()
    watcher = InputWatcher(win, tracker)
    try:
        nudge_input()
        pump_messages(0.3)
    finally:
        watcher.close()
        win.close()
    assert tracker.ignored >= 1  # the zero-motion SendInput came back flagged as injected


def test_buttons_down_is_a_live_bool():
    assert buttons_down() in (True, False)
