import pytest

from gazefocus.app.state import Status
from gazefocus.app.tray import Tray, status_icon
from gazefocus.types import Zone


@pytest.mark.parametrize("status", list(Status))
@pytest.mark.parametrize("focus", [Zone.EXTERNAL, Zone.LAPTOP, None])
def test_every_status_has_an_icon(qapp, status, focus):
    icon = status_icon(status, focus)
    assert not icon.isNull() and not icon.pixmap(32, 32).toImage().isNull()


def make(qapp):
    calls = []
    tray = Tray(
        on_toggle_pause=lambda: calls.append("pause"),
        on_recalibrate=lambda: calls.append("recalibrate"),
        on_open_config=lambda: calls.append("config"),
        on_open_logs=lambda: calls.append("logs"),
        on_quit=lambda: calls.append("quit"),
        restore_focus=lambda: calls.append("restore"),
    )
    return tray, calls


def test_menu_actions_call_back(qapp):
    tray, calls = make(qapp)
    for action in (tray.pause_action, tray.recalibrate_action, tray.config_action, tray.logs_action, tray.quit_action):
        action.trigger()
    assert calls == ["pause", "recalibrate", "config", "logs", "quit"]
    tray.close()


def test_focus_is_restored_after_a_menu_that_opened_nothing(qapp):  # Review Focus #2
    tray, calls = make(qapp)
    tray.pause_action.trigger()
    tray._after_menu()
    tray._after_menu()  # dismissed with Esc: restore as well
    assert calls == ["pause", "restore", "restore"]
    tray.close()


def test_focus_is_not_stolen_back_from_a_window_the_menu_opened(qapp):
    tray, calls = make(qapp)
    tray.config_action.trigger()
    tray._after_menu()
    assert calls == ["config"]
    tray.close()


def test_update_shows_status_and_pause_resume(qapp):
    tray, _ = make(qapp)
    tray.update(Status.RUNNING, Zone.EXTERNAL)
    assert tray.icon.toolTip() == "GazeFocus: running (focus on EXTERNAL)"
    assert tray.pause_action.text() == "Pause (Ctrl+Alt+G)"
    tray.update(Status.PAUSED, None)
    assert tray.icon.toolTip() == "GazeFocus: paused" and tray.pause_action.text().startswith("Resume")
    tray.close()
