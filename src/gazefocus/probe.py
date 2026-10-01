"""Guided M0-A probe: per-phase head-pose statistics and per-frame timing."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from gazefocus.types import HeadSample

PHASES = (
    ("LAPTOP", "Look at the middle of the LAPTOP screen", 5.0),
    ("EXTERNAL", "Turn to where the external monitor normally sits and look at its middle", 5.0),
    ("PAST_EXTERNAL", "Keep turning past the external monitor, as far as is comfortable", 4.0),
)


@dataclass(frozen=True)
class PhaseStats:
    name: str
    frames: int
    face_frames: int
    yaw_mean: float | None
    yaw_min: float | None
    yaw_max: float | None
    pitch_mean: float | None
    iris_h_mean: float | None
    ms_p50: float | None
    ms_p95: float | None


def summarize_phase(name: str, samples: list[HeadSample], ms: list[float]) -> PhaseStats:
    faces = [s for s in samples if s.face]

    def mean(vals):
        return float(np.mean(vals)) if vals else None

    yaws = [s.yaw for s in faces]
    return PhaseStats(
        name=name,
        frames=len(samples),
        face_frames=len(faces),
        yaw_mean=mean(yaws),
        yaw_min=min(yaws) if yaws else None,
        yaw_max=max(yaws) if yaws else None,
        pitch_mean=mean([s.pitch for s in faces]),
        iris_h_mean=mean([s.iris_h for s in faces]),
        ms_p50=float(np.percentile(ms, 50)) if ms else None,
        ms_p95=float(np.percentile(ms, 95)) if ms else None,
    )


def run_probe(
    read_frame: Callable[[], np.ndarray | None],
    track: Callable[[np.ndarray, float], HeadSample],
    *,
    clock: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
    fps: float = 15.0,
    phases=PHASES,
    countdown_s: float = 2.0,
) -> list[PhaseStats]:
    period = 1.0 / fps
    out = []
    for name, prompt, seconds in phases:
        say(f">>> {prompt}  (starting in {countdown_s:.0f} s)")
        sleep(countdown_s)
        samples, ms = [], []
        end = clock() + seconds
        while (start := clock()) < end:
            frame = read_frame()
            if frame is None:
                sleep(period)
                continue
            t0 = clock()
            samples.append(track(frame, t0))
            ms.append((clock() - t0) * 1000.0)
            spare = period - (clock() - start)
            if spare > 0:
                sleep(spare)
        stats = summarize_phase(name, samples, ms)
        say(f"    {name}: {stats.frames} frames, face in {stats.face_frames} of them")
        out.append(stats)
    return out


def _f(v, fmt="{:.1f}"):
    return "-" if v is None else fmt.format(v)


def format_report(stats: list[PhaseStats], cpu_total_pct: float, backend: str | None) -> str:
    lines = [
        f"camera backend: {backend}   process CPU (share of all cores): {cpu_total_pct:.1f}%",
        "",
        "| phase | frames | face % | yaw mean | yaw min..max | pitch mean | iris_h mean | ms p50 | ms p95 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in stats:
        pct = 100.0 * s.face_frames / s.frames if s.frames else 0.0
        lines.append(
            f"| {s.name} | {s.frames} | {pct:.0f} | {_f(s.yaw_mean)} | {_f(s.yaw_min)}..{_f(s.yaw_max)} | "
            f"{_f(s.pitch_mean)} | {_f(s.iris_h_mean, '{:.2f}')} | {_f(s.ms_p50)} | {_f(s.ms_p95)} |"
        )
    by = {s.name: s for s in stats}
    lap, ext = by.get("LAPTOP"), by.get("EXTERNAL")
    if lap and ext and lap.yaw_mean is not None and ext.yaw_mean is not None:
        delta = ext.yaw_mean - lap.yaw_mean
        sign = "NEGATIVE" if delta < 0 else "POSITIVE"
        lines += ["", f"Turning toward the external monitor makes yaw {sign} (EXTERNAL - LAPTOP = {delta:+.1f} deg)."]
    return "\n".join(lines)


def main() -> int:
    from gazefocus.paths import model_path
    from gazefocus.vision.camera import CameraSource
    from gazefocus.vision.tracker import HeadTracker
    from gazefocus.win.camera_usage import camera_busy_message

    cam = CameraSource()
    if not cam.open():
        print(camera_busy_message(exclude=(sys.executable, getattr(sys, "_base_executable", ""))), file=sys.stderr)
        return 2
    backend = cam.backend
    tracker = HeadTracker(model_path())
    cpu0, wall0 = time.process_time(), time.perf_counter()
    try:
        stats = run_probe(cam.read, tracker.process)
    finally:
        cam.release()
        tracker.close()
    cpu = (time.process_time() - cpu0) / (time.perf_counter() - wall0) / (os.cpu_count() or 1) * 100.0
    print(format_report(stats, cpu, backend))
    return 0


if __name__ == "__main__":
    sys.exit(main())
