import pytest

from gazefocus.win import _api
from gazefocus.win.msgwindow import MessageWindow
from gazefocus.win.windows import WindowFacts, choose_target, is_switch_target, top_level_windows, window_facts

LG, LAP = r"\\.\DISPLAY5", r"\\.\DISPLAY1"


def good(hwnd, device=LG, **kw):
    fields = {"exists": True, "visible": True, "class_name": "Chrome_WidgetWin_1", "device": device, **kw}
    return WindowFacts(hwnd=hwnd, **fields)


@pytest.mark.parametrize(
    "facts,reason",
    [
        (WindowFacts(1, exists=False), "gone"),
        (good(1, visible=False), "hidden"),
        (good(1, minimized=True), "minimized"),
        (good(1, cloaked=True), "cloaked"),
        (good(1, hung=True), "not responding"),
        (good(1, own_process=True), "GazeFocus itself"),
        (WindowFacts(1, True, visible=True, class_name="Shell_TrayWnd", device=LAP), "shell"),
        (good(1, top_level=False), "not top-level"),
        (good(1, tool_window=True), "tool window"),
        (good(1, device=None), "off-screen"),
    ],
)
def test_invalid_targets_say_why(facts, reason):
    assert is_switch_target(facts) == (False, reason)


def test_a_normal_window_is_a_target():
    assert is_switch_target(good(1)) == (True, "ok")


def test_choose_prefers_most_recent_valid_window_on_the_monitor():
    table = {1: good(1, device=LAP), 2: good(2, minimized=True), 3: good(3), 4: good(4)}
    assert choose_target(LG, [1, 2, 3, 4], table.__getitem__, lambda: []) == 3


def test_choose_falls_back_to_zorder_when_mru_has_nothing():  # Review Focus #3: MRU window closed
    table = {9: WindowFacts(9, exists=False), 5: good(5, device=LAP), 6: good(6)}
    assert choose_target(LG, [9], table.__getitem__, lambda: [5, 6]) == 6


def test_choose_returns_none_for_an_empty_monitor():
    table = {5: good(5, device=LAP)}
    assert choose_target(LG, [], table.__getitem__, lambda: [5]) is None


def test_live_desktop_has_windows_and_our_window_is_never_a_target():
    assert len(top_level_windows()) > 0
    win = MessageWindow()
    try:
        f = window_facts(win.hwnd)
    finally:
        win.close()
    assert f.exists and f.own_process and f.tool_window
    assert is_switch_target(f)[0] is False


def test_facts_of_a_dead_handle():
    assert window_facts(0).exists is False
    win = MessageWindow()
    hwnd = win.hwnd
    win.close()
    assert window_facts(hwnd).exists is False


def test_facts_of_the_live_foreground_window_are_readable():
    f = window_facts(_api.user32.GetForegroundWindow())
    assert isinstance(f.title, str) and isinstance(f.class_name, str)
