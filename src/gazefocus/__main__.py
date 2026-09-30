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


from gazefocus.cues import beep as _beep  # noqa: E402  (kept importable as cli._beep)


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
    from gazefocus.calibration import commit_calibration
    from gazefocus.runtime import calibrate
    from gazefocus.win.monitors import enumerate_monitors, zone_monitors

    cfg = _config()
    monitors = enumerate_monitors()
    zones = zone_monitors(monitors, cfg.dock.monitor)
    if zones["LG"] is None:
        print("note: the LG is not connected; its position is calibrated anyway (dry-run use until it is plugged in)")
    cam = _open_camera(cfg)
    if cam is None:
        return EXIT_CAMERA
    backend, tracker = cam.backend, _tracker()
    samples: dict = {}
    try:
        print("listen for beeps: 1 = look at the LG, 2 = look at the laptop, 3 = done")
        model, counts = calibrate(
            cam.read, tracker.process, seconds=args.seconds, fps=cfg.camera.fps, cue=_beep, samples_out=samples
        )
    except ValueError as e:
        print(f"calibration failed: {e}", file=sys.stderr)
        return EXIT_CALIBRATION
    finally:
        cam.release()
        tracker.close()
    result = commit_calibration(
        model, counts, samples, monitors=monitors, dock_monitor=cfg.dock.monitor, force=args.force,
        camera={"index": cfg.camera.index, "width": cfg.camera.width, "height": cfg.camera.height, "backend": backend},
    )
    if not result.saved:
        print(f"{result.message} Rerun with --force to save this one anyway.", file=sys.stderr)
        return EXIT_CALIBRATION
    print(result.message)
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


def configure_console() -> None:
    """Window titles can hold characters the console code page lacks (e.g. cp1252 and '\u25d0')."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_run(args) -> int:
    from gazefocus.app.main import run_app

    return run_app(seconds=args.seconds)


def cmd_dock_demo(args) -> int:
    from gazefocus.dock.demo import run_demo

    return run_demo(seconds=args.seconds)


def _diag_zone_devices() -> tuple[dict, str]:
    """{zone: device} from a matching calibration, else primary = LAPTOP and the other = LG."""
    from gazefocus.storage import calibration_path, load_if_matches
    from gazefocus.win.monitors import enumerate_monitors, layout_fingerprint

    monitors = enumerate_monitors()
    cal, _ = load_if_matches(calibration_path(), layout_fingerprint(monitors))
    if cal is not None:
        by_id = {m.id: m.device for m in monitors}
        return {z: by_id.get(i) for z, i in cal.zone_monitors.items()}, "calibration"
    primary = next((m.device for m in monitors if m.primary), None)
    others = [m.device for m in monitors if not m.primary]
    return {"LAPTOP": primary, "LG": others[0] if len(others) == 1 else None}, "primary/other guess"


def cmd_diag(args) -> int:
    import time as _time

    from gazefocus.win import windows
    from gazefocus.win.focus import bring_to_front
    from gazefocus.win.monitors import enumerate_monitors, layout_fingerprint

    if args.what == "monitors":
        monitors = enumerate_monitors()
        for m in monitors:
            print(f"{m.device}  primary={m.primary}  rect={m.rect}  work={m.work}\n    id={m.id}")
        zones, source = _diag_zone_devices()
        print(f"fingerprint {layout_fingerprint(monitors)}   zones ({source}): {zones}")
        return EXIT_OK
    if args.what == "windows":
        by_device: dict = {}
        for hwnd in windows.top_level_windows():
            f = windows.window_facts(hwnd)
            ok, reason = windows.is_switch_target(f)
            if ok or args.all:
                by_device.setdefault(f.device, []).append((f, reason))
        for device, items in by_device.items():
            print(f"{device}:")
            for f, reason in items:
                print(f"  {f.hwnd:>10}  {reason:<16} {f.class_name[:28]:<28} {f.title[:60]}")
        return EXIT_OK
    zones, source = _diag_zone_devices()
    device = zones.get(args.zone)
    if device is None:
        print(f"{args.zone} is not connected (zones from {source}: {zones})")
        return EXIT_BAD_INPUT
    if args.delay > 0:
        print(f"switching to {args.zone} ({device}) in {args.delay:.0f} s: click a window on the OTHER screen now")
        _time.sleep(args.delay)
    hwnd = windows.choose_target(device, [], windows.window_facts, windows.top_level_windows)
    if hwnd is None:
        print(f"no window to focus on {args.zone}")
        return EXIT_BAD_INPUT
    title = windows.window_facts(hwnd).title
    result = bring_to_front(hwnd)
    print(f"{'OK' if result.ok else 'FAILED'}: {title!r} via {result.method} in {result.ms:.0f} ms {result.detail}")
    return EXIT_OK if result.ok else EXIT_BAD_INPUT


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
    run = sub.add_parser("run", help="the GazeFocus background app (tray icon; focus follows your gaze)")
    run.add_argument("--seconds", type=float, help="quit after this many seconds (smoke tests)")
    run.set_defaults(fn=cmd_run)
    dd = sub.add_parser("dock-demo", help="show the dock cycling through every state (no camera)")
    dd.add_argument("--seconds", type=float, help="quit after this many seconds")
    dd.set_defaults(fn=cmd_dock_demo)
    d = sub.add_parser("diag", help="check the Windows side: monitors, windows, a focus switch")
    dsub = d.add_subparsers(dest="what", required=True)
    dsub.add_parser("monitors", help="monitor layout, ids, fingerprint and zone mapping")
    dw = dsub.add_parser("windows", help="focus targets per monitor, in Z-order")
    dw.add_argument("--all", action="store_true", help="also list rejected windows with the reason")
    df = dsub.add_parser("focus", help="focus the top window on a screen (spike M0-B)")
    df.add_argument("zone", choices=("LAPTOP", "LG"))
    df.add_argument("--delay", type=float, default=3.0, help="seconds to click elsewhere first")
    d.set_defaults(fn=cmd_diag)
    configure_console()
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
