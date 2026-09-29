"""gazefocus command line. Plan 1: terminal tools and a dry run (nothing is focused yet)."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

SELF = (sys.executable, getattr(sys, "_base_executable", ""))
EXIT_OK, EXIT_BAD_INPUT, EXIT_CAMERA, EXIT_CALIBRATION = 0, 1, 2, 3


def _config():
    from gazefocus.config import load_config, write_default_config
    from gazefocus.paths import app_dir

    path = app_dir() / "config.toml"
    write_default_config(path)
    cfg, warnings = load_config(path)
    for w in warnings:
        print(f"config: {w}", file=sys.stderr)
    return cfg


def _open_camera(cfg):
    from gazefocus.vision.camera import CameraSource
    from gazefocus.win.camera_usage import camera_busy_message

    cam = CameraSource(cfg.camera.index, cfg.camera.width, cfg.camera.height)
    if not cam.open():
        print(camera_busy_message(exclude=SELF), file=sys.stderr)
        return None
    return cam


BEEPS = {"LG": 1, "LAPTOP": 2, "DONE": 3}


def _beep(name: str) -> None:
    """1 beep = look at the LG, 2 = look at the laptop, 3 = done."""
    import winsound

    # 450 ms: idle laptop audio needs ~200-300 ms to wake, so short tones get swallowed (desk session)
    for _ in range(BEEPS.get(name, 0)):
        winsound.Beep(1046 if name == "DONE" else 880, 450)


def _tracker():
    from gazefocus.paths import model_path
    from gazefocus.vision.tracker import HeadTracker

    return HeadTracker(model_path())


def cmd_probe(args) -> int:
    from gazefocus import probe

    return probe.main()


def cmd_live(args) -> int:
    from gazefocus import viewer

    return viewer.main()


def cmd_calibrate(args) -> int:
    import shutil

    from gazefocus.logic.classifier import quality
    from gazefocus.runtime import calibrate
    from gazefocus.storage import Calibration, calibration_path, now_iso, save_calibration
    from gazefocus.win.monitors import enumerate_monitors, layout_fingerprint, zone_monitors

    cfg = _config()
    monitors = enumerate_monitors()
    zones = zone_monitors(monitors, cfg.dock.monitor)
    if zones["LG"] is None:
        print("note: the LG is not connected; its position is calibrated anyway (dry-run use until it is plugged in)")
    cam = _open_camera(cfg)
    if cam is None:
        return EXIT_CAMERA
    backend, tracker = cam.backend, _tracker()
    try:
        print("listen for beeps: 1 = look at the LG, 2 = look at the laptop, 3 = done")
        model, counts = calibrate(cam.read, tracker.process, seconds=args.seconds, fps=cfg.camera.fps, cue=_beep)
    except ValueError as e:
        print(f"calibration failed: {e}", file=sys.stderr)
        return EXIT_CALIBRATION
    finally:
        cam.release()
        tracker.close()
    cal = Calibration(
        created=now_iso(),
        layout_fingerprint=layout_fingerprint(monitors),
        monitors=tuple(monitors),
        zone_monitors=zones,
        camera={"index": cfg.camera.index, "width": cfg.camera.width, "height": cfg.camera.height, "backend": backend},
        model=model,
        samples=counts,
    )
    if quality(model.separation) == "too close" and not args.force:
        print(
            f"calibration too close ({model.separation:.1f} sigma): turn your head a little more toward each "
            "screen, or move the LG closer to the laptop. The previous calibration was kept; "
            "rerun with --force to save this one anyway.",
            file=sys.stderr,
        )
        return EXIT_CALIBRATION
    path = calibration_path()
    if path.exists():
        shutil.copyfile(path, path.with_name("calibration.prev.json"))
    save_calibration(cal, path)
    print(f"saved {path} (mean yaw LG {model.mean_lg[0]:+.1f}, laptop {model.mean_laptop[0]:+.1f})")
    return EXIT_OK


def _matching_calibration():
    from gazefocus.storage import calibration_path, load_if_matches
    from gazefocus.win.monitors import enumerate_monitors, layout_fingerprint

    cal, warning = load_if_matches(calibration_path(), layout_fingerprint(enumerate_monitors()))
    if cal is None:
        print(warning or "not calibrated yet: run `gazefocus calibrate-cli` first", file=sys.stderr)
    return cal


def cmd_watch(args) -> int:
    from gazefocus.logic.classifier import ZoneClassifier
    from gazefocus.logic.decider import GazeDecider
    from gazefocus.replay import Recorder
    from gazefocus.runtime import watch_loop

    cfg = _config()
    cal = _matching_calibration()
    if cal is None:
        return EXIT_CALIBRATION
    cam = _open_camera(cfg)
    if cam is None:
        return EXIT_CAMERA
    tracker = _tracker()
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    recorder = Recorder(Path(args.record)) if args.record else None
    print("watching (dry run: nothing is focused yet). Ctrl+C to stop.")
    try:
        watch_loop(
            cam.read, tracker.process, ZoneClassifier(cal.model, cfg.classifier), GazeDecider(cfg.decider),
            seconds=args.seconds, fps=cfg.camera.fps, recorder=recorder, should_stop=lambda: stop["now"],
        )
    finally:
        cam.release()
        tracker.close()
        if recorder is not None:
            recorder.close()
    return EXIT_OK


def cmd_bench(args) -> int:
    from gazefocus.runtime import bench_loop

    cfg = _config()
    cam = _open_camera(cfg)
    if cam is None:
        return EXIT_CAMERA
    tracker = _tracker()
    try:
        report = bench_loop(cam.read, tracker.process, seconds=args.minutes * 60.0, fps=cfg.camera.fps)
    finally:
        cam.release()
        tracker.close()
    print(f"whole run: {report.line()}")
    return EXIT_OK


def cmd_replay(args) -> int:
    from gazefocus.replay import read_recording, replay, summarize
    from gazefocus.storage import calibration_path, load_calibration

    cfg = _config()
    cal, warning = load_calibration(calibration_path())
    if cal is None:
        print(warning or "not calibrated yet: run `gazefocus calibrate-cli` first", file=sys.stderr)
        return EXIT_CALIBRATION
    try:
        decisions = replay(read_recording(Path(args.file)), cal.model, cfg)
    except (OSError, ValueError) as e:
        print(f"replay failed: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    print("\n".join(summarize(decisions)) or "(no switches or blocks)")
    print(f"{len(decisions)} frames, {sum(d.action == 'switch' for d in decisions)} switches")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="gazefocus", description="Webcam focus-follows-gaze (Plan 1: terminal tools, dry run).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="guided tracking and speed measurement (spike M0-A)").set_defaults(fn=cmd_probe)
    sub.add_parser("live", help="live mirrored camera view with the head-pose overlay").set_defaults(fn=cmd_live)
    c = sub.add_parser("calibrate-cli", help="terminal calibration: LG, then laptop")
    c.add_argument("--seconds", type=float, default=6.0)
    c.add_argument("--force", action="store_true", help="save even a 'too close' calibration")
    c.set_defaults(fn=cmd_calibrate)
    w = sub.add_parser("watch", help="dry run: which screen you look at, and what GazeFocus would do")
    w.add_argument("--record", metavar="FILE")
    w.add_argument("--seconds", type=float)
    w.set_defaults(fn=cmd_watch)
    b = sub.add_parser("bench", help="measure CPU, RAM and latency against the spec budget")
    b.add_argument("--minutes", type=float, default=10.0)
    b.set_defaults(fn=cmd_bench)
    r = sub.add_parser("replay", help="run a recording through the classifier and decider")
    r.add_argument("file")
    r.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
