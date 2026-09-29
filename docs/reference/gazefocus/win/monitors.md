# gazefocus/win/monitors.py
Verified against: GazeFocus@3cc6d6e · 2026-09-29

- `enumerate_monitors()`:
  1. Calls `ensure_dpi_awareness()` (per-monitor v2, so rectangles are in **physical** pixels).
  2. Then `EnumDisplayMonitors` + `GetMonitorInfoW` for the rectangle, work area and primary flag.
  3. Then `EnumDisplayDevicesW(..., EDD_GET_DEVICE_INTERFACE_NAME)` for a stable `id`. `\\.\DISPLAYn` names can change between boots.
- `layout_fingerprint`: the first 16 hex characters of SHA-1 over the sorted `(id, rect, primary)` values. Moving, adding or removing a monitor changes it.
- `zone_monitors(monitors, laptop="primary")`: LAPTOP is the primary monitor (or the device named in `dock.monitor`). LG is the single other monitor, or `None` when it's unplugged or there are more than two.
- Live layout (2026-09-29, physical px): laptop `DISPLAY1` primary (0,0,2560,1600), id `…DISPLAY#CSW1659…`; LG `DISPLAY5` (−1920,−302,0,778), id `…DISPLAY#GSM5CD6…`; fingerprint `720bfe067c959044`.
