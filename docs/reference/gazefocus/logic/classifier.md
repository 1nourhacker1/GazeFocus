# gazefocus/logic/classifier.py
Verified against: GazeFocus@90c2edd · 2026-09-29

**Features:** `yaw`, `pitch`, `iris_h`. `iris_v` was dropped because eyelid position follows pitch.

**Fit** (`fit_zone_model`):
1. Keep only the face samples, then **trim turn frames**: drop any sample more than 3 MAD from its screen's median yaw. Each screen needs at least 5 samples left, otherwise `ValueError` ("at least 5").
2. Take the per-screen means and a **diagonal** pooled variance, with floors of 1° for yaw and pitch and 0.05 for iris_h.
3. Weights are `Δμ/σ²`, so every weight has the **same sign as its own mean difference**.
4. Rescale so the LG mean projects to **−1** and the laptop mean to **+1**.
5. `separation` = the diagonal Mahalanobis distance between the means. Identical means raise `ValueError` ("indistinguishable").
6. The model also stores the pooled `sd` per feature. `quality()`: ≥ 4 is excellent, ≥ 2 is good, anything lower is too close.

**Why diagonal:** the first real calibration (2026-09-29) fitted with full-covariance LDA gave `pitch` a weight of −0.378, the *opposite* sign to its mean difference. It was exploiting the correlation between pitch and eyelid position. Looking down at the laptop then read as LG, and a head at +41° read as LAPTOP. See `docs/spikes/plan1-desk-session.md`.

**Per frame** (`ZoneClassifier.update`):
- **Face present:**
  - If `is_outlier`, meaning pitch or iris_h is more than `ood_sigma` (3.5) sd from **both** screens (for example looking down at a phone), it returns `(UNKNOWN, None)` and the frame is **not** fed into the EMA. Yaw isn't gated: turning past the LG still means LG.
  - Otherwise it keeps an EMA of z with α = `ema_alpha`, restarted after any face loss. Margin ≤ −dead_band is LG, ≥ +dead_band is LAPTOP, anything between is UNKNOWN.
- **Face lost:** checked on the first lost frame. If the last face frame was within `face_lost_memory_s` and the margin was ≤ `face_lost_lg_margin`, it **latches LG**; otherwise it returns `(UNKNOWN, None)`.
