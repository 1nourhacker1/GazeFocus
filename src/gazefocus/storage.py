"""calibration.json: validated save/load; only used while the monitor layout still matches."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from gazefocus.logic.classifier import FEATURES, ZoneModel
from gazefocus.paths import app_dir
from gazefocus.win.monitors import MonitorInfo

VERSION = 2  # v2 (2026-09-29): 3 features + per-feature sd; v1 files must be recalibrated


@dataclass(frozen=True)
class Calibration:
    created: str
    layout_fingerprint: str
    monitors: tuple[MonitorInfo, ...]
    zone_monitors: dict  # {"LAPTOP": id | None, "EXTERNAL": id | None}
    camera: dict  # {"index", "width", "height", "backend"}
    model: ZoneModel
    samples: dict  # {"EXTERNAL": n, "LAPTOP": n}
    version: int = VERSION


def calibration_path() -> Path:
    return app_dir() / "calibration.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_calibration(cal: Calibration, path: Path) -> None:
    data = {
        "version": cal.version,
        "created": cal.created,
        "layout": {"fingerprint": cal.layout_fingerprint, "monitors": [asdict(m) for m in cal.monitors]},
        "zone_monitors": cal.zone_monitors,
        "camera": cal.camera,
        "model": cal.model.to_dict(),
        "samples": cal.samples,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_calibration(path: Path) -> tuple[Calibration | None, str | None]:
    if not path.exists():
        return None, None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("version") != VERSION:
            return None, f"calibration.json version {d.get('version')!r} is not supported; please recalibrate"
        monitors = tuple(
            MonitorInfo(m["device"], m["id"], tuple(m["rect"]), tuple(m["work"]), bool(m["primary"]))
            for m in d["layout"]["monitors"]
        )
        model = ZoneModel.from_dict(d["model"])
        values = (*model.w, model.b, model.separation, *model.sd)
        sizes = {len(model.w), len(model.sd), len(model.mean_external), len(model.mean_laptop)}
        if sizes != {len(FEATURES)} or not all(math.isfinite(v) for v in values) or min(model.sd) <= 0:
            raise ValueError("model has non-finite or wrong-sized weights")
        return (
            Calibration(
                created=str(d["created"]),
                layout_fingerprint=str(d["layout"]["fingerprint"]),
                monitors=monitors,
                zone_monitors=dict(d["zone_monitors"]),
                camera=dict(d["camera"]),
                model=model,
                samples=dict(d["samples"]),
            ),
            None,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:  # JSONDecodeError is a ValueError
        return None, f"calibration.json is unreadable ({type(e).__name__}: {e}); please recalibrate"


def load_if_matches(path: Path, fingerprint: str) -> tuple[Calibration | None, str | None]:
    cal, warning = load_calibration(path)
    if cal is None:
        return None, warning
    if cal.layout_fingerprint != fingerprint:
        return None, "monitor layout changed since calibration; please recalibrate"
    return cal, None
