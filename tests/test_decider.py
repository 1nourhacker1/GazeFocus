import pytest

from gazefocus.config import DeciderCfg
from gazefocus.logic.decider import Context, GazeDecider
from gazefocus.types import Zone

FPS = 15
EXTERNAL, LAPTOP, UNKNOWN = Zone.EXTERNAL, Zone.LAPTOP, Zone.UNKNOWN


def frames(t0, t1):
    n = round((t1 - t0) * FPS)
    return [t0 + i / FPS for i in range(n + 1)]


def feed(dec, zone, times, focus=LAPTOP, **kw):
    return [dec.step(zone, -0.8 if zone is EXTERNAL else 0.8, Context(t=t, focus_zone=focus, **kw)) for t in times]


def first(decisions, action):
    return next((d for d in decisions if d.action == action), None)


def test_on_target_and_unknown_do_nothing():
    dec = GazeDecider()
    assert feed(dec, LAPTOP, [0.0])[0].reason == "on target"
    assert feed(dec, UNKNOWN, [0.1])[0].reason == "no gaze target"


def test_switch_fires_once_after_dwell():
    dec = GazeDecider()
    out = feed(dec, EXTERNAL, frames(0.0, 1.0))
    sw = first(out, "switch")
    assert sw.t == pytest.approx(8 / FPS) and sw.target is EXTERNAL and sw.reason == "dwell met"
    assert out[7].reason.startswith("dwell ")
    assert [d.reason for d in out[9:]] == ["switch pending"] * len(out[9:])
    assert sum(d.action == "switch" for d in out) == 1


def test_margin_passes_through():
    d = GazeDecider().step(EXTERNAL, -0.93, Context(t=0.0, focus_zone=LAPTOP))
    assert d.margin == -0.93 and d.zone is EXTERNAL


def test_dwell_resets_on_unknown():
    dec = GazeDecider()
    assert first(feed(dec, EXTERNAL, frames(0.0, 0.4)), "switch") is None
    feed(dec, UNKNOWN, [0.45])
    out = feed(dec, EXTERNAL, frames(0.5, 1.2))
    assert first(out, "switch").t == pytest.approx(0.5 + 8 / FPS)


def test_glance_while_typing_is_blocked_then_switches_after_thaw():
    dec = GazeDecider()
    out = feed(dec, EXTERNAL, frames(0.0, 2.0), last_key_t=0.3)
    blocked = [d for d in out if d.action == "blocked"]
    assert blocked and blocked[0].reason.startswith("typing ")
    sw = first(out, "switch")
    assert sw.t >= 1.8 and sw.t < 1.8 + 1.5 / FPS  # fires on the first frame after 0.3 + 1.5 s


def test_continuous_typing_never_switches():
    dec = GazeDecider()
    out = []
    for t in frames(0.0, 1.5):
        last_key = t - (t % 0.2)  # a key every 200 ms
        out += feed(dec, EXTERNAL, [t], last_key_t=last_key)
    out += feed(dec, LAPTOP, frames(1.6, 2.0))
    assert first(out, "switch") is None


def test_mouse_button_held_blocks():
    out = feed(GazeDecider(), EXTERNAL, frames(0.0, 1.0), mouse_buttons_down=True)
    assert first(out, "switch") is None
    assert first(out, "blocked").reason == "mouse button held"


def test_manual_focus_cooldown():
    out = feed(GazeDecider(), EXTERNAL, frames(0.0, 1.5), last_manual_focus_t=0.3)
    assert first(out, "blocked").reason == "manual focus cooldown"
    assert first(out, "switch").t >= 1.3


@pytest.mark.parametrize(
    "kw,reason",
    [({"ready": False}, "not ready"), ({"paused": True}, "paused"), ({"fullscreen": True}, "fullscreen app")],
)
def test_other_freezes(kw, reason):
    out = feed(GazeDecider(), EXTERNAL, frames(0.0, 1.0), **kw)
    assert first(out, "switch") is None and first(out, "blocked").reason == reason


def test_freeze_priority_order():
    out = feed(GazeDecider(), EXTERNAL, frames(0.0, 1.0), ready=False, paused=True, mouse_buttons_down=True, last_key_t=0.9)
    assert first(out, "blocked").reason == "not ready"


def test_post_switch_cooldown_with_short_dwell():
    dec = GazeDecider(DeciderCfg(dwell_ms=100))
    sw = first(feed(dec, EXTERNAL, frames(0.0, 0.3)), "switch")
    dec.notify_switched(sw.t)
    out = feed(dec, LAPTOP, frames(0.2, 1.0), focus=EXTERNAL)
    assert first(out, "blocked").reason == "post-switch cooldown"
    assert first(out, "switch").t >= sw.t + 0.4 - 1e-9


def test_failed_switch_needs_look_away():
    dec = GazeDecider()
    sw = first(feed(dec, EXTERNAL, frames(0.0, 0.6)), "switch")
    dec.notify_switch_failed(sw.t)
    out = feed(dec, EXTERNAL, frames(0.7, 1.5))
    assert first(out, "switch") is None
    assert first(out, "blocked").reason == "switch failed; look away to retry"
    feed(dec, UNKNOWN, [1.55])
    assert first(feed(dec, EXTERNAL, frames(1.6, 2.3)), "switch") is not None


def test_unknown_focus_counts_as_elsewhere():
    out = feed(GazeDecider(), LAPTOP, frames(0.0, 1.0), focus=UNKNOWN)
    assert first(out, "switch").target is LAPTOP


def test_failure_latches_the_pending_target_even_if_gaze_moved_meanwhile():
    """Plan 1 review: notify_switch_failed latched the *current* candidate, which is None if the
    gaze wandered to UNKNOWN while the (asynchronous) switch was still pending."""
    dec = GazeDecider()
    sw = first(feed(dec, EXTERNAL, frames(0.0, 0.6)), "switch")
    feed(dec, UNKNOWN, [0.65])  # gaze wanders while the switch is in flight
    dec.notify_switch_failed(0.7)
    out = feed(dec, EXTERNAL, frames(0.75, 1.6))
    assert sw.target is EXTERNAL
    assert first(out, "switch") is None
    assert first(out, "blocked").reason == "switch failed; look away to retry"


def test_reason_category_ignores_numbers():
    from gazefocus.logic.decider import reason_category

    assert reason_category("typing 0.3s") == reason_category("typing 1.2s") == "typing"
    assert reason_category("manual focus cooldown") == "manual focus cooldown"
