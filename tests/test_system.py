import pytest

from gazefocus.win.msgwindow import MessageWindow, pump_messages
from gazefocus.win.system import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMSUSPEND,
    WM_DISPLAYCHANGE,
    WM_HOTKEY,
    WM_POWERBROADCAST,
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
    Hotkey,
    SingleInstance,
    SystemEvents,
    fullscreen_busy,
    on_battery,
    parse_hotkey,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Ctrl+Alt+G", (MOD_CONTROL | MOD_ALT, ord("G"))),
        ("alt + shift + 7", (MOD_ALT | MOD_SHIFT, ord("7"))),
        ("Ctrl+F24", (MOD_CONTROL, 0x87)),
    ],
)
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["G", "Ctrl+Alt", "Ctrl+Banana", "Ctrl+G+H", "Ctrl+F25"])
def test_parse_hotkey_rejects(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)


def test_single_instance_blocks_a_second_copy():
    first = SingleInstance("Local\\GazeFocus-test-single")
    second = SingleInstance("Local\\GazeFocus-test-single")
    try:
        assert first.acquired is True and second.acquired is False
    finally:
        second.close()
        first.close()
    third = SingleInstance("Local\\GazeFocus-test-single")
    assert third.acquired is True
    third.close()


def test_state_queries_return_bools():
    assert fullscreen_busy() in (True, False)
    assert on_battery() in (True, False)


def test_hotkey_registers_and_dispatches_its_id():
    win = MessageWindow()
    pressed = []
    hk = Hotkey(win, "Ctrl+Alt+Shift+F24", lambda: pressed.append(1), hotkey_id=7)
    try:
        assert hk.registered
        win.post(WM_HOTKEY, 8)  # another hotkey id: ignored
        win.post(WM_HOTKEY, 7)
        pump_messages(0.2)
    finally:
        hk.close()
        win.close()
    assert pressed == [1]


def test_system_events_dispatch():
    win = MessageWindow()
    seen = []
    ev = SystemEvents(
        win,
        on_lock=lambda: seen.append("lock"),
        on_unlock=lambda: seen.append("unlock"),
        on_suspend=lambda: seen.append("suspend"),
        on_resume=lambda: seen.append("resume"),
        on_display_change=lambda: seen.append("display"),
    )
    try:
        win.post(WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK)
        win.post(WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK)
        win.post(WM_POWERBROADCAST, PBT_APMSUSPEND)
        win.post(WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC)
        win.post(WM_DISPLAYCHANGE)
        pump_messages(0.2)
    finally:
        ev.close()
        win.close()
    assert seen == ["lock", "unlock", "suspend", "resume", "display"]
