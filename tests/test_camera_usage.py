from gazefocus.win.camera_usage import (
    CameraUser,
    apps_using_camera,
    camera_busy_message,
    read_consent_store,
)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ENTRIES = [
    ("Microsoft.WindowsCamera_8wekyb3d8bbwe", True, {"LastUsedTimeStart": 5, "LastUsedTimeStop": 0}),
    (CHROME, False, {"LastUsedTimeStart": 9, "LastUsedTimeStop": 0}),
    (r"C:\Apps\Discord.exe", False, {"LastUsedTimeStart": 3, "LastUsedTimeStop": 4}),
    ("Some.NeverUsed_abc", True, {}),
    ("Zero.Start_abc", True, {"LastUsedTimeStart": 0, "LastUsedTimeStop": 0}),
]


def test_reports_only_apps_with_open_sessions():
    users = apps_using_camera(ENTRIES)
    assert users == [
        CameraUser("Microsoft.WindowsCamera_8wekyb3d8bbwe", True),
        CameraUser(CHROME, False),
    ]


def test_exclude_is_case_insensitive():
    users = apps_using_camera(ENTRIES, exclude=[CHROME.upper()])
    assert [u.app for u in users] == ["Microsoft.WindowsCamera_8wekyb3d8bbwe"]


def test_message_names_short_app_names():
    msg = camera_busy_message(apps_using_camera(ENTRIES))
    assert "chrome.exe" in msg and "Microsoft.WindowsCamera" in msg


def test_stale_entries_are_only_hints():  # Review Focus #2
    msg = camera_busy_message([CameraUser(CHROME, False)])
    assert "Possibly" in msg and "stale" in msg


def test_message_when_nobody_reported():
    msg = camera_busy_message([])
    assert "no other app" in msg


def test_real_registry_read_is_well_formed():
    for app, packaged, values in read_consent_store():
        assert isinstance(app, str) and isinstance(packaged, bool) and isinstance(values, dict)
