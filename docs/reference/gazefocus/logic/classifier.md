# gazefocus/logic/classifier.py
Verified against: GazeFocus@b887938 · 2026-10-01

**Features:** `yaw`, `pitch`, `iris_h`. `iris_v` was dropped because eyelid position follows pitch.

**Fit** (`fit_zone_model`):
1. Keep only the face samples, then **trim turn frames**: drop any sample more than 3 MAD from its screen's median yaw. Each screen needs at least 5 samples left, otherwise `ValueError` ("at least 5").
2. Take the per-screen means and a **diagonal** pooled variance, with floors of 1° for yaw and pitch and 0.05 for iris_h.
3. Weights are `Δμ/σ²`, so every weight has the **same sign as its own mean difference**.
4. Rescale so the external monitor mean projects to **−1** and the laptop mean to **+1**.
5. `separation` = the diagonal Mahalanobis distance between the means. Identical means raise `ValueError` ("indistinguishable").
6. The model also stores the pooled `sd` per feature. `quality()`: ≥ 4 is excellent, ≥ 2 is good, anything lower is too close.

**Why diagonal:** the first real calibration (2026-09-29) fitted with full-covariance LDA gave `pitch` a weight of −0.378, the *opposite* sign to its mean difference. It was exploiting the correlation between pitch and eyelid position. Looking down at the laptop then read as external monitor, and a head at +41° read as LAPTOP. See the spike notes (not published).

**Per frame** (`ZoneClassifier.update`):
- **Face present:**
  - If `is_outlier` (iris_h is exempt once yaw is past the external monitor mean), meaning pitch or iris_h is more than `ood_sigma` (3.5) sd from **both** screens (for example looking down at a phone), it returns `(UNKNOWN, None)` and the frame is **not** fed into the EMA. The gate uses a minimum sd of **4° for pitch and 0.15 for iris_h** (`OOD_SD_FLOOR`), because a steady calibration left pitch sd at 1°, which flagged reading the laptop's bottom edge. On the second desk recording this cut gated frames from 222 to 78 of 888 with the same 9 switches. Yaw isn't gated: turning past the external monitor still means external monitor.
  - Otherwise it keeps an EMA of z with α = `ema_alpha`, restarted after any face loss. Margin ≤ −dead_band is external monitor, ≥ +dead_band is LAPTOP, anything between is UNKNOWN.
- **Face lost:** checked on the first lost frame. If the last frame that produced a **valid** (ungated) margin was within `face_lost_memory_s` and that margin was ≤ `face_lost_external_margin`, it **latches external monitor**; otherwise it returns `(UNKNOWN, None)`. Gated frames never refresh this memory (final-review fix: a phone lean after an external monitor look used to latch external monitor).
- Non-finite features are treated like a gated frame: UNKNOWN, and never fed into the EMA.
