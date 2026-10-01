import numpy as np
from PySide6.QtGui import QImage, QPainter, Qt

from gazefocus.dock.panel import BUTTONS, PREVIEW, PanelContent, button_at, draw_panel, preview_image

LEFT, TOP = 20.0, 10.0


def render(content, opacity=1.0, dark=False):
    img = QImage(340, 180, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw_panel(p, LEFT, TOP, content, opacity=opacity, dark=dark)
    p.end()
    return img


def at(img, x, y):
    c = img.pixelColor(int(LEFT + x), int(TOP + y))
    return c.red(), c.green(), c.blue(), c.alpha()


def camera(left_bgr, right_bgr, w=160, h=120):
    f = np.zeros((h, w, 3), np.uint8)
    f[:, : w // 2], f[:, w // 2:] = left_bgr, right_bgr
    return f


def test_buttons_are_hit_by_their_rects(qapp):
    for name, r in BUTTONS.items():
        assert button_at(LEFT + r.center().x(), TOP + r.center().y(), LEFT, TOP) == name
    assert button_at(LEFT + 60, TOP + 90, LEFT, TOP) is None  # the preview is not a button
    assert button_at(LEFT + 400, TOP + 130, LEFT, TOP) is None


def test_the_buttons_fit_inside_the_300_px_panel(qapp):
    assert all(r.right() <= 288 and r.bottom() <= 146 for r in BUTTONS.values())


def test_no_preview_shows_the_dark_placeholder(qapp):
    img = render(PanelContent("Paused", "camera off", "Resume"))
    r, g, b, a = at(img, PREVIEW.center().x(), PREVIEW.center().y())
    assert a == 255 and max(r, g, b) < 80


def test_the_preview_is_mirrored(qapp):
    frame = camera((0, 0, 255), (255, 0, 0))  # red on the camera's left, blue on its right (BGR)
    img = render(PanelContent("Focus: External", "", "Pause", preview=preview_image(frame)))
    left = at(img, PREVIEW.left() + 20, PREVIEW.center().y())
    right = at(img, PREVIEW.right() - 20, PREVIEW.center().y())
    assert left[2] > 200 and left[0] < 60  # blue shows on the left: a mirror
    assert right[0] > 200 and right[2] < 60


def test_the_face_box_is_drawn_mirrored_in_green(qapp):
    frame = camera((0, 0, 0), (0, 0, 0))
    content = PanelContent("Focus: External", "", "Pause", preview=preview_image(frame), face_box=(0.1, 0.2, 0.4, 0.8))
    img = render(content)
    greens = [at(img, x, PREVIEW.center().y()) for x in np.arange(PREVIEW.left(), PREVIEW.right(), 0.5)]
    xs = [PREVIEW.left() + i * 0.5 for i, c in enumerate(greens) if c[1] > 120 and c[0] < 120]
    assert xs and min(xs) > PREVIEW.center().x()  # a box on the camera's left appears on the right


def test_a_transparent_panel_draws_nothing(qapp):
    img = render(PanelContent("Focus: External", "x", "Pause"), opacity=0.0)
    assert all(at(img, x, y)[3] == 0 for x in (30, 150, 250) for y in (60, 130))


def test_preview_image_owns_its_pixels(qapp):
    frame = camera((1, 2, 3), (4, 5, 6))
    img = preview_image(frame)
    frame[:] = 0  # the camera thread reuses its buffer
    assert img.pixelColor(5, 5).blue() == 1 and img.width() == 160
