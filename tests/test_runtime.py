import numpy as np
import pytest

from gazefocus.logic.classifier import ZoneClassifier, ZoneModel
from gazefocus.logic.decider import GazeDecider
from gazefocus.replay import Recorder, read_recording
from gazefocus.runtime import (
    MIN_CAL_SAMPLES,
    Pacer,
    bench_loop,
    calibrate,
    collect_phase,
    margin_bar,
    watch_loop,
)
from gazefocus.types import HeadSample, Zone

FRAME = np.zeros((2, 2, 3), np.uint8)
TOY = ZoneModel(w=(1 / 15, 0.0, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 0, 0, 0), mean_laptop=(0, 0, 0, 0))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, dt):
        self.now += max(0.0, dt)


def test_pacer_holds_the_rate():
    c = FakeClock()
    p = Pacer(15.0, c.time, c.sleep)
    for _ in range(15):
        p.wait()
    assert c.now == pytest.approx(1.0)


def test_collect_phase_discards_settle_time():
    c = FakeClock()
    out = collect_phase(lambda: FRAME, lambda f, t: HeadSample(t, True), 2.0, clock=c.time, sleep=c.sleep)
    assert 23 <= len(out) <= 25 and out[0].t >= 0.4


def test_collect_phase_survives_no_frames():
    c = FakeClock()
    assert collect_phase(lambda: None, lambda f, t: HeadSample(t, True), 1.0, clock=c.time, sleep=c.sleep) == []


def phase_tracker(said, lg_yaw=-32.0, face=True):
    def track(frame, t):
        return HeadSample(t, face, yaw=lg_yaw if "LG" in said[-1] else -2.0, pitch=0.0)

    return track


def test_calibrate_fits_and_counts():
    c, said = FakeClock(), []
    rng = np.random.default_rng(1)

    def track(frame, t):
        base = -32.0 if "LG" in said[-1] else -2.0
        return HeadSample(t, True, yaw=base + rng.normal(0, 2), pitch=rng.normal(0, 2))

    model, counts = calibrate(lambda: FRAME, track, clock=c.time, sleep=c.sleep, say=said.append)
    assert counts["LG"] >= MIN_CAL_SAMPLES and counts["LAPTOP"] >= MIN_CAL_SAMPLES
    assert model.z(np.array([-32.0, 0, 0, 0])) < -0.5 < 0.5 < model.z(np.array([-2.0, 0, 0, 0]))
    assert any("LG" in s for s in said) and any("separation" in s for s in said)


def test_calibrate_rejects_too_few_face_samples():
    c, said = FakeClock(), []
    with pytest.raises(ValueError, match="face"):
        calibrate(lambda: FRAME, phase_tracker(said, face=False), clock=c.time, sleep=c.sleep, say=said.append)


def test_margin_bar():
    assert "o" not in margin_bar(None)
    assert margin_bar(-2.0).startswith("LG[o") and margin_bar(5.0).endswith("o]LAPTOP")
    assert margin_bar(0.0) == "LG[----------o----------]LAPTOP"


def test_watch_loop_switches_and_records(tmp_path):
    c, said = FakeClock(), []
    track = lambda f, t: HeadSample(t, True, yaw=0.0 if t < 1.0 else -30.0)
    rec_path = tmp_path / "w.jsonl"
    with Recorder(rec_path) as rec:
        out = watch_loop(
            lambda: FRAME, track, ZoneClassifier(TOY), GazeDecider(),
            seconds=2.5, clock=c.time, sleep=c.sleep, say=said.append, recorder=rec,
        )
    assert [d.target for d in out if d.action == "switch"] == [Zone.LG]
    assert any("SWITCH -> LG" in s for s in said)
    assert len(list(read_recording(rec_path))) == len(out)


def test_bench_loop_reports_and_judges():
    c = FakeClock()
    cpu = {"t": 0.0}

    def track(frame, t):
        c.now += 0.008
        cpu["t"] += 0.008
        return HeadSample(t, True)

    lines = []
    rep = bench_loop(
        lambda: FRAME, track, seconds=3.0, report_every=1.0, clock=c.time, sleep=c.sleep,
        fps=15.0, cpu_time=lambda: cpu["t"], rss_mb=lambda: 250.0, cores=4, say=lines.append,
    )
    assert rep.frames == pytest.approx(45, abs=1)
    assert rep.ms_p50 == pytest.approx(8.0)
    assert rep.cpu_pct == pytest.approx(3.0, abs=0.2)  # 15 * 0.008 s per s / 4 cores
    assert "CPU" in rep.verdict() and "FAIL" in rep.verdict() and "RSS 250" in rep.verdict()
    assert len(lines) >= 2


def test_default_clocks_are_high_resolution():
    # Ruling carried from Task 4: time.monotonic ticks at 15.6 ms on Windows.
    import inspect
    import time

    from gazefocus import runtime

    for fn in (runtime.collect_phase, runtime.calibrate, runtime.watch_loop, runtime.bench_loop):
        assert inspect.signature(fn).parameters["clock"].default is time.perf_counter, fn.__name__
