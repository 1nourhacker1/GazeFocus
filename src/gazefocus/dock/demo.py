"""`gazefocus dock-demo`: the real dock on the laptop screen, cycling through every state (no camera).

Each state holds for a few seconds so it can be judged at the desk. Hovering opens the panel; a
click prints what it would do. Ctrl+C (or --seconds) ends it.
"""

from __future__ import annotations

import signal
import sys
from typing import Callable

from gazefocus.dock.view import ALERT, PAUSED, TRACKING, DockView
from gazefocus.types import Zone

EXTERNAL, LAP = Zone.EXTERNAL, Zone.LAPTOP
CYCLE_S = 32.0
KEYS = [6.0 + 0.15 * i for i in range(14)]  # typing from 6.0 s to 8.0 s, a key every 150 ms


def _t(zone, title, **kw) -> Callable[[float], DockView]:
    return lambda now: DockView(TRACKING, zone, title=title, detail="(demo)", **kw)


# (offset in the cycle, what to print, the view at that moment given `now`)
STEPS: list[tuple[float, str | None, Callable[[float], DockView]]] = [
    (0.0, "Tracking: focus on the external monitor (the bigger tile holds the water)", _t(EXTERNAL, "Focus: External")),
    (3.0, "Switch: the water flows to the laptop", _t(LAP, "Focus: Laptop")),
    *[(k, "Typing: amber water under a lid" if i == 0 else None,
       lambda now: DockView(TRACKING, LAP, last_key_t=now, title="Frozen while typing"))
      for i, k in enumerate(KEYS)],
    (8.2, "Stopped typing: the lid holds 0.3 s, melts, then the water turns green", lambda now: DockView(
        TRACKING, LAP, last_key_t=now - 0.2, title="Frozen while typing")),
    (11.0, "A glance while typing: the water wobbles", lambda now: DockView(
        TRACKING, LAP, last_key_t=now, blocked=True, title="Frozen while typing")),
    (14.0, "No face: the water evaporates", _t(LAP, "No face, holding Laptop", face=False)),
    (17.0, "Face back: drops condense into the tile", _t(LAP, "Focus: Laptop")),
    (20.0, "Paused: the water drains, the tiles dim, bars appear", lambda now: DockView(
        PAUSED, LAP, title="Paused", detail="camera off")),
    (23.0, "Resumed", _t(LAP, "Focus: Laptop")),
    (26.0, "Camera unavailable: empty tiles and a '!'", lambda now: DockView(
        ALERT, LAP, title="Camera unavailable", detail="details in the tray")),
    (29.0, "Back to tracking (the cycle repeats every 32 s)", _t(EXTERNAL, "Focus: External")),
]


def run_demo(seconds: float | None = None) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from gazefocus.config import load_config
    from gazefocus.dock.window import DockWindow
    from gazefocus.paths import app_dir
    from gazefocus.win.monitors import ensure_dpi_awareness

    ensure_dpi_awareness()
    cfg, _ = load_config(app_dir() / "config.toml")
    app = QApplication.instance() or QApplication(sys.argv)
    dock = DockWindow(cfg.dock, on_toggle_pause=lambda: print("  (click: GazeFocus would pause or resume)"),
                      on_recalibrate=lambda: print("  (click: GazeFocus would recalibrate)"))
    g = app.primaryScreen().availableGeometry()
    dock.place((g.left(), g.top(), g.right() + 1, g.bottom() + 1))
    dock.show()
    clock = dock.clock

    def schedule_cycle() -> None:
        for offset, label, view in STEPS:
            QTimer.singleShot(int(offset * 1000), lambda label=label, view=view: step(label, view))
        QTimer.singleShot(int(CYCLE_S * 1000), schedule_cycle)

    def step(label: str | None, view: Callable[[float], DockView]) -> None:
        if label:
            print(label, flush=True)
        dock.set_view(view(clock()))

    print("GazeFocus dock demo: hover the dock to open the panel; Ctrl+C quits.", flush=True)
    schedule_cycle()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wake = QTimer(interval=200, timeout=lambda: None)  # lets Python notice Ctrl+C
    wake.start()
    if seconds is not None:
        QTimer.singleShot(int(seconds * 1000), app.quit)
    code = app.exec()
    dock.close()
    return code
