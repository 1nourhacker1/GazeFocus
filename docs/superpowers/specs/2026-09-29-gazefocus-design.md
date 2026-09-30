# GazeFocus: design spec

> Status: **design, approved section by section in brainstorming on 2026-09-29; the written spec was approved the same day.**
> Implemented through Plan 2: §4, §6, §7 and §10–12 in `src/gazefocus/`, with the per-file docs under `docs/reference/gazefocus/`. Desk acceptance passed for the core scenarios (2026-09-30). §8 and §9 (the dock and overlay) are Plan 3.
> Mockups: `docs/superpowers/mockups/` (the dock, calibration, and the earlier style options).

## 1. Intent

**What the user said.** Two screens, lots of windows. "Sometimes I look at a different screen than the one I type in."
They want an app that uses the laptop webcam to see which screen they're looking at and moves keyboard focus there. There should also be
a floating status dock just under the laptop camera. They found `PINTO0309/screen-eye-tracking` and don't want to start
from zero.

**Agreed understanding.**
- A personal tool for one person on one laptop, not a product.
- Success means typing lands in the window on the screen the user is looking at.
- It must never fight them: no switching mid-typing, no typing lag, no noticeable slowdown.

**Assumptions** (not stated by the user; made during design):
- There are exactly two monitors.
- The user sits roughly where they sat during calibration.
- The webcam stays on the laptop.

## 2. Context (verified on the machine, 2026-09-29)

| Item | Value |
|---|---|
| Laptop | Lenovo 83NX, Core Ultra 9 275HX (24 cores), 31 GB RAM, RTX 5060 Laptop, Intel NPU |
| Screen A: laptop (primary) | `\\.\DISPLAY1`, 16", 2560×1600 at 240 Hz, 150% scaling (1707×1067 logical). **The webcam sits on top of it.** |
| Screen B: LG | `\\.\DISPLAY5`, 24", 1920×1080, 100%. Positioned **left of** the laptop and **raised**: logical origin (−1920, −302) |
| Camera | Integrated RGB camera only, no IR. **Windows Studio Effects** is present: Automatic Framing was on and the user turned it off; Eye Contact is off. |
| Toolchain | Python 3.14 system-wide, **uv 0.9.29** (used to pin 3.12), .NET 10, Node 24, git |

Consequence of the layout: looking at the LG means turning the head **left and slightly up**, away from the camera.
That's a large, easy signal, so a coarse left-or-right decision is enough. Pixel-accurate gaze isn't needed.

### Recon verdicts
- **PINTO0309/screen-eye-tracking:** MIT code, Electron overlay.
  - Its 185 MB gaze model is very likely InsightFace 3DGazeNet, which is licensed **for non-commercial use only**. That's acceptable here because this is a personal tool.
  - Overkill for a two-zone decision, and it warns about off-axis cameras.
  - Its local API (`:47892`, yaw/pitch) is a possible alternative `HeadTracker` later.
- **Closest prior art:** `UtkarshBagaria/AutoFocus`, used as a reference. `Glance Switch` (Mac) confirms that head direction is enough to pick a screen.
- **Chosen tracker:** MediaPipe Face Landmarker (Apache-2.0, Tasks API). Fallback: OpenSeeFace (BSD-2).

## 3. Goals, success criteria, non-goals

**Success criteria** (each measured, not assumed):
1. CPU **under 2% total** and RAM **under 300 MB**, measured by `--bench`.
2. **No typing lag.** Input is observed via Raw Input, never a keyboard hook.
3. A switch happens within **about 0.6 s** of looking at the other screen (0.5 s dwell plus one frame plus switch time).
4. **Fewer than 1 false switch per hour** of normal work, counted from a day of `decisions.log`.
5. The acceptance checklist (§12.4) passes on the user's desk.

**Non-goals for v1:** more than 2 monitors, an installer or code signing, starting with Windows, GPU inference, a settings UI
(the config file is the settings UI), reduced-motion or reduced-transparency modes (the user explicitly declined them),
and multiple users.

## 4. Behaviour

### 4.1 When focus moves ("follow gaze, pause while typing": the user's choice)
Focus moves to the other screen when **all** of these hold:
1. The classifier reports the other screen past the *enter* threshold (§6.3).
2. It has done so **continuously for `dwell_ms` = 500**. The dwell timer resets on UNKNOWN or on the current screen.
3. **No freeze condition is active:**

| Freeze condition | Default |
|---|---|
| Any key pressed within `typing_freeze_ms` | 1500 ms (every key counts, modifiers included) |
| Any mouse button held (drags, including moving a window between screens) | while held |
| Focus changed by something other than GazeFocus (click, Alt+Tab, an app popping up) | `manual_cooldown_ms` = 1000 |
| GazeFocus just switched | `post_switch_cooldown_ms` = 400 (prevents flip-flopping back and forth) |
| A fullscreen game or presentation is in front (`SHQueryUserNotificationState`) | while active |
| Paused, not calibrated, layout changed, or the camera is unavailable | while active |

