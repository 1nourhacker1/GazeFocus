from gazefocus.win.msgwindow import MessageWindow, pump_messages

WM_USER = 0x0400


def test_posted_message_reaches_its_handler():
    win = MessageWindow()
    got = []
    win.on(WM_USER + 1, lambda w, l: got.append((w, l)) or 0)
    try:
        assert win.post(WM_USER + 1, 7, 9)
        pump_messages(0.2)
    finally:
        win.close()
    assert got == [(7, 9)]


def test_two_windows_dispatch_independently():
    a, b = MessageWindow("a"), MessageWindow("b")
    got = []
    a.on(WM_USER + 2, lambda w, l: got.append("a") or 0)
    b.on(WM_USER + 2, lambda w, l: got.append("b") or 0)
    try:
        b.post(WM_USER + 2)
        pump_messages(0.2)
    finally:
        a.close()
        b.close()
    assert got == ["b"]


def test_a_failing_handler_does_not_break_the_pump():
    win = MessageWindow()
    got = []

    def boom(w, l):
        raise RuntimeError("handler bug")

    win.on(WM_USER + 3, boom)
    win.on(WM_USER + 4, lambda w, l: got.append("still alive") or 0)
    try:
        win.post(WM_USER + 3)
        win.post(WM_USER + 4)
        pump_messages(0.2)
    finally:
        win.close()
    assert got == ["still alive"]


def test_qt_event_loop_pumps_the_window(qapp):
    win = MessageWindow()
    got = []
    win.on(WM_USER + 5, lambda w, l: got.append(w) or 0)
    try:
        win.post(WM_USER + 5, 42)
        from PySide6.QtCore import QDeadlineTimer, QEventLoop

        qapp.processEvents(QEventLoop.AllEvents, QDeadlineTimer(200))
        for _ in range(20):
            if got:
                break
            qapp.processEvents()
    finally:
        win.close()
    assert got == [42]


def test_close_is_idempotent():
    win = MessageWindow()
    win.close()
    win.close()
    assert win.hwnd == 0
