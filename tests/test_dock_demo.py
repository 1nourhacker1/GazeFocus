from gazefocus.dock.demo import CYCLE_S, KEYS, STEPS
from gazefocus.dock.scene import GlyphScene
from gazefocus.dock.view import ALERT, PAUSED, TRACKING


def test_the_steps_are_in_order_and_fit_the_cycle():
    offsets = [o for o, _, _ in STEPS]
    assert offsets == sorted(offsets) and 0 <= offsets[0] and offsets[-1] < CYCLE_S


def test_the_demo_visits_every_state():
    views = [view(100.0 + o) for o, _, view in STEPS]
    modes = {v.mode for v in views}
    assert {TRACKING, PAUSED, ALERT} <= modes
    assert any(not v.face for v in views) and any(v.blocked for v in views)
    assert any(v.last_key_t is not None for v in views)


def test_each_labelled_step_prints_one_line_and_typing_prints_once():
    labels = [label for _, label, _ in STEPS if label]
    assert sum("Typing" in label for label in labels) == 1 and len(KEYS) == 14


def test_the_whole_cycle_runs_through_the_scene():
    scene = GlyphScene(seed=0)
    for offset, _, view in STEPS:
        scene.update(view(100.0 + offset), 100.0 + offset)
        scene.frame(100.0 + offset + 0.1)
    assert not scene.busy(100.0 + CYCLE_S + 5)  # it settles: no idle animation