Dwell keeps accumulating during a freeze. If you're still looking at the other screen when the freeze ends, the switch
happens immediately. That's the "lid melts, then the water pours" behaviour shown in the mockup.

**Accepted tradeoff:** if you're copying from the LG into a laptop window and pause typing for more than 1.5 s, focus moves.
The escape hatches are the dock click, Ctrl+Alt+G, and tuning `typing_freeze_ms`.

**Source of truth:** the live `GetForegroundWindow()` is authoritative. The decider never trusts its own idea of where
focus is.

### 4.2 Which window receives focus
- The **most recently used (MRU) valid window on the target monitor**, tracked with `EVENT_SYSTEM_FOREGROUND`.
- A window is valid when all of these hold:
  - `IsWindow`, `IsWindowVisible` and not `IsIconic` (minimized windows are skipped, never restored)
  - not DWM-cloaked, and on the current virtual desktop (`IVirtualDesktopManager`)
  - `MonitorFromWindow` still returns the target monitor (the window may have moved)
  - not a GazeFocus window, and not a shell window (`Progman`, `WorkerW`, `Shell_TrayWnd`, `Shell_SecondaryTrayWnd`)
- If the MRU list has no valid window, the fallback is the first valid window in Z-order (`EnumWindows` walks from the top).
- If there's none at all (an empty desktop), nothing happens.
- If focus is already on the target monitor, nothing happens.

### 4.3 Cursor
- If the mouse has been idle for `cursor_idle_warp_ms` = 2000 when a switch fires, the cursor moves (`SetCursorPos`) to
  its **last position on the target monitor**. With no history, it moves to the centre of the target window.
- The position is clamped to the monitor's work area.
- If the mouse is active, the cursor is never touched.

### 4.4 Face lost
- If the face disappears and the last valid smoothed margin (within 300 ms) was **at or below −1.2**, meaning past the LG's
  calibrated centre, it counts as **LG**, because turning hard left takes the face out of view.
- Otherwise it's **UNKNOWN**. UNKNOWN never triggers a switch, and focus is held.

### 4.5 Pause
- Toggled by clicking the dock, the tray menu, or **Ctrl+Alt+G** (`RegisterHotKey`, no hook).
- Pausing **releases the camera** (the light turns off). Resuming reopens it.
- Pausing, locking or sleeping during a calibration **cancels it**. That releases the camera and keeps the previous calibration (Plan 2 final review).

## 5. Architecture

A single Python 3.12 process (uv-managed) with two threads:

```
[camera thread]  CameraSource → HeadTracker ──HeadSample (Qt signal, queued)──┐
                                                                               ▼
[Qt main thread: also runs the Win32 message loop that hooks need]
  ZoneClassifier → GazeDecider → FocusSwitcher
        ▲              ▲ ▲              ▲
   Calibration   InputWatcher  ForegroundTracker        Dock / CalibrationOverlay / Tray
                 (Raw Input)   (WinEvent hook, MRU)     (Qt Quick)
```

| Unit | Responsibility | Depends on | Pure (testable without hardware)? |
|---|---|---|---|
| `vision.camera.CameraSource` | Opens the camera (OpenCV MSMF), 640×480, yields frames at the configured FPS; release and reopen | OpenCV | no |
| `vision.pose` | 4×4 face transform → yaw/pitch; landmarks → iris offsets | numpy | **yes** |
| `vision.tracker.HeadTracker` | MediaPipe FaceLandmarker in `VIDEO` mode → `HeadSample` | mediapipe, `pose` | no |
| `logic.classifier.ZoneClassifier` | Fits the calibration (diagonal discriminant, §6); turns a sample into (zone, margin); outlier gate; separation score | numpy | **yes** |
| `logic.decider.GazeDecider` | The §4.1 state machine: takes samples, input times, foreground events and a clock, emits `Decision`s | none | **yes** |
| `win.rawinput.InputWatcher` | Last key time, last mouse-move time, buttons held, last cursor position per monitor; ignores **injected** input (`hDevice == 0`) | ctypes | no |
| `win.foreground.ForegroundTracker` | WinEvent hook, MRU per monitor, flags manual versus our own focus changes | ctypes | no |
| `win.focus.FocusSwitcher` | §7.3 procedure, cursor warp, result reporting | ctypes | no |
| `win.monitors` | Enumerate monitors, per-monitor DPI, layout fingerprint | ctypes | no |
| `win.system` | Single instance (named mutex), session lock/unlock, fullscreen state, camera-in-use check, hotkey | ctypes, winreg | no |
| `win.dwm` | Window styles (no-activate, tool window, topmost), acrylic backdrop, region | ctypes | no |
| `ui.dock` + `qml/Dock.qml` + `shaders/liquid.frag` | §8 | PySide6 | no |
| `ui.calibration` + `qml/CalibrationOverlay.qml` | §9 | PySide6 | no |
| `ui.tray` | Tray icon menu | PySide6 | no |
| `config`, `storage`, `replay`, `diag` | §10, §12 | tomllib, json | mostly |

