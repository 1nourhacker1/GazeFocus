import pytest

from gazefocus.logic.classifier import ZoneModel
from gazefocus.logic.decider import Context
from gazefocus.replay import Recorder, read_recording, replay, summarize
from gazefocus.types import HeadSample, Zone

TOY = ZoneModel(w=(1 / 15, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 0, 0), mean_laptop=(0, 0, 0), sd=(10.0, 5.0, 0.1))


def frames(segments, focus=Zone.LAPTOP, **ctx_kw):
    """segments: [(seconds, yaw_or_None)] at 15 FPS; the recorded focus stays `focus` unless ctx_kw overrides."""
    out, t = [], 0.0
    for seconds, yaw in segments:
        for _ in range(round(seconds * 15)):
            s = HeadSample(t=t, face=yaw is not None, yaw=yaw or 0.0)
            out.append((s, Context(t=t, focus_zone=focus, **ctx_kw)))
            t += 1 / 15
    return out


def test_recorder_round_trip(tmp_path):
    p = tmp_path / "rec.jsonl"
    data = frames([(0.2, -30.0), (0.1, None)], last_key_t=0.05)
    with Recorder(p) as rec:
        for s, c in data:
            rec.write(s, c)
    assert list(read_recording(p)) == data


def test_bad_line_reports_line_number(tmp_path):
    p = tmp_path / "rec.jsonl"
    p.write_text('{"sample": {"t": 0, "face": false}, "ctx": {"t": 0, "focus_zone": "LAPTOP"}}\n{oops\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        list(read_recording(p))


def test_replay_simulates_switches_both_ways():
    decisions = replay(frames([(1.0, 0.0), (1.0, -30.0), (1.2, 0.0)]), TOY)
    switches = [d for d in decisions if d.action == "switch"]
    assert [d.target for d in switches] == [Zone.LG, Zone.LAPTOP]
    assert 1.5 <= switches[0].t <= 1.8


def test_recorded_manual_focus_change_overrides_simulation():
    data = frames([(0.5, 0.0)])
    t0 = len(data) / 15
    later = frames([(1.5, 0.0)], focus=Zone.LG, last_manual_focus_t=t0)
    later = [(HeadSample(s.t + t0, s.face, s.yaw), Context(t=c.t + t0, focus_zone=c.focus_zone,
             last_manual_focus_t=c.last_manual_focus_t)) for s, c in later]
    decisions = replay(data + later, TOY)
    sw = [d for d in decisions if d.action == "switch"]
    assert sw and sw[0].target is Zone.LAPTOP and sw[0].t >= t0 + 1.0 - 1e-9


def test_summarize_collapses_typing_runs():
    decisions = replay(frames([(0.3, 0.0), (1.5, -30.0)], last_key_t=0.0), TOY)
    lines = summarize(decisions)
    assert sum("typing" in line for line in lines) == 1
    assert any("SWITCH" in line and "LG" in line for line in lines)


def test_replay_ignores_the_recorded_simulated_switches_of_another_model():
    """Review Important #3: watch records its *simulated* focus in ctx.focus_zone. A focus change
    only counts as the user's when last_manual_focus_t changes on that frame."""
    data = []
    for i in range(60):  # 4 s of steady laptop gaze...
        t = i / 15
        recorded_focus = Zone.LG if 1.0 <= t < 3.0 else Zone.LAPTOP  # ...but model A had "switched" to LG
        data.append((HeadSample(t, True, yaw=0.0), Context(t=t, focus_zone=recorded_focus)))
    decisions = replay(data, TOY)
    assert [d for d in decisions if d.action == "switch"] == []
