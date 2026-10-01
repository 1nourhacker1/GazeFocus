"""Render the README's screenshots with the app's own drawing code, offscreen, over a made-up wallpaper.

Screen captures can't show the dock: it excludes itself from capture. Run:
    uv run python scripts/render_screenshots.py
It writes docs/images/*.png. Nothing appears on screen and no camera is used.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ["QT_SCALE_FACTOR"] = "2"  # crisp images: everything renders at 2 physical px per logical px

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtGui import QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gazefocus.calib.overlay import CardWindow, draw_drop  # noqa: E402
from gazefocus.calib.session import Card, CalibrationResult, DropState  # noqa: E402
from gazefocus.config import DockCfg  # noqa: E402
from gazefocus.dock import geometry  # noqa: E402
from gazefocus.dock.view import ALERT, PAUSED, TRACKING, DockView  # noqa: E402
from gazefocus.dock.window import DockWindow  # noqa: E402
from gazefocus.logic.classifier import fit_zone_model  # noqa: E402
from gazefocus.types import HeadSample, Zone  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
SCREEN = (1600, 1000)  # logical px of the made-up laptop screen
DPR = 2


def wallpaper(w: int, h: int, seed: int = 7) -> np.ndarray:
    """Soft colour blobs on a deep blue, like a desktop wallpaper (BGR, physical px)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (70, 38, 28)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for colour in ((235, 120, 70), (200, 80, 190), (90, 170, 250), (120, 210, 130), (250, 190, 120)):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h * 0.8), rng.uniform(0.25, 0.45) * w
        k = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))[..., None]
        img = img * (1 - 0.75 * k) + np.array(colour, np.float32) * 0.75 * k
    img = cv2.GaussianBlur(img, (0, 0), 25)
    return np.clip(img, 0, 255).astype(np.uint8)


WALL = wallpaper(SCREEN[0] * DPR, SCREEN[1] * DPR)


class WallGrabber:
    """Stands in for the GDI grab: the wallpaper under the window."""

    def __init__(self, w, h):
        self.w, self.h = w, h

    def grab(self, x, y):
        out = np.zeros((self.h, self.w, 3), np.uint8)
        src = WALL[max(0, y):y + self.h, max(0, x):x + self.w]
        out[: src.shape[0], : src.shape[1]] = src
        return out

    def close(self):
        pass


class Clock:
    t = 100.0

    def __call__(self):
        return Clock.t


class Ticker(QObject):
    tick = Signal()
    running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def handled(self):
        pass

    def close(self):
        pass


def run(dock, ticker, seconds):
    end = Clock.t + seconds
    while Clock.t < end:
        Clock.t += 1 / 120
        if ticker.running:
            ticker.tick.emit()


def to_qimage(bgr: np.ndarray) -> QImage:
    h, w = bgr.shape[:2]
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    return QImage(rgba.data, w, h, 4 * w, QImage.Format_ARGB32).copy()


def new_dock(scale=2.625):
    ticker = Ticker()
    d = DockWindow(DockCfg(scale=scale), on_toggle_pause=lambda: None, on_recalibrate=lambda: None, native=False,
                   grabber_factory=WallGrabber, ticker=ticker, clock=Clock(), seed=3)
    d.place((0, 0, SCREEN[0], SCREEN[1]))
    d.show()
    d._refresh_backdrop()
    return d, ticker


def physical(img: QImage) -> QImage:
    """The same pixels at a pixel ratio of 1, so they are drawn 1:1 onto a plain canvas."""
    out = img.copy()
    out.setDevicePixelRatio(1)
    return out


def crop_of_dock(d) -> QImage:
    """The wallpaper behind the dock with the dock drawn over it: what the user sees."""
    x, y, w, h = d.x() * DPR, d.y() * DPR, d.width() * DPR, d.height() * DPR
    canvas = to_qimage(WALL[y:y + h, x:x + w])
    p = QPainter(canvas)
    p.drawImage(0, 0, physical(d.img))
    p.end()
    return canvas


def save(img: QImage, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT / name))
    print("wrote", OUT / name, f"{img.width()}x{img.height()}")


def dock_states() -> None:
    """Six collapsed docks side by side: each state the glyph shows."""
    states = [
        ("Focus on the laptop", DockView(TRACKING, Zone.LAPTOP)),
        ("Focus on the external monitor", DockView(TRACKING, Zone.EXTERNAL)),
        ("Typing: frozen", "typing"),
        ("No face", DockView(TRACKING, Zone.LAPTOP, face=False)),
        ("Paused", DockView(PAUSED, Zone.LAPTOP)),
        ("Needs you", DockView(ALERT, Zone.LAPTOP)),
    ]
    tiles = []
    for _, view in states:
        d, ticker = new_dock()
        d.set_view(DockView(TRACKING, Zone.EXTERNAL))
        run(d, ticker, 2.0)
        if view == "typing":
            d.set_view(DockView(TRACKING, Zone.LAPTOP))
            run(d, ticker, 2.0)
            d.set_view(DockView(TRACKING, Zone.LAPTOP, last_key_t=Clock.t))
            run(d, ticker, 0.25)
        else:
            d.set_view(view)
            run(d, ticker, 2.5 if view.face else 1.2)  # steam is caught mid-rise
        d._frame(Clock.t)
        pill = geometry.pill_at(0.0, d.cfg.scale, d.width())
        full = crop_of_dock(d)
        x0, y0 = int((pill.left - 18) * DPR), 0
        tiles.append(full.copy(x0, y0, int((2 * pill.hw + 36) * DPR), int((2 * pill.hh + 30) * DPR)))
        d.close()
    gap = 0
    strip = QImage(sum(t.width() for t in tiles) + gap * (len(tiles) - 1), tiles[0].height(), QImage.Format_ARGB32)
    p = QPainter(strip)
    x = 0
    for t in tiles:
        p.drawImage(x, 0, t)
        x += t.width() + gap
    p.end()
    save(strip, "dock-states.png")


