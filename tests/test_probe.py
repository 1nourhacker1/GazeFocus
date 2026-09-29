import numpy as np
import pytest

from gazefocus.probe import PHASES, format_report, run_probe, summarize_phase
from gazefocus.types import HeadSample


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, dt):
        self.now += max(0.0, dt)


def test_run_probe_collects_per_phase_stats():
    clock, said = FakeClock(), []

    def track(frame, t):
        clock.now += 0.006  # 6 ms "inference"
        prompt = said[-1]
        if "past the LG" in prompt:
            return HeadSample(t=t, face=False)
        yaw = -32.0 if "LG" in prompt else -2.0
        return HeadSample(t=t, face=True, yaw=yaw, pitch=5.0, iris_h=0.1)

    stats = run_probe(
        lambda: np.zeros((2, 2, 3), np.uint8), track,
        clock=clock.time, sleep=clock.sleep, say=said.append, fps=15.0, countdown_s=2.0,
    )
    by = {s.name: s for s in stats}
    assert [s.name for s in stats] == [p[0] for p in PHASES]
    assert by["LAPTOP"].yaw_mean == -2.0 and by["LG"].yaw_mean == -32.0
    assert by["PAST_LG"].face_frames == 0 and by["PAST_LG"].yaw_mean is None
    assert 70 <= by["LAPTOP"].frames <= 76  # about 5 s at 15 FPS
    assert by["LG"].ms_p50 == pytest.approx(6.0)


def test_summarize_empty_phase():
    s = summarize_phase("X", [], [])
    assert s.frames == 0 and s.ms_p50 is None


def test_report_mentions_sign_and_budget():
    stats = [
        summarize_phase("LAPTOP", [HeadSample(0, True, yaw=-2.0)], [7.0]),
        summarize_phase("LG", [HeadSample(0, True, yaw=-31.0)], [8.0]),
        summarize_phase("PAST_LG", [HeadSample(0, False)], [6.0]),
    ]
    text = format_report(stats, cpu_total_pct=0.8, backend="MSMF")
    assert "NEGATIVE" in text and "0.8" in text and "MSMF" in text


def test_default_clock_is_high_resolution():
    # time.monotonic ticks every 15.6 ms on Windows (GetTickCount64), which quantized
    # the first M0-A run's timings to 0 / 16 ms. perf_counter has 100 ns resolution.
    import inspect
    import time

    assert inspect.signature(run_probe).parameters["clock"].default is time.perf_counter
