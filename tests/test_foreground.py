from gazefocus.win.foreground import MRU_LIMIT, ForegroundHook, MruTracker

LG, LAP = r"\\.\DISPLAY5", r"\\.\DISPLAY1"


def test_mru_order_is_most_recent_first_per_monitor():
    m = MruTracker()
    m.on_foreground(1.0, 10, LG)
    m.on_foreground(2.0, 20, LAP)
    m.on_foreground(3.0, 11, LG)
    m.on_foreground(4.0, 10, LG)
    assert m.order(LG) == [10, 11] and m.order(LAP) == [20]
    assert m.last_app_window == 10


def test_a_window_moved_to_the_other_monitor_leaves_the_old_list():
    m = MruTracker()
    m.on_foreground(1.0, 10, LAP)
    m.on_foreground(2.0, 10, LG)
    assert m.order(LAP) == [] and m.order(LG) == [10]


def test_announced_switch_is_ours_unannounced_is_manual():
    m = MruTracker()
    m.expect(10, 5.0)
    assert m.on_foreground(5.1, 10, LG) is True and m.last_manual_t is None
    assert m.on_foreground(6.0, 20, LAP) is False and m.last_manual_t == 6.0


def test_announcement_expires_and_must_match_the_window():
    m = MruTracker()
    m.expect(10, 5.0)
    assert m.on_foreground(5.1, 99, LG) is False  # a different window came up
    m.expect(10, 7.0)
    assert m.on_foreground(7.5, 10, LG) is False  # 0.5 s later than announced: someone else did it


def test_non_targets_count_as_manual_but_never_enter_the_mru():
    m = MruTracker()
    m.on_foreground(1.0, 30, LAP, is_target=False)  # e.g. the taskbar
    assert m.order(LAP) == [] and m.last_manual_t == 1.0 and m.last_app_window is None


def test_mru_is_bounded_and_forget_works():
    m = MruTracker()
    for i in range(MRU_LIMIT + 5):
        m.on_foreground(float(i), i, LG)
    assert len(m.order(LG)) == MRU_LIMIT
    m.forget(MRU_LIMIT + 4)
    assert MRU_LIMIT + 4 not in m.order(LG)


def test_hook_installs_and_uninstalls():
    hook = ForegroundHook(lambda hwnd: None)
    hook.close()
    hook.close()  # idempotent
