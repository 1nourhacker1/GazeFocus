"""System-tray icon and menu: status at a glance, Pause/Resume, Recalibrate, config, logs, Quit.

Opening a tray menu makes the taskbar the foreground window. When the menu closes without
opening a window of its own, the tray hands focus back to the last app window, so the next
keystroke doesn't land on the taskbar.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from gazefocus.app.state import Status
from gazefocus.types import Zone

GREEN, BLUE, GREY, RED = QColor(40, 167, 69), QColor(10, 132, 255), QColor(142, 142, 147), QColor(255, 69, 58)
ATTENTION = {Status.CAMERA_WAIT, Status.NOT_CALIBRATED, Status.LAYOUT_CHANGED, Status.UNSUPPORTED, Status.TRACKER_FAILED}
RESTORE_DELAY_MS = 150


def status_icon(status: Status, focus: Zone | None, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    k = size / 32.0
    tiles = {Zone.LG: QRectF(2 * k, 7 * k, 15 * k, 11 * k), Zone.LAPTOP: QRectF(19 * k, 11 * k, 11 * k, 9 * k)}
    for zone, rect in tiles.items():
        path = QPainterPath()
        path.addRoundedRect(rect, 2.5 * k, 2.5 * k)
        if status is Status.CALIBRATING:
            p.fillPath(path, BLUE)
        elif status is Status.RUNNING and zone == focus:
            p.fillPath(path, GREEN)
        p.setPen(QPen(QColor(0, 0, 0, 200), 3.0 * k))  # dark rim + light line: readable on any taskbar
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255), 1.4 * k))
        p.drawPath(path)
    if status is Status.PAUSED or status in (Status.LOCKED, Status.SUSPENDED):
        p.setPen(Qt.NoPen)
        p.setBrush(GREY)
        for x in (12.5, 17.5):
            p.drawRoundedRect(QRectF(x * k, 22 * k, 3 * k, 8 * k), 1 * k, 1 * k)
    if status in ATTENTION:
        p.setPen(Qt.NoPen)
        p.setBrush(RED)
        p.drawEllipse(QPointF(25 * k, 25 * k), 6 * k, 6 * k)
        p.setPen(QPen(QColor(255, 255, 255), 2.2 * k))
        p.drawLine(QPointF(25 * k, 21.5 * k), QPointF(25 * k, 25.5 * k))
        p.drawPoint(QPointF(25 * k, 28 * k))
    p.end()
    return QIcon(pm)


class Tray:
    def __init__(
        self,
        *,
        on_toggle_pause: Callable[[], None],
        on_recalibrate: Callable[[], None],
        on_open_config: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_quit: Callable[[], None],
        restore_focus: Callable[[], None],
        hotkey_text: str = "Ctrl+Alt+G",
    ) -> None:
        self.restore_focus, self.hotkey_text = restore_focus, hotkey_text
        self._opened_window = False
        self.icon = QSystemTrayIcon()
        self.menu = QMenu()
        self.status_action = self.menu.addAction("GazeFocus")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()
        self.pause_action = self.menu.addAction(f"Pause ({hotkey_text})")
        self.pause_action.triggered.connect(self._act(on_toggle_pause, opens_window=False))
        self.recalibrate_action = self.menu.addAction("Recalibrate")
        self.recalibrate_action.triggered.connect(self._act(on_recalibrate, opens_window=False))
        self.menu.addSeparator()
        self.config_action = self.menu.addAction("Open config")
        self.config_action.triggered.connect(self._act(on_open_config, opens_window=True))
        self.logs_action = self.menu.addAction("Open logs folder")
        self.logs_action.triggered.connect(self._act(on_open_logs, opens_window=True))
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("Quit GazeFocus")
        self.quit_action.triggered.connect(self._act(on_quit, opens_window=True))
        self.menu.aboutToHide.connect(self._menu_hidden)
        self.icon.setContextMenu(self.menu)
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.update(Status.NOT_CALIBRATED, None)
        if self.available:
            self.icon.show()

    def _act(self, fn: Callable[[], None], *, opens_window: bool) -> Callable[[], None]:
        def run() -> None:
            self._opened_window = opens_window
            fn()

        return run

    def _menu_hidden(self) -> None:
        QTimer.singleShot(RESTORE_DELAY_MS, self._after_menu)  # after `triggered`, which fires on release

    def _after_menu(self) -> None:
        if not self._opened_window:
            self.restore_focus()
        self._opened_window = False

    def update(self, status: Status, focus: Zone | None) -> None:
        self.icon.setIcon(status_icon(status, focus))
        text = f"GazeFocus: {status.value}"
        if status is Status.RUNNING and focus in (Zone.LG, Zone.LAPTOP):
            text += f" (focus on {focus.value})"
        self.icon.setToolTip(text)
        self.status_action.setText(text)
        paused = status is Status.PAUSED
        self.pause_action.setText(f"{'Resume' if paused else 'Pause'} ({self.hotkey_text})")

    def notify(self, title: str, text: str) -> None:
        if self.available:
            self.icon.showMessage(title, text, QSystemTrayIcon.Information, 6000)

    def close(self) -> None:
        self.icon.hide()
