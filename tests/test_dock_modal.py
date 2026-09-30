import random

from PySide6.QtGui import QImage, QPainter, Qt

from gazefocus.calib.session import CalibrationResult
from gazefocus.dock.modal import (
    INTRO_BUTTONS,
    SCATTER,
    draw_intro,
    draw_result,
    fmt_deg,
    modal_button_at,
    plot_map,
    result_buttons,
)
from gazefocus.logic.classifier import fit_zone_model
from gazefocus.types import HeadSample

LEFT, TOP = 10.0, 6.0


def result(lg_yaw=30.0, lap_yaw=0.0, *, title="Calibrated ✓", q="excellent"):
    rng = random.Random(3)
    lg = [HeadSample(i, True, lg_yaw + rng.gauss(0, 2), rng.gauss(-3, 2), 0.0) for i in range(60)]
    lap = [HeadSample(i, True, lap_yaw + rng.gauss(0, 2), rng.gauss(-8, 2), 0.0) for i in range(60)]
    model = fit_zone_model(lg, lap)
    return CalibrationResult(model, {"LG": lg, "LAPTOP": lap}, {"LG": 60, "LAPTOP": 60}, q, title,
                             "Look at each screen: the water should follow.")


def render(draw, w=392, h=212):
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw(p)
    p.end()
    return img


def test_the_intro_buttons_are_hit_by_their_rects():
    for name, r in INTRO_BUTTONS.items():
        c = r.center()
        assert modal_button_at("intro", LEFT + c.x(), TOP + c.y(), LEFT, TOP) == name
    assert modal_button_at("intro", LEFT + 150, TOP + 60, LEFT, TOP) is None  # the paragraph


def test_a_result_that_can_be_saved_offers_save_and_redo():
    r = result()
    assert r.can_save and set(result_buttons(True)) == {"save", "redo"}
    save = result_buttons(True)["save"].center()
    assert modal_button_at("result", LEFT + save.x(), TOP + save.y(), LEFT, TOP, r) == "save"


def test_a_result_that_cannot_be_saved_offers_only_redo():
    bad = CalibrationResult(None, {}, {"LG": 3, "LAPTOP": 70}, None, "Too few samples", "Is the room too dark?")
    assert set(result_buttons(False)) == {"redo"}
    save = result_buttons(True)["save"].center()
    hit = modal_button_at("result", LEFT + save.x(), TOP + save.y(), LEFT, TOP, bad)
    assert hit != "save"
    redo = result_buttons(False)["redo"].center()
    assert modal_button_at("result", LEFT + redo.x(), TOP + redo.y(), LEFT, TOP, bad) == "redo"


def test_degrees_are_signed_like_the_mockup():
    assert (fmt_deg(29.3), fmt_deg(-3.6), fmt_deg(0.0)) == ("+29°", "−4°", "0°")


def test_the_plot_puts_the_lg_on_the_left_and_every_sample_inside():
    for lg_yaw, lap_yaw in ((30.0, 0.0), (-34.0, -3.0)):  # the LG's yaw can have either sign
        r = result(lg_yaw, lap_yaw)
        to_xy = plot_map(r)
        lg_x = [to_xy(s.yaw, s.pitch)[0] for s in r.samples["LG"]]
        lap_x = [to_xy(s.yaw, s.pitch)[0] for s in r.samples["LAPTOP"]]
        assert sum(lg_x) / 60 < sum(lap_x) / 60
        for s in r.samples["LG"] + r.samples["LAPTOP"]:
            x, y = to_xy(s.yaw, s.pitch)
            assert 4 <= x <= SCATTER.width() - 4 and 4 <= y <= SCATTER.height() - 4


def test_the_intro_start_button_is_blue(qapp):
    img = render(lambda p: draw_intro(p, LEFT, TOP, opacity=1.0, dark=False))
    r = INTRO_BUTTONS["start"]
    c = img.pixelColor(int(LEFT + r.left() + 5), int(TOP + r.center().y()))
    assert (c.red(), c.green(), c.blue()) == (10, 132, 255)


def test_the_scatter_shows_each_screen_in_its_colour(qapp):
    r = result()
    img = render(lambda p: draw_result(p, LEFT, TOP, r, opacity=1.0, dark=False))
    blue = purple = 0
    for x in range(int(SCATTER.width())):
        for y in range(int(SCATTER.height())):
            c = img.pixelColor(int(LEFT + SCATTER.left() + x), int(TOP + SCATTER.top() + y))
            if c.blue() > 200 and c.red() < 80 and c.alpha() > 100:
                blue += x < SCATTER.width() / 2
            if c.red() > 150 and c.blue() > 200 and c.green() < 120 and c.alpha() > 100:
                purple += x >= SCATTER.width() / 2
    assert blue > 20 and purple > 20  # the LG's blue points on the left, the laptop's purple on the right


def test_a_transparent_modal_panel_draws_nothing(qapp):
    img = render(lambda p: draw_result(p, LEFT, TOP, result(), opacity=0.0, dark=False))
    assert all(img.pixelColor(x, y).alpha() == 0 for x in range(0, 392, 7) for y in range(0, 212, 7))