def preview_frame() -> np.ndarray:
    """A drawn stand-in for the camera picture: no real face."""
    f = np.zeros((120, 160, 3), np.uint8)
    f[:] = (58, 52, 48)
    cv2.ellipse(f, (80, 140), (62, 48), 0, 0, 360, (92, 84, 78), -1)  # shoulders
    cv2.ellipse(f, (82, 58), (24, 31), 0, 0, 360, (128, 150, 178), -1)  # head
    return cv2.GaussianBlur(f, (0, 0), 1.2)


def hover_panel() -> None:
    d, ticker = new_dock()
    d.set_view(DockView(TRACKING, Zone.EXTERNAL, title="Focus: LG FHD",
                        detail="yaw +31.2°   pitch +4.1°\nmargin -1.84   key 6.2 s ago"))
    run(d, ticker, 2.0)
    d._hover.timeout.emit()
    run(d, ticker, 1.2)
    d.set_preview(preview_frame(), HeadSample(Clock.t, True, yaw=31.2, pitch=4.1, box=(0.36, 0.22, 0.66, 0.78),
                                              nose=(0.5, 0.5)))
    save(crop_of_dock(d), "dock-panel.png")
    d.close()


def sample_result(names=("LG FHD", "Laptop")) -> CalibrationResult:
    rng = random.Random(5)
    ext = [HeadSample(i, True, 31 + rng.gauss(0, 4), 4 + rng.gauss(0, 3), 0.5 + rng.gauss(0, 0.03)) for i in range(72)]
    lap = [HeadSample(i, True, rng.gauss(0, 4), -6 + rng.gauss(0, 3), 0.5 + rng.gauss(0, 0.03)) for i in range(72)]
    m = fit_zone_model(ext, lap)
    return CalibrationResult(m, {"EXTERNAL": ext, "LAPTOP": lap}, {"EXTERNAL": 72, "LAPTOP": 72}, "excellent",
                             "Calibrated ✓", "Look at each screen: the water should follow.",
                             {"EXTERNAL": names[0], "LAPTOP": names[1]})


def result_panel() -> None:
    d, ticker = new_dock()
    d.show_result(sample_result(), lambda: None, lambda: None)
    run(d, ticker, 1.5)
    save(crop_of_dock(d), "calibration-result.png")
    d.close()


def calibration() -> None:
    """The laptop screen mid-calibration, scaled down: dimmed, the card, the drop on its tour, the dock."""
    global WALL
    w, h = SCREEN[0] * DPR, SCREEN[1] * DPR
    dimmed = (WALL.astype(np.float32) * 0.75).astype(np.uint8)  # the target screen's 25 % dim
    original, WALL = WALL, dimmed
    try:
        card = CardWindow((0, 0, SCREEN[0], SCREEN[1]), native=False, grabber_factory=WallGrabber, refraction=True)
        card.set_card(Card("LAPTOP", "Now this screen", "Follow the drop"), 0.0)
        d, ticker = new_dock()
        canvas = to_qimage(dimmed)
        p = QPainter(canvas)
        p.drawImage(card.x() * DPR, card.y() * DPR, physical(card.img))
        p.scale(DPR, DPR)
        draw_drop(p, 0.64 * SCREEN[0], 0.45 * SCREEN[1], DropState(0, 0, 1.0, 1.3, 0.83, 25), progress=0.62,
                  ring_alpha=1.0)
        p.resetTransform()
        p.drawImage(d.x() * DPR, d.y() * DPR, physical(d.img))
        p.end()
        card.close()
        d.close()
    finally:
        WALL = original
    crop = canvas.copy(int(0.22 * w), 0, int(0.56 * w), int(0.56 * h))  # the dock, the card and the drop
    save(crop.scaled(crop.width() // 2, crop.height() // 2, mode=Qt.SmoothTransformation), "calibration.png")


def main() -> int:
    QApplication.instance() or QApplication(sys.argv)
    for family in ("Segoe UI Variable Text", "Segoe UI Variable Display"):  # variable fonts: offscreen Qt can't load them
        QFont.insertSubstitution(family, "Segoe UI")
    dock_states()
    hover_panel()
    result_panel()
    calibration()
    return 0


if __name__ == "__main__":
    sys.exit(main())
