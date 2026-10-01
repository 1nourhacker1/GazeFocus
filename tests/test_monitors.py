from gazefocus.win.monitors import MonitorInfo, enumerate_monitors, layout_fingerprint, zone_monitors

LAP = MonitorInfo(r"\\.\DISPLAY1", "id-lap", (0, 0, 2560, 1600), (0, 0, 2560, 1552), True)
EXTERNAL = MonitorInfo(r"\\.\DISPLAY5", "id-ext", (-1920, -302, 0, 778), (-1920, -302, 0, 738), False)


def test_fingerprint_is_order_independent_and_sensitive():
    assert layout_fingerprint([LAP, EXTERNAL]) == layout_fingerprint([EXTERNAL, LAP])
    moved = MonitorInfo(EXTERNAL.device, EXTERNAL.id, (2560, 0, 4480, 1080), EXTERNAL.work, False)
    assert layout_fingerprint([LAP, EXTERNAL]) != layout_fingerprint([LAP, moved])
    assert len(layout_fingerprint([LAP])) == 16


def test_zone_monitors_two_one_three():
    assert zone_monitors([LAP, EXTERNAL]) == {"LAPTOP": "id-lap", "EXTERNAL": "id-ext"}
    assert zone_monitors([LAP]) == {"LAPTOP": "id-lap", "EXTERNAL": None}
    third = MonitorInfo(r"\\.\DISPLAY7", "id-3", (2560, 0, 4480, 1080), (2560, 0, 4480, 1040), False)
    assert zone_monitors([LAP, EXTERNAL, third])["EXTERNAL"] is None


def test_zone_monitors_by_device_name():
    assert zone_monitors([LAP, EXTERNAL], laptop=r"\\.\DISPLAY5") == {"LAPTOP": "id-ext", "EXTERNAL": "id-lap"}


def test_enumerate_real_monitors():
    mons = enumerate_monitors()
    assert len(mons) >= 1
    assert sum(m.primary for m in mons) == 1
    assert all(m.rect[2] > m.rect[0] and m.rect[3] > m.rect[1] for m in mons)
