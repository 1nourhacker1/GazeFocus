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
TOY = ZoneModel(w=(1 / 15, 0.0, 0.0), b=1.0, separation=5.0, mean_external=(-30, 0, 0), mean_laptop=(0, 0, 0), sd=(10.0, 5.0, 0.1))


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
    # settle 1.0 s (desk session: a head turn between screens takes ~1 s): (2.0 - 1.0) * 15 frames
    assert 14 <= len(out) <= 16 and out[0].t >= 1.0 - 1e-9


def test_collect_phase_survives_no_frames():
    c = FakeClock()
    assert collect_phase(lambda: None, lambda f, t: HeadSample(t, True), 1.0, clock=c.time, sleep=c.sleep) == []


def phase_tracker(said, external_yaw=-32.0, face=True):
    def track(frame, t):
        return HeadSample(t, face, yaw=external_yaw if "external monitor" in said[-1] else -2.0, pitch=0.0)

    return track


def test_calibrate_fits_and_counts():
    c, said = FakeClock(), []
    rng = np.random.default_rng(1)

    def track(frame, t):
        base = -32.0 if "external monitor" in said[-1] else -2.0
        return HeadSample(t, True, yaw=base + rng.normal(0, 2), pitch=rng.normal(0, 2))

    model, counts = calibrate(lambda: FRAME, track, clock=c.time, sleep=c.sleep, say=said.append)
    assert counts["EXTERNAL"] >= MIN_CAL_SAMPLES and counts["LAPTOP"] >= MIN_CAL_SAMPLES
    assert model.z(np.array([-32.0, 0, 0])) < -0.5 < 0.5 < model.z(np.array([-2.0, 0, 0]))
    assert any("external monitor" in s for s in said) and any("separation" in s for s in said)


def test_calibrate_rejects_too_few_face_samples():
    c, said = FakeClock(), []
    with pytest.raises(ValueError, match="face"):
        calibrate(lambda: FRAME, phase_tracker(said, face=False), clock=c.time, sleep=c.sleep, say=said.append)


def test_margin_bar():
    assert "o" not in margin_bar(None)
    assert margin_bar(-2.0).startswith("EXTERNAL[o") and margin_bar(5.0).endswith("o]LAPTOP")
    assert margin_bar(0.0) == "EXTERNAL[----------o----------]LAPTOP"


def test_watch_loop_switches_and_records(tmp_path):
    c, said = FakeClock(), []
    track = lambda f, t: HeadSample(t, True, yaw=0.0 if t < 1.0 else -30.0)
    rec_path = tmp_path / "w.jsonl"
    with Recorder(rec_path) as rec:
        out = watch_loop(
            lambda: FRAME, track, ZoneClassifier(TOY), GazeDecider(),
            seconds=2.5, clock=c.time, sleep=c.sleep, say=said.append, recorder=rec,
        )
    assert [d.target for d in out if d.action == "switch"] == [Zone.EXTERNAL]
    assert any("SWITCH -> EXTERNAL" in s for s in said)
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


def test_calibrate_cues_each_phase_before_it_records():
    """Desk session: typed cues arrived seconds late and ruined a calibration; the program must cue itself."""
    c, said, cues = FakeClock(), [], []
    rng = np.random.default_rng(2)

    def track(frame, t):
        base = -32.0 if "external monitor" in said[-1] else -2.0
        return HeadSample(t, True, yaw=base + rng.normal(0, 2), pitch=rng.normal(0, 2))

    first_sample_t = {}

    def tracking(frame, t):
        phase = "EXTERNAL" if "external monitor" in said[-1] else "LAPTOP"
        first_sample_t.setdefault(phase, t)
        return track(frame, t)

    calibrate(lambda: FRAME, tracking, clock=c.time, sleep=c.sleep, say=said.append,
              cue=lambda name: cues.append((name, c.time())))
    assert [n for n, _ in cues] == ["EXTERNAL", "LAPTOP", "DONE"]
    assert cues[0][1] < first_sample_t["EXTERNAL"] and cues[1][1] < first_sample_t["LAPTOP"]


def test_calibrate_hands_back_the_raw_samples():
    c, said, samples = FakeClock(), [], {}
    rng = np.random.default_rng(3)

    def track(frame, t):
        base = -32.0 if "external monitor" in said[-1] else -2.0
        return HeadSample(t, True, yaw=base + rng.normal(0, 2), pitch=rng.normal(0, 2))

    calibrate(lambda: FRAME, track, clock=c.time, sleep=c.sleep, say=said.append, samples_out=samples)
    assert set(samples) == {"EXTERNAL", "LAPTOP"} and len(samples["EXTERNAL"]) >= MIN_CAL_SAMPLES


def test_calibrate_lead_in_is_configurable():
    c, said = FakeClock(), []
    rng = np.random.default_rng(4)

    def track(frame, t):
        base = -32.0 if "external monitor" in said[-1] else -2.0
        return HeadSample(t, True, yaw=base + rng.normal(0, 2), pitch=rng.normal(0, 2))

    calibrate(lambda: FRAME, track, clock=c.time, sleep=c.sleep, say=said.append, seconds=6.0, lead_in_s=0.0)
    assert c.now == pytest.approx(12.0, abs=0.2)  # two 6 s phases and no 2 s lead-ins
    assert "(starting in 0 s)" in said[0]
