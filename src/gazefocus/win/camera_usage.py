"""Which apps Windows records as using the webcam.

Only a hint: records go stale when an app crashes, so consult this only after
opening the camera has already failed.
"""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from typing import Iterable

BASE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"

Entry = tuple[str, bool, dict]  # (app, packaged, registry values)


@dataclass(frozen=True)
class CameraUser:
    app: str
    packaged: bool


def _subkeys(key) -> list[str]:
    out, i = [], 0
    while True:
        try:
            out.append(winreg.EnumKey(key, i))
        except OSError:
            return out
        i += 1


def _values(key) -> dict:
    out, i = {}, 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
        except OSError:
            return out
        out[name] = value
        i += 1


def read_consent_store() -> list[Entry]:
    try:
        base = winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE)
    except OSError:
        return []
    entries: list[Entry] = []
    with base:
        for name in _subkeys(base):
            try:
                with winreg.OpenKey(base, name) as key:
                    if name == "NonPackaged":
                        for exe in _subkeys(key):
                            try:
                                with winreg.OpenKey(key, exe) as sub:
                                    entries.append((exe.replace("#", "\\"), False, _values(sub)))
                            except OSError:
                                continue
                    else:
                        entries.append((name, True, _values(key)))
            except OSError:
                continue  # one unreadable entry must not break the busy-camera message
    return entries


def apps_using_camera(entries: Iterable[Entry] | None = None, exclude: Iterable[str] = ()) -> list[CameraUser]:
    if entries is None:
        entries = read_consent_store()
    skip = {e.lower() for e in exclude if e}
    users = []
    for app, packaged, values in entries:
        start, stop = values.get("LastUsedTimeStart"), values.get("LastUsedTimeStop")
        if isinstance(start, int) and start > 0 and stop == 0 and app.lower() not in skip:
            users.append(CameraUser(app, packaged))
    return users


def _short(user: CameraUser) -> str:
    return user.app.split("_", 1)[0] if user.packaged else user.app.rsplit("\\", 1)[-1]


def camera_busy_message(users: list[CameraUser] | None = None, exclude: Iterable[str] = ()) -> str:
    if users is None:
        users = apps_using_camera(exclude=exclude)
    if not users:
        return (
            "Could not open the camera, and Windows reports no other app using it. "
            "Is another GazeFocus command (e.g. `gazefocus run`) holding it? "
            "Otherwise check Settings > Privacy & security > Camera."
        )
    names = ", ".join(_short(u) for u in users)
    return (
        f"Could not open the camera. Possibly in use by: {names}. "
        "(Windows' record can be stale if an app crashed.)"
    )
