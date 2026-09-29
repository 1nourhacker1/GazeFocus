# gazefocus/logic/classifier.py
Verified against: GazeFocus@38de0cc · 2026-09-29

**Fit** (`fit_zone_model`):
1. Keep only the face samples; each screen needs at least 5, otherwise `ValueError` ("at least 5").
2. Standardize each feature (yaw, pitch, iris_h, iris_v) with the pooled mean and standard deviation. A feature with zero spread gets scale 1.
3. Two-class LDA with a pooled within-class covariance plus ridge 1e-3.
4. Rescale so the LG mean projects to **−1** and the laptop mean to **+1**. The result is stored as `z = w·f + b` in raw feature units.
5. `separation` = the Mahalanobis distance between the means (Fisher). Identical clusters raise `ValueError` ("indistinguishable").
6. `quality()`: ≥ 4 is excellent, ≥ 2 is good, anything lower is too close.

**Per frame** (`ZoneClassifier.update`):
- Face present: EMA of z with α = `ema_alpha`, restarted after any face loss. Margin ≤ −dead_band is LG, ≥ +dead_band is LAPTOP, anything between is UNKNOWN.
- Face lost: the check happens once, on the first lost frame. If the last face frame was within `face_lost_memory_s` and the margin was ≤ `face_lost_lg_margin`, it **latches LG** and returns the last margin. Otherwise it returns `(UNKNOWN, None)`.
- The latch holds until the face returns.
