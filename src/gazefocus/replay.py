"""Record HeadSamples + Contexts as JSONL (never video) and replay them through the logic."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable, Iterator

from gazefocus.config import Config
from gazefocus.logic.classifier import ZoneClassifier, ZoneModel
from gazefocus.logic.decider import Context, GazeDecider, reason_category
from gazefocus.types import Decision, HeadSample, Zone


def _ctx_to_dict(ctx: Context) -> dict:
    d = asdict(ctx)
    d["focus_zone"] = ctx.focus_zone.value
    return d


def _ctx_from_dict(d: dict) -> Context:
    d = dict(d)
    d["focus_zone"] = Zone(d["focus_zone"])
    return Context(**d)


class Recorder:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = path.open("w", encoding="utf-8")

    def write(self, sample: HeadSample, ctx: Context) -> None:
        self._f.write(json.dumps({"sample": asdict(sample), "ctx": _ctx_to_dict(ctx)}) + "\n")

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_recording(path: Path) -> Iterator[tuple[HeadSample, Context]]:
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                yield HeadSample(**d["sample"]), _ctx_from_dict(d["ctx"])
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"{path.name} line {n}: {e}") from e


def replay(frames: Iterable[tuple[HeadSample, Context]], model: ZoneModel, cfg: Config = Config()) -> list[Decision]:
    classifier, decider = ZoneClassifier(model, cfg.classifier), GazeDecider(cfg.decider)
    out: list[Decision] = []
    sim_focus: Zone | None = None
    manual_prev: float | None = None
    for sample, ctx in frames:
        # Follow the recording's focus only at the start and when the *user* moved it (a new
        # last_manual_focus_t). Other recorded focus changes are the recording model's own
        # (simulated or real) switches, which a replay with another model must not inherit.
        if sim_focus is None or ctx.last_manual_focus_t != manual_prev:
            sim_focus = ctx.focus_zone
        manual_prev = ctx.last_manual_focus_t
        zone, margin = classifier.update(sample)
        d = decider.step(zone, margin, replace(ctx, focus_zone=sim_focus))
        if d.action == "switch":
            decider.notify_switched(ctx.t)
            sim_focus = d.target
        out.append(d)
    return out


def summarize(decisions: Iterable[Decision]) -> list[str]:
    lines, run = [], None
    for d in decisions:
        margin = "n/a" if d.margin is None else f"{d.margin:+.2f}"
        if d.action == "switch":
            lines.append(f"{d.t:8.2f}s  SWITCH  -> {d.target.value}  (margin {margin})")
            run = None
        elif d.action == "blocked":
            if reason_category(d.reason) != run:
                lines.append(f"{d.t:8.2f}s  blocked -> {d.target.value}: {d.reason}")
                run = reason_category(d.reason)
        else:
            run = None
    return lines
