"""config.toml: typed defaults, forgiving validation, live reload by polling."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class DeciderCfg:
    dwell_ms: int = 500
    typing_freeze_ms: int = 1500
    manual_cooldown_ms: int = 1000
    post_switch_cooldown_ms: int = 400
    cursor_idle_warp_ms: int = 2000


@dataclass(frozen=True)
class ClassifierCfg:
    ema_alpha: float = 0.35
    dead_band: float = 0.25
    face_lost_lg_margin: float = -1.2
    face_lost_memory_s: float = 0.3
    ood_sigma: float = 3.5


@dataclass(frozen=True)
class CameraCfg:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 15
    idle_fps: int = 5
    idle_after_s: int = 120
    battery_fps: int = 10


@dataclass(frozen=True)
class DockCfg:
    enabled: bool = True
    monitor: str = "primary"
    scale: float = 2.625  # 1.75 x 1.5: a 115.5 x 52.5 pill (the user asked for 1.5x, 2026-09-30)
    refraction: bool = True  # the lens rim (M0-C2)


@dataclass(frozen=True)
class HotkeyCfg:
    pause: str = "Ctrl+Alt+G"


@dataclass(frozen=True)
class Config:
    decider: DeciderCfg = field(default_factory=DeciderCfg)
    classifier: ClassifierCfg = field(default_factory=ClassifierCfg)
    camera: CameraCfg = field(default_factory=CameraCfg)
    dock: DockCfg = field(default_factory=DockCfg)
    hotkey: HotkeyCfg = field(default_factory=HotkeyCfg)


def _int(lo: int, hi: int):
    return (lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi), f"an integer {lo}..{hi}"


def _num(lo: float, hi: float, lo_open: bool = False, desc: str | None = None):
    def ok(v):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return False
        return (lo < v if lo_open else lo <= v) and v <= hi

    return ok, desc or f"a number {lo}..{hi}"


def _bool():
    return (lambda v: isinstance(v, bool)), "true or false"


def _text():
    return (lambda v: isinstance(v, str) and v.strip() != ""), "a non-empty string"


_MS = _int(0, 60_000)
RULES = {
    "decider": {f.name: _MS for f in fields(DeciderCfg)},
    "classifier": {
        "ema_alpha": _num(0.0, 1.0, lo_open=True, desc="a number in (0, 1]"),
        "dead_band": _num(0.0, 0.99),
        "face_lost_lg_margin": _num(-5.0, 0.0),
        "face_lost_memory_s": _num(0.0, 5.0),
        "ood_sigma": _num(1.0, 20.0),
    },
    "camera": {
        "index": _int(0, 9),
        "width": _int(160, 3840),
        "height": _int(120, 2160),
        "fps": _int(1, 60),
        "idle_fps": _int(1, 60),
        "idle_after_s": _int(0, 86_400),
        "battery_fps": _int(1, 60),
    },
    "dock": {"enabled": _bool(), "monitor": _text(), "scale": _num(0.5, 4.0), "refraction": _bool()},
    "hotkey": {"pause": _text()},
}


def load_config(path: Path) -> tuple[Config, list[str]]:
    """Never raises on bad content: invalid parts fall back to defaults with a warning."""
    if not path.exists():
        return Config(), []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Config(), [f"could not read config.toml ({e}); using all defaults"]
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return Config(), [f"config.toml is not valid TOML ({e}); using all defaults"]
    cfg, warns = Config(), []
    for section, table in data.items():
        if section not in RULES:
            warns.append(f"unknown section [{section}] (ignored)")
            continue
        if not isinstance(table, dict):
            warns.append(f"[{section}] must be a table (ignored)")
            continue
        current = getattr(cfg, section)
        updates = {}
        for key, value in table.items():
            rule = RULES[section].get(key)
            if rule is None:
                warns.append(f"unknown key [{section}].{key} (ignored)")
                continue
            ok, desc = rule
            default = getattr(current, key)
            if not ok(value):
                warns.append(f"[{section}].{key} = {value!r} must be {desc}; using default {default!r}")
                continue
            updates[key] = float(value) if isinstance(default, float) else value
        cfg = replace(cfg, **{section: replace(current, **updates)})
    return cfg, warns


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"  # TOML booleans are lower-case
    return f'"{v}"' if isinstance(v, str) else repr(v)


def default_toml() -> str:
    cfg = Config()
    lines = ["# GazeFocus settings. Saved changes are picked up live.", ""]
    for sec in fields(Config):
        lines.append(f"[{sec.name}]")
        values = getattr(cfg, sec.name)
        lines += [f"{f.name} = {_fmt(getattr(values, f.name))}" for f in fields(values)]
        lines.append("")
    return "\n".join(lines)


def write_default_config(path: Path) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_toml(), encoding="utf-8")
    return True


class ConfigWatcher:
    """Call poll() periodically (the app does it once a second)."""

    def __init__(self, path: Path, on_change: Callable[[Config, list[str]], None]) -> None:
        self.path, self.on_change = path, on_change
        self._stamp = self._read_stamp()

    def _read_stamp(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def poll(self) -> bool:
        stamp = self._read_stamp()
        if stamp == self._stamp:
            return False
        self._stamp = stamp
        self.on_change(*load_config(self.path))
        return True
