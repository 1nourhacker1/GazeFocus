"""gazefocus.log and decisions.log (spec §10): one line per decision that matters, never 15/s."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from gazefocus.logic.decider import reason_category
from gazefocus.types import Decision
from gazefocus.win.focus import SwitchResult

FORMAT = "%(asctime)s %(message)s"


def setup_logging(folder: Path, *, to_stderr: bool = True) -> tuple[logging.Logger, logging.Logger]:
    """(app log, decision log), each a rotating file of 5 x 1 MB under `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    loggers = []
    for name, file in (("gazefocus", "gazefocus.log"), ("gazefocus.decisions", "decisions.log")):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        handler = RotatingFileHandler(folder / file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)
        loggers.append(logger)
    if to_stderr:
        err = logging.StreamHandler()
        err.setFormatter(logging.Formatter(FORMAT))
        loggers[0].addHandler(err)
    return loggers[0], loggers[1]


class DecisionLogger:
    """Logs every switch, the first frame of each blocked run, and every switch outcome."""

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger
        self._run: str | None = None

    def decision(self, d: Decision) -> bool:
        margin = "n/a" if d.margin is None else f"{d.margin:+.2f}"
        if d.action == "switch":
            self._run = None
            self._log.info("zone=%s margin=%s -> SWITCH %s", d.zone.value, margin, d.target.value)
            return True
        if d.action == "blocked":
            category = reason_category(d.reason)
            if category == self._run:
                return False
            self._run = category
            self._log.info("zone=%s margin=%s -> BLOCKED(%s)", d.zone.value, margin, d.reason)
            return True
        self._run = None
        return False

    def outcome(self, target: str, title: str, result: SwitchResult) -> None:
        if result.ok:
            self._log.info("   focused %r on %s via %s in %.0f ms", title, target, result.method, result.ms)
        else:
            self._log.info("   FAIL %r on %s: %s (%.0f ms)", title, target, result.detail, result.ms)

    def note(self, text: str) -> None:
        self._log.info("   %s", text)
