# gazefocus/config.py
Verified against: GazeFocus@bf7feda · 2026-09-29

The file is `%APPDATA%\GazeFocus\config.toml`; the CLI writes the defaults on first run via `write_default_config`.

| Section | Keys (defaults) | Valid range |
|---|---|---|
| `decider` | `dwell_ms` 500, `typing_freeze_ms` 1500, `manual_cooldown_ms` 1000, `post_switch_cooldown_ms` 400, `cursor_idle_warp_ms` 2000 | integers 0..60000 |
| `classifier` | `ema_alpha` 0.35, `dead_band` 0.25, `face_lost_lg_margin` −1.2, `face_lost_memory_s` 0.3, `ood_sigma` 3.5 | (0,1], 0..0.99, −5..0, 0..5, 1..20 |
| `camera` | `index` 0, `width` 640, `height` 480, `fps` 15, `idle_fps` 5, `idle_after_s` 120, `battery_fps` 10 | see `RULES` |
| `dock` | `monitor` "primary", `scale` 1.75 | non-empty text, 0.5..4 |
| `hotkey` | `pause` "Ctrl+Alt+G" | non-empty text |

- `load_config` **never raises on bad content**. Invalid TOML gives all defaults and one warning. A bad value gives that key's default and a warning. Unknown sections and keys produce warnings and are ignored.
- Integer values given for float keys are converted to float.
- `ConfigWatcher.poll()` reloads when the file's mtime or size changes, including deletion (which reverts to the defaults).
- An unreadable file (OSError) gives all defaults plus one warning.
