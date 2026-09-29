"""Camera-driven loops for the CLI. Plan 2 moves the frame loop onto the Qt app's camera thread."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from gazefocus.logic.classifier import ZoneClassifier, ZoneModel, fit_zone_model, quality
from gazefocus.logic.decider import Context, GazeDecider
from gazefocus.types import Decision, HeadSample, Zone

ReadFrame = Callable[[], "np.ndarray | None"]
Track = Callable[[np.ndarray, float], HeadSample]

MIN_CAL_SAMPLES = 40
CAL_PHASES = (
    ("LG", "Look at the LG (turn toward where it sits) and let your eyes wander over all of it"),
    ("LAPTOP", "Now look at the LAPTOP screen and let your eyes wander over all of it"),
)


class Pacer:
    def __init__(self, fps: float, clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
        self.period, self.clock, self.sleep = 1.0 / fps, clock, sleep
        self._next: float | None = None

    def wait(self) -> None:
        now = self.clock()
        if self._next is None:
            self._next = now
        self._next += self.period
        if self._next > now:
            self.sleep(self._next - now)
        else:
            self._next = now  # fell behind: never try to catch up


def collect_phase(
    read_frame: ReadFrame, track: Track, seconds: float, *,
    clock=time.perf_counter, sleep=time.sleep, fps: float = 15.0, settle_s: float = 1.0,
) -> list[HeadSample]:
    pacer, start, out = Pacer(fps, clock, sleep), clock(), []
    while (now := clock()) - start < seconds:
        frame = read_frame()
        if frame is not None:
            sample = track(frame, now)
            if now - start >= settle_s:
                out.append(sample)
        pacer.wait()
    return out


def calibrate(
    read_frame: ReadFrame, track: Track, *, seconds: float = 6.0,
    clock=time.perf_counter, sleep=time.sleep, fps: float = 15.0, say=print,
    cue: Callable[[str], None] = lambda name: None,
) -> tuple[ZoneModel, dict]:
    collected = {}
    for name, prompt in CAL_PHASES:
        say(f">>> {prompt}  (starting in 2 s)")
        cue(name)  # audible: the user may be looking at the other screen, not at this prompt
        sleep(2.0)
        collected[name] = collect_phase(read_frame, track, seconds, clock=clock, sleep=sleep, fps=fps)
    cue("DONE")
    counts = {k: sum(s.face for s in v) for k, v in collected.items()}
    if min(counts.values()) < MIN_CAL_SAMPLES:
        raise ValueError(
            f"too few face samples (LG={counts['LG']}, LAPTOP={counts['LAPTOP']}; need {MIN_CAL_SAMPLES} each). "
            "Is the room too dark, or were you out of view?"
        )
    model = fit_zone_model(collected["LG"], collected["LAPTOP"])
    say(f"separation {model.separation:.1f} sigma ({quality(model.separation)})")
    return model, counts


def margin_bar(margin: float | None, width: int = 21) -> str:
    cells = ["-"] * width
    if margin is not None:
        pos = round((max(-2.0, min(2.0, margin)) + 2.0) / 4.0 * (width - 1))
        cells[pos] = "o"
    return "LG[" + "".join(cells) + "]LAPTOP"


def format_status(d: Decision, focus: Zone) -> str:
    m = "  n/a" if d.margin is None else f"{d.margin:+.2f}"
    tail = f"  SWITCH -> {d.target.value}" if d.action == "switch" else (
        f"  blocked: {d.reason}" if d.action == "blocked" else ""
    )
    return f"{d.t:8.2f}s  gaze={d.zone.value:<7} margin={m} {margin_bar(d.margin)}  focus={focus.value}{tail}"


def watch_loop(
    read_frame: ReadFrame, track: Track, classifier: ZoneClassifier, decider: GazeDecider, *,
    seconds: float | None = None, clock=time.perf_counter, sleep=time.sleep, fps: float = 15.0,
    say=print, recorder=None, should_stop: Callable[[], bool] = lambda: False,
) -> list[Decision]:
    """Dry run: simulated focus (starts on LAPTOP, follows every switch); no input information yet."""
    pacer, start, focus, out, last_zone = Pacer(fps, clock, sleep), clock(), Zone.LAPTOP, [], None
    while not should_stop() and (seconds is None or clock() - start < seconds):
        frame = read_frame()
        if frame is not None:
            t = clock()
            sample = track(frame, t)
            zone, margin = classifier.update(sample)
            ctx = Context(t=t, focus_zone=focus)
            if recorder is not None:
                recorder.write(sample, ctx)
            d = decider.step(zone, margin, ctx)
            if d.action == "switch":
                decider.notify_switched(t)
                focus = d.target
            if zone != last_zone or d.action != "none":
                say(format_status(d, focus))
                last_zone = zone
            out.append(d)
        pacer.wait()
    return out


@dataclass(frozen=True)
class BenchReport:
    seconds: float
    frames: int
    fps: float
    ms_p50: float | None
    ms_p95: float | None
    cpu_pct: float
    rss_mb: float

    def verdict(self) -> str:
        cpu = "PASS" if self.cpu_pct <= 2.0 else "FAIL"
        rss = "PASS" if self.rss_mb <= 300.0 else "FAIL"
        return f"CPU {self.cpu_pct:.2f}% (<=2%) {cpu} | RSS {self.rss_mb:.0f} MB (<=300) {rss}"

    def line(self) -> str:
        p50 = "-" if self.ms_p50 is None else f"{self.ms_p50:.1f}"
        p95 = "-" if self.ms_p95 is None else f"{self.ms_p95:.1f}"
        return f"{self.seconds:6.0f}s  fps={self.fps:4.1f}  ms p50={p50} p95={p95}  {self.verdict()}"


def _report(seconds, frames, ms, cpu_seconds, cores, rss) -> BenchReport:
    seconds = max(seconds, 1e-9)
    return BenchReport(
        seconds=seconds,
        frames=frames,
        fps=frames / seconds,
        ms_p50=float(np.percentile(ms, 50)) if ms else None,
        ms_p95=float(np.percentile(ms, 95)) if ms else None,
        cpu_pct=cpu_seconds / seconds / cores * 100.0,
        rss_mb=rss,
    )


def _default_rss_mb() -> float:
    import psutil

    return psutil.Process().memory_info().rss / 2**20


def bench_loop(
    read_frame: ReadFrame, track: Track, *, seconds: float, report_every: float = 60.0,
    clock=time.perf_counter, sleep=time.sleep, fps: float = 15.0, cpu_time=time.process_time,
    rss_mb=_default_rss_mb, cores: int = os.cpu_count() or 1, say=print,
) -> BenchReport:
    pacer = Pacer(fps, clock, sleep)
    start, cpu_start = clock(), cpu_time()
    all_ms, frames = [], 0
    win_start, win_cpu, win_ms, win_frames = start, cpu_start, [], 0
    while clock() - start < seconds:
        frame = read_frame()
        if frame is not None:
            t0 = clock()
            track(frame, t0)
            ms = (clock() - t0) * 1000.0
            all_ms.append(ms)
            win_ms.append(ms)
            frames += 1
            win_frames += 1
        now = clock()
        if now - win_start >= report_every:
            say(_report(now - win_start, win_frames, win_ms, cpu_time() - win_cpu, cores, rss_mb()).line())
            win_start, win_cpu, win_ms, win_frames = now, cpu_time(), [], 0
        pacer.wait()
    return _report(clock() - start, frames, all_ms, cpu_time() - cpu_start, cores, rss_mb())
