"""Committing a new calibration: shared by `calibrate-cli` and the tray's Recalibrate.

A "too close" result never replaces the current calibration unless forced; a replaced file is
kept as calibration.prev.json; the raw samples are saved next to it for offline refits.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from gazefocus.logic.classifier import ZoneModel, quality
from gazefocus.storage import Calibration, calibration_path, now_iso, save_calibration
from gazefocus.types import HeadSample, recordable
from gazefocus.win.monitors import MonitorInfo, layout_fingerprint, zone_monitors

SAMPLES_FILE = "calibration-samples.jsonl"


@dataclass(frozen=True)
class CommitResult:
    saved: bool
    message: str


def save_samples(path: Path, samples: dict[str, Sequence[HeadSample]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for screen, items in samples.items():
            for s in items:
                f.write(json.dumps({"screen": screen, **recordable(s)}) + "\n")


def load_samples(path: Path) -> dict[str, list[HeadSample]]:
    out: dict[str, list[HeadSample]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out.setdefault(d.pop("screen"), []).append(HeadSample(**d))
    return out


def commit_calibration(
    model: ZoneModel,
    counts: dict,
    samples: dict[str, Sequence[HeadSample]] | None,
    *,
    monitors: Sequence[MonitorInfo],
    dock_monitor: str,
    camera: dict,
    force: bool = False,
    path: Path | None = None,
) -> CommitResult:
    q = quality(model.separation)
    if q == "too close" and not force:
        return CommitResult(
            False,
            f"calibration too close ({model.separation:.1f} sigma): turn your head a little more toward each "
            "screen, or move the LG closer to the laptop. The previous calibration was kept.",
        )
    path = path or calibration_path()
    cal = Calibration(
        created=now_iso(),
        layout_fingerprint=layout_fingerprint(monitors),
        monitors=tuple(monitors),
        zone_monitors=zone_monitors(monitors, dock_monitor),
        camera=dict(camera),
        model=model,
        samples=dict(counts),
    )
    if path.exists():
        shutil.copyfile(path, path.with_name("calibration.prev.json"))
    save_calibration(cal, path)
    if samples:
        save_samples(path.with_name(SAMPLES_FILE), samples)
    return CommitResult(
        True,
        f"saved {path} ({model.separation:.1f} sigma, {q}; mean yaw LG {model.mean_lg[0]:+.1f}, "
        f"laptop {model.mean_laptop[0]:+.1f})",
    )