> *(Plan 2, 2026-09-29)*
> - The app lives in `gazefocus.app`: `state`, `decision_log`, `controller` (with an injectable `Desktop` for all Win32 access, so behaviour is tested with fakes), `workers`, `tray` and `main`.
> - The Windows side is in `gazefocus.win`: `_api` (every prototype, declared once), `msgwindow` (a hidden **top-level** window, not message-only, so it also gets broadcasts; Qt's loop pumps it), `windows`, `focus`, `rawinput`, `foreground` and `system`.
> - Shared helpers: `calibration.commit_calibration` (used by the CLI and the tray) and `cues.beep`.

**Core types** (`gazefocus/types.py`):
```python
@dataclass(frozen=True)
class HeadSample:          # one per processed frame
    t: float               # monotonic seconds
    face: bool
    yaw: float; pitch: float        # degrees; yaw > 0 = turned toward the LG, i.e. the user's left (M0-A)
    iris_h: float; iris_v: float    # −1..1 within the eye opening

class Zone(Enum): LAPTOP, LG, UNKNOWN   # internally keyed by monitor ID, not by name

@dataclass(frozen=True)
class Decision:
    t: float; zone: Zone; margin: float
    action: Literal["none", "switch", "blocked"]
    reason: str            # e.g. "typing 0.4s", "dwell 320/500", "manual cooldown"
    target_monitor: str | None
```

## 6. Signal processing

> **Revised 2026-09-29 (Plan 1 desk session).** The first real calibration showed that the full-covariance, four-feature LDA originally written here weighted pitch *against* its own mean difference, by exploiting the pitch↔eyelid correlation. Looking down at the laptop then read as the LG. What follows is the design that replaced it; the evidence is in `docs/spikes/plan1-desk-session.md`.

### 6.1 Features
- From MediaPipe (`num_faces=1`, facial transformation matrices on, blendshapes off, confidence thresholds 0.5):
  - **yaw and pitch** from the rotation part of the 4×4 matrix. Turning toward the LG makes yaw **positive** (M0-A).
  - **iris_h**: the iris centres (landmarks 468 and 473) relative to the eye corners (33/133, 362/263), averaged across both eyes.
  - `iris_v`, the position between the lids, is still computed, but **it isn't used**: eyelid position follows pitch.
- Feature vector: `f = (yaw, pitch, iris_h)`.

### 6.2 Calibration fit
- **Trim turn frames:** per screen, drop any sample more than 3 MAD from the median yaw. The first 1.0 s of each phase is discarded as well.
- **Diagonal linear discriminant:** per-screen means plus a *diagonal* pooled variance (floors of 1°, 1° and 0.05). Each weight is `Δμ/σ²`, so it always has the sign of its own mean difference, and yaw dominates in practice.
- Projections are scaled so the LG's mean sits at **z = −1** and the laptop's mean at **z = +1**.
- **Separation score** = the diagonal Mahalanobis distance between the screen means, shown as "Nσ":
  - **4σ or more:** excellent
  - **2σ to 4σ:** good
  - **under 2σ:** too close. The message is "turn your head a little more, or move the LG closer". The **previous calibration is kept** unless `--force` is given; a replaced one is saved as `calibration.prev.json`.
- The model stores the pooled `sd` per feature, for the outlier gate below.

### 6.3 Per-frame classification
- **Outlier gate:** if pitch or iris_h is more than `ood_sigma` (3.5) sd from **both** screens (for example looking down at a phone), the result is UNKNOWN and the frame isn't used.
  - The gate uses a minimum sd of 4° for pitch and 0.15 for iris_h.
  - iris_h isn't gated when the head is already turned past the LG.
  - Yaw is never gated.
- `z = w·f + b`, smoothed with an **exponential moving average (EMA), α = 0.35** (about 150 ms at 15 FPS). The result is the margin. The EMA restarts after a gated stretch or a face loss.
- **z ≤ −0.25** is LG, **z ≥ +0.25** is LAPTOP, and anything between is UNKNOWN (a dead band, which is the hysteresis).
- Face lost: see §4.4. The 300 ms memory counts from the last frame that produced a **valid** margin, not a gated one.

## 7. Windows integration

### 7.1 Input: Raw Input (never `WH_KEYBOARD_LL`)
- A hidden message-only window registers keyboard and mouse with `RIDEV_INPUTSINK`.
- Events arrive as copies after delivery, so they can't add latency.
- Injected events are ignored (`hDevice == NULL`), so our own `SendInput` never counts as the user touching the mouse.
- *(Plan 2)* Mouse buttons *held* are read live with `GetAsyncKeyState` every frame, never cached from Raw Input, so a missed button-up can't freeze switching. The window receiving Raw Input is a hidden top-level window (see §5), not a message-only one.

### 7.2 Foreground tracking
- `SetWinEventHook(EVENT_SYSTEM_FOREGROUND, …, WINEVENT_OUTOFCONTEXT)` on the Qt thread.
- The MRU list is keyed by monitor handle (via `MonitorFromWindow`) and rebuilt when monitors change.
- A change is labelled *ours* if it happens within 300 ms of our own `SetForegroundWindow` to that window. Anything else is
  *manual*, which starts the cooldown.

### 7.3 Focus switch procedure (in order)
1. Validate the target window (§4.2).
2. `SendInput` one zero-motion relative mouse move. This makes our process the one that received the last input event,
   which Windows requires before it allows `SetForegroundWindow` (the PowerToys FancyZones trick).
3. `SetForegroundWindow(hwnd)`, then check that `GetForegroundWindow() == hwnd` within 50 ms.
4. If that fails, on a worker thread with a **500 ms timeout**: `AttachThreadInput`, then `BringWindowToTop` +
   `SetForegroundWindow`, then detach. The timeout matters because `AttachThreadInput` can deadlock.
5. If that fails too, log `FAIL`, shake the dock once, and **don't retry this switch**. That covers a focus lock or a hung window. **M0-B (2026-09-30):** elevated windows do *not* end up here. The direct path focused the elevated Task Manager, and switched away from it, in 7 ms from medium integrity.
6. On success: warp the cursor (§4.3), log the decision, and start `post_switch_cooldown`.

### 7.4 Other system hooks
- **DPI:** per-monitor DPI awareness v2 (Qt 6's default). All geometry is in physical pixels, converted per monitor.
- **Session:** `WTSRegisterSessionNotification`. Lock releases the camera; unlock reopens it. Resume from sleep also reopens it.
- **Camera in use:** when opening fails, check
  `HKCU\…\CapabilityAccessManager\ConsentStore\webcam\**\LastUsedTimeStop == 0` for another app. If another app has it,
  show the "camera off" state and retry every 5 s.
  **M0-D result (2026-09-29):**
  - The webcam is **exclusive**. The Windows Camera app fails while GazeFocus holds it.
  - A failed attempt by another app leaves **no** ConsentStore trace, so this check only covers the reverse case.
  - Plan 2 must hand the camera over explicitly: the manual pause, and possibly a call-app heuristic. See `docs/spikes/m0d-camera-sharing.md`.
  **Decision (2026-09-29):** camera hand-over is **manual only**. Ctrl+Alt+G or tray → Pause releases the camera. The user declined auto-yielding to call apps, and declined Windows' "allow multiple apps to use the camera" setting.
- **Single instance:** named mutex `Local\GazeFocus`. A second launch exits.

## 8. The dock

### 8.1 Visual design (approved: `mockups/dock-liquid-v2.html`)
- **Placement:** top centre of the laptop's work area, 4 px below the top edge, directly under the camera. It doesn't move.
- **Collapsed size:** **1.75×** the base 44×20, then 1.5× bigger at the user's request (M0-C2, 2026-09-30): **115.5×52.5 logical px**. Pill-shaped.
- **Material:** "Liquid Glass" imitation:
  - backdrop blur of whatever is behind: blur(20px) saturate(1.7), self-captured (§8.5)
  - a **lens rim**: content under the edge bends around it. On by default; `dock.refraction = false` turns it off (M0-C2)
  - a translucent fill
  - a specular top edge, rim light and soft shadow
- **Glyph colours** (outlines, lid and pause bars) switch between dark and light based on the brightness *behind* the dock.
  It samples at 1 Hz with a 0.45/0.55 hysteresis, and the dock excludes itself from the capture
  (`WDA_EXCLUDEFROMCAPTURE`).
- **Glyph: two tiles** in a viewBox of 88×40:
  - LG at (18,10,22,14), on the left and 4 units higher; laptop at (48,14,22,14).
  - **Both tiles share one base size.** The **focused tile scales to 1.18**, the other to 0.9, and both return to 1.0 when paused (the user asked for this).
- **Water** fills the focused tile. It's green (#28A745 on light backgrounds, #30D158 on dark) with a small specular highlight.
  Liquid merging is done with a signed-distance-field smooth-min (in the CPU renderer, §8.5), the equivalent of the mockup's blur-and-threshold "goo" filter.

### 8.2 States and cues (shape as well as colour)
| State | Visual |
|---|---|
| Tracking | Water in the focused tile, which is the bigger one |
| Frozen while typing | Water turns **amber** (#D67800 / #FF9F0A) and a **lid** line closes over the tile. A blocked gaze makes the water wobble slightly. The lid holds for 0.3 s after each key (steady typing never moves it), then melts linearly and is gone exactly when the 1.5 s freeze ends: the freeze countdown (Plan 3). |
| No face | The water **evaporates** (5 steam particles) and the tiles are empty. Focus is held. |
| Paused | The water **drains**, the tiles drop to 1.0 and dim, and **pause bars** appear |
| Camera off / not calibrated / error | Empty tiles plus a small "!" |

### 8.3 Motion (timings from the approved mockup)
- **Switch ("Flow", the user's choice), 580 ms:**
  - The source water drains over 290 ms (ease-in) and its tile shrinks over 320 ms.
  - A stream of 6 merging droplets follows an arc above the tiles.
  - The target fills over 320 ms (ease-out), starting at 290 ms. Its tile springs to 1.18 using `1 − e^(−5.5t)·cos(9t)` over 435 ms, starting at 244 ms.
  - A slosh wave with amplitude 1.8 decays over about 1 s.
- **Other animations:** evaporate 560 ms, condense 500 ms (3 falling drops), drain 440 ms, lid close 180 ms, thaw 1500 ms.
- **No idle animation. Ever.** Nothing moves unless the state changes. The dock is in peripheral vision under the camera,
  and motion there would pull the gaze back to the laptop and cause false switches.
- Windows' "Animation effects" and "Transparency effects" settings are **ignored**, at the user's request.

### 8.4 Interaction
- **Hover for 350 ms:** the dock springs open to a **300×158** panel, anchored at the top: `cubic-bezier(.3,1.45,.5,1)` over 520 ms, with a more opaque fill.
  It collapses 250 ms after the pointer leaves.
- **The panel contains:**
  - a camera preview at 10 FPS, **only while open**, with a face box and head-direction ray
  - a state title ("Focus: LG", "Frozen while typing", …)
  - yaw, pitch, margin, and time since the last key
  - **Pause/Resume** and **Recalibrate** buttons
- **Clicking the pill area** toggles pause, with a ripple.
- **The open panel (Plan 3):**
  - The glyph stays centred at the top at 77 px wide, with the content 6 px below it (the mockup's layout).
  - Only its buttons act; a click anywhere else in it, or on the shadow, does nothing.
  - The camera preview runs at 10 fps only while the panel is open, and the last frame is dropped when it closes.

### 8.5 Implementation (M0-C2, 2026-09-30)
- **Window:** a frameless, translucent `QWidget` with `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus` and `WA_ShowWithoutActivating`.
  - Win32 styles `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST`, plus `WM_MOUSEACTIVATE → MA_NOACTIVATE`.
  - **The dock must never become the foreground window.**
- **The glass is rendered by us**, because M0-C showed that DWM and accent blur never show behind Qt's layered windows.
  1. The dock excludes itself from capture with `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`.
  2. It grabs the pixels behind it with a GDI `BitBlt`, about 7 times a second, and renders a frame only when they changed.
  3. It renders the blur, saturation, tint, highlights, shadow and lens rim with numpy and OpenCV.
  4. Qt presents the result with per-pixel alpha (`UpdateLayeredWindow`). There's no window region, so the edges are antialiased, and pixels with alpha 0 let clicks through.
- **Clock:** during an animation, frames are paced by `DwmFlush` on a helper thread, at the display refresh (240 Hz on this laptop). Qt's 60 Hz animation timer looked choppy (M0-C2).
- **Caching:**
  - Blurs and luminance are computed once per backdrop change.
  - The glass is cached per shape and theme, so a water switch only redraws the glyph.
  - While the panel resizes, the glass renders at half resolution, then one full-resolution frame follows.
  - No grabs run while something moves.
- **Expanding:** the window is sized to the panel's maximum, and the pill is drawn inside it.
- **Hidden** while locked, asleep, or while a fullscreen app (not a maximized window) covers the laptop screen (Plan 3).
- See `docs/spikes/m0c-glass-dock.md` and `docs/spikes/m0c2-liquid-glass.md`.
- **CPU cost:**
  - When idle, there are zero frames. There's only a 4–6 ms screen grab about 7 times a second, to notice changes behind the dock.
  - An animation costs 2–5 ms a frame, for half a second.

## 9. Calibration (approved: `mockups/calibration.html`, guidance "follow the drop")

1. **Triggered by:** first run, the Recalibrate button, or a changed monitor layout (the dock shows "!").
2. **Start:** the dock swells into a panel: *"Calibrate GazeFocus. Sit the way you normally do, follow the drop with your eyes,
   turn your head naturally. About 15 s."* with **Start** and **Not now**.
3. **LG step:**
   - A full-screen overlay appears on each monitor: click-through, never takes focus, 25% dim on the target screen and 62% on the other.
   - A glowing water drop rises from the dock and arcs to the LG's centre (1100 ms).
   - A glass card, *"Look at this screen · Follow the drop"*, shows for 1300 ms, above centre.
   - The drop **tours** the screen for 5200 ms along a Catmull-Rom spline through
     (.5,.5) → (.1,.14) → (.9,.14) → (.9,.86) → (.1,.86) → (.5,.5), easing in and out on each segment so it
     lingers briefly in each corner. A progress ring surrounds it.
4. **Laptop step:** the same, with top waypoints at y = .24 to stay clear of the dock. Then the drop returns into the dock.
5. **Sampling rules:**
   - Only frames where the face is detected count.
   - The first 400 ms of each tour are discarded (the eyes are still settling).
   - At least **40 valid samples per screen** are required.
   - If the face is lost, the drop **waits** and the card says *"Can't see you. Is the room too dark?"*
6. **Result panel** in the dock (it springs open to **372×200**):
   - a yaw/pitch scatter plot per screen with the dividing line
   - mean yaw and pitch per screen
   - the separation score and meter (§6.2)
   - **Save** and **Redo**
7. **Esc** cancels at any point. Raw Input sees the key; nothing captures it.
8. **Both monitors must be connected.**
   - The app refuses Recalibrate with anything other than 2 monitors.
   - It doesn't save a result if the layout changed during the run, so the good calibration can't be replaced by a one-monitor one.
   - `calibrate-cli` still allows one monitor, for dry-run use (Plan 1).
9. **As built (Plan 4, 2026-09-30):**
   - **Triggers:** the tray, the hover panel's Recalibrate, a click on the dock's "!" (not calibrated or layout changed), and the first start. Every trigger opens the intro first. **Redo** skips the intro.
   - **Camera:** the samples come from the tracking camera, which stays on (or starts) at the full `camera.fps` while calibrating. Nothing switches meanwhile.
   - **The beeps are kept** (1 = LG, 2 = laptop, 3 = done), because the user may be looking at the other screen. They play off the UI thread.
   - **Timeline:** 420 ms, then for each screen: travel 1100 ms, the card (1300 / 1200 ms), the tour 5200 ms. Then 700 ms back to the dock, and 600 ms of fade. That's about 17 s.
     - A tour's clock stands still while no face is seen, or no camera frame has arrived for 1 s. After 0.3 s the card says *"Can't see you / Is the room too dark?"*
     - The laptop leg ends at the laptop's centre, where its tour begins (the mockup's (.5, .55) would make the drop jump).
   - **Overlay:** a black dim window per monitor with only its window opacity animated; one small per-pixel-alpha window for the drop and ring, moved each frame; a dark-glass card window per monitor. The drop and cards are excluded from capture. The dock is lifted back above them.
   - **Result panel:**
     - The scatter fits its axes to the samples, with the LG always on the left.
     - The dashed line is the fitted model's real boundary.
     - A saveable result gets a live preview: the dock's water follows the new model before Save, as the hint promises.
   - **Can't save:** too close gives only **Redo** ("Too close" / "Turn your head a little more, or move the LG closer to the laptop."). Fewer than 40 samples per screen: "Too few samples", with the counts.
   - **Cancels:** Esc (even on the result panel), Not now, pause, lock, sleep, and a layout change mid-run. The layout fingerprint is checked again at Save.
   - **Every exit ends it** (Plan 4 final review):
     - 20 s without a face ends a tour with "Couldn't see you".
     - A camera failure, or the tracker's 3rd crash, cancels the run.
     - A result left alone for 60 s, or interrupted by pause, lock or sleep, is **saved** if it can be (Esc discards it).
     - A config reload that rebuilds the dock shows the same panel again.

## 10. Configuration and files (`%APPDATA%\GazeFocus\`)

**`config.toml`** reloads live when saved. Invalid values are logged and the defaults are kept.

| Key | Default |
|---|---|
| `decider.dwell_ms` | 500 |
| `decider.typing_freeze_ms` | 1500 |
| `decider.manual_cooldown_ms` | 1000 |
| `decider.post_switch_cooldown_ms` | 400 |
| `decider.cursor_idle_warp_ms` | 2000 |
| `classifier.ema_alpha` | 0.35 |
| `classifier.dead_band` | 0.25 |
| `classifier.face_lost_lg_margin` | −1.2 |
| `camera.index` | 0 |
| `camera.width` | 640 |
| `camera.height` | 480 |
| `camera.fps` | 15 |
| `camera.idle_fps` | 5 |
| `camera.idle_after_s` | 120 |
| `camera.battery_fps` | 10 |
| `dock.monitor` | `"primary"` |
| `dock.scale` | 1.75 |
| `hotkey.pause` | `"Ctrl+Alt+G"` |

- **`calibration.json`:** `version`, `created`, and `layout` (a fingerprint plus each monitor's device name, ID, rectangle and primary flag).
  Also `camera` (name and resolution), the model `{w, b, separation, mean_lg, mean_laptop, sd}` and per-screen sample counts.
  This is **version 2** (2026-09-29); version 1 files are refused with "please recalibrate". A replaced calibration is kept as `calibration.prev.json`.
  It's loaded only if the layout fingerprint matches the current monitors.
- **`logs/gazefocus.log`** (rotating, 5 × 1 MB) and **`logs/decisions.log`**: one line per `Decision`, with action `switch`, `blocked` or `FAIL`.
- **Model:** `models/face_landmarker.task` in the repo folder (gitignored). `scripts/fetch_model.py` downloads it and verifies a pinned SHA-256.

## 11. Performance budget

- **Estimated** (to be measured in M0-A):
  - MediaPipe: about 5–8 ms per frame on one core; at 15 FPS that's about 0.5–1% of total CPU
  - RAM: about 200–300 MB
  - Extra battery draw: about 1 W, mostly the camera staying on
- **Adaptive frame rate:**
  - 15 FPS normally
  - 5 FPS after 120 s with no input
  - 10 FPS on battery
  - 0 when paused or locked (camera released)
  - 10 FPS preview only while the hover panel is open
- `--bench` prints FPS, per-stage milliseconds, CPU % and RSS once a minute.

## 12. Errors and testing

### 12.1 Failure handling
| Situation | Behaviour |
|---|---|
| Camera busy or unplugged | Release it, show "camera off", retry every 5 s, resume on its own |
| Lock or sleep | Release the camera immediately; reopen on unlock or resume |
| Target window closed or frozen | Take the next MRU entry and never wait on it (no `SendMessage` to the target) |
| Focus refused (e.g. a focus lock or a hung window) | Fallback chain (§7.3), then one `FAIL` log line and a dock shake. No retry loop. |
| Tracker thread exception | Log it and restart after 2 s. After 3 consecutive failures the dock shows "!". |
| Not calibrated or layout changed | No switching; the dock shows "!" and offers calibration |
| More than 2 monitors | "Unsupported layout" state; no switching |

### 12.2 Unit tests (pytest, no hardware, written test-first)
- `pose`: synthetic rotation matrices produce known yaw and pitch, including the sign convention.
- `classifier`: fit on synthetic clusters; margins, dead band and separation score; the face-lost rule.
- `decider`: scripted timelines with a fake clock covering:
  - dwell, and the dwell reset
  - glance-while-typing blocked, then the switch at the end of the thaw
  - a held mouse button, and manual Alt+Tab cooldown
  - post-switch cooldown; face lost (both branches); paused; fullscreen
  - "already on the target monitor, so do nothing"
- `config` / `storage`: defaults, validation, round trips, and fingerprint mismatch.

### 12.3 Record, replay and diagnostics
- `--record` saves `HeadSample`s plus input and foreground timings as JSONL, **with no video**.
- `--replay FILE` runs a recording through the classifier and decider and prints the decisions, so tuning can be tested
  against real behaviour.
- `gazefocus diag monitors | windows | focus <monitor> | camera` checks each Windows piece by hand.
  *(Plan 2)* Implemented as `gazefocus diag monitors | windows [--all] | focus {LAPTOP,LG} [--delay 3]`; `gazefocus live` serves as `diag camera`.

### 12.4 Acceptance checklist (on the desk; **the LG must be reconnected**)
1. Look at the LG while idle → focus moves within about 0.6 s, and the cursor warps if the mouse is idle.
2. Glance at the LG while typing continuously on the laptop → no switch; the dock shows the lid.
3. Stop typing while still looking at the LG → the switch happens right after the 1.5 s thaw.
4. Drag a window from the laptop to the LG → no switch during the drag.
5. Alt+Tab to a window on the other screen → honoured, with no bounce-back.
6. Lean down to a phone (face lost) → focus held and the dock shows evaporation.
7. A Teams or camera app grabs the camera → "camera off", then it resumes afterwards.
8. Lock and unlock → the camera light goes off, then tracking resumes.
9. An elevated window (Task Manager) on either screen: switching to it and away from it works, with no hang (M0-B showed this). A refused switch gives one `FAIL` line and a shake.
10. `--bench` over 10 minutes → CPU under 2% and RSS under 300 MB. Typing latency feels unchanged.

## 13. Tech stack and repo layout

- **Python 3.12** via uv (MediaPipe wheels support 3.9–3.12; the system Python is 3.14).
- **Dependencies:** `mediapipe` 1.0.x (Tasks API; the old `mp.solutions` API was removed in 0.10.30), `opencv-python`,
  `numpy`, `PySide6` (Qt Quick and shader tools), `comtypes` (only for `IVirtualDesktopManager`), `pytest`.
- **Win32 access:** `ctypes` throughout.

```
C:\work\GazeFocus\
  pyproject.toml  uv.lock  README.md  .gitignore
  scripts/fetch_model.py
  models/                      (gitignored; face_landmarker.task)
  src/gazefocus/
    __main__.py  app.py  config.py  storage.py  types.py  replay.py  diag.py
    vision/  camera.py  tracker.py  pose.py
    logic/   classifier.py  decider.py
    win/     rawinput.py  foreground.py  focus.py  monitors.py  system.py  dwm.py
    ui/      dock.py  calibration.py  tray.py  qml/Dock.qml  qml/CalibrationOverlay.qml  shaders/liquid.frag
  tests/  test_pose.py  test_classifier.py  test_decider.py  test_config.py  test_storage.py  test_replay.py
  docs/   treestruct.md  superpowers/specs/  superpowers/mockups/  reference/ (a mirror of src/, written as code lands)
```

## 14. Risks and early spikes (milestone M0, before the main build)

| ID | Question | How we find out | If it fails |
|---|---|---|---|
| M0-A | Does MediaPipe keep tracking at the yaw needed to look at the LG, and hit the budget on this CPU? What is the yaw sign? | A probe script: live yaw/pitch plus timing while the user looks at each screen | Rely on the face-lost rule more heavily, or switch the tracker to OpenSeeFace |
| M0-B | Does the §7.3 trick reliably focus windows from a process that has no focus of its own? | `diag focus` against Chrome, VS Code, Explorer and Windows Terminal | Try the alternative ordering, an Alt-key tap, or accept a flash |
| M0-C | Can a no-activate Qt Quick window show acrylic clipped to a pill, and animate its shape without flicker? | A minimal dock window | Try the next fallback in §8.5 |
| M0-D | Can Teams or Zoom share the camera while GazeFocus holds it? | Hold the camera and start a Teams test call | Auto-pause when another app wants the camera (already specified) |

The camera-only spikes (A, C, D) run with the LG disconnected. M0-B needs any second window target, which works on one screen, but the per-monitor behaviour needs the LG.

## 15. Decisions log (2026-09-29, brainstorming)

| Decision | Chosen | Rejected |
|---|---|---|
| Trigger | Follow gaze, pause while typing | Type where I look; always follow; hotkey only |
| Audience | Just me (personal) | Open source; product |
| Cursor | Warp only if the mouse is idle | Never; always |
| Dock features | Status, click to pause, recalibrate, hover preview | none |
| Approach | A: all Python, one process | B: C# host + Python tracker; C: all C# with ONNX |
| Dock style | C: mini screen map, Liquid Glass, water | A: text pill; B: status dot |
| Switch motion | Flow | Hop |
| Dock size | 1.75× | 1×, 1.5×, 2× |
| Tile sizing | Equal base size; the selected tile grows | Proportional to physical size |
| Accessibility fallbacks | None; always full motion and glass (user's choice) | Honour the Windows settings |
| Calibration guidance | Follow the drop | Look around freely |
| Project location | `C:\work\GazeFocus` | none |
| Classifier (desk session, after Plan 1) | Diagonal discriminant on yaw, pitch, iris_h; turn-frame trim; outlier gate; v2 calibration file | Full-covariance LDA on four features (weighted pitch against its own mean difference on real data) |
| Live view (user request) | `gazefocus live`, a mirrored preview with the head-pose overlay | none |
| Calibration cues | The program beeps (450 ms): 1 = LG, 2 = laptop, 3 = done | Typed cues from the assistant (arrived seconds late) |
| Camera hand-over for calls (Plan 2) | Manual pause (Ctrl+Alt+G / tray) | Auto-yield to call apps; Windows multi-app camera setting |
| Focus after using the tray menu (Plan 2) | Return focus to the last app window | Leave it on the taskbar |
| Recalibrate without both monitors (Plan 2 final review) | Refused in the app; a mid-run layout change isn't saved | Save a one-monitor calibration over the good one |
| Dock renderer (M0-C2) | CPU: self-captured backdrop, numpy/OpenCV glass, per-pixel alpha, DwmFlush clock | Qt Quick shader; WebView acrylic |
| Dock size (M0-C2, user) | Pill 1.5× bigger (115.5×52.5); panel stays 300×158 | 77×35 |
| Lens rim (M0-C2) | On by default, config switch | Off |
| Typing lid timing (Plan 3) | Holds 0.3 s, then melts until the freeze ends | Melts over 1.5 s after typing stops |
| Dock over fullscreen apps (Plan 3) | Hidden | Always on top |
| Calibration overlay | Plan 4 | Plan 3 |
| Calibration samples (Plan 4) | The tracking camera, into a Qt-thread session (the drop reacts to each frame) | A separate calibration thread with its own camera (Plan 2's `CalibrationJob`, removed) |
| Calibration cues (Plan 4) | Overlay **and** the beeps | Overlay only |
| No face during a tour (Plan 4) | The drop waits; the card asks after 0.3 s | Keep touring and collect fewer samples |
| Result preview (Plan 4) | The dock's water follows the new model before Save | Static result |
| A double-click on the dock (Plan 4) | One click | Two toggles |
