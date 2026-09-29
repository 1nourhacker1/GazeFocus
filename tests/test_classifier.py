import numpy as np
import pytest

from gazefocus.config import ClassifierCfg
from gazefocus.logic.classifier import FEATURES, ZoneClassifier, ZoneModel, features, fit_zone_model, quality
from gazefocus.types import HeadSample, Zone


def cluster(rng, n, yaw, pitch, ih, iv, spread=(4.0, 3.0, 0.1, 0.1), face=True):
    out = []
    for i in range(n):
        y, p, h, v = rng.normal((yaw, pitch, ih, iv), spread)
        out.append(HeadSample(t=i / 15, face=face, yaw=y, pitch=p, iris_h=h, iris_v=v))
    return out


@pytest.fixture
def rng():
    return np.random.default_rng(7)


def test_features_are_yaw_pitch_iris_h():
    assert FEATURES == ("yaw", "pitch", "iris_h")
    assert list(features(HeadSample(0, True, 1, 2, 3, 4))) == [1, 2, 3]


def test_fit_maps_screen_means_to_minus_and_plus_one(rng):
    lg, lap = cluster(rng, 80, 32, 7, 0.2, 0.0), cluster(rng, 80, -2, 12, 0.0, 0.0)
    m = fit_zone_model(lg, lap)
    assert m.z(np.array(m.mean_lg)) == pytest.approx(-1.0, abs=1e-9)
    assert m.z(np.array(m.mean_laptop)) == pytest.approx(1.0, abs=1e-9)
    assert m.separation > 4 and quality(m.separation) == "excellent"
    assert len(m.sd) == len(FEATURES) and all(v > 0 for v in m.sd)


def test_weights_follow_mean_differences_not_correlations(rng):
    """Desk session 2026-09-29: full-covariance LDA gave pitch a weight whose sign contradicted
    the class means, because pitch and eyelid noise were correlated. Weights must follow the
    per-feature mean difference."""
    lg, lap = [], []
    for i in range(80):
        for out, yaw, ih in ((lg, 32.0, 0.05), (lap, -2.0, 0.0)):
            n = rng.normal()
            out.append(HeadSample(i / 15, True, yaw=yaw + rng.normal(0, 5), pitch=10 + 5 * n, iris_h=ih + 0.1 * n))
    m = fit_zone_model(lg, lap)
    diff = np.array(m.mean_laptop) - np.array(m.mean_lg)
    for w, d in zip(m.w, diff):
        assert w == 0 or np.sign(w) == np.sign(d)
    assert abs(m.w[0] * m.sd[0]) > 5 * abs(m.w[1] * m.sd[1])  # yaw dominates pitch


def test_looking_down_at_the_laptop_stays_laptop(rng):
    lg, lap = cluster(rng, 80, 30, 8, 0.2, 0.0), cluster(rng, 80, 0, 12, 0.0, 0.0)
    c = ZoneClassifier(fit_zone_model(lg, lap), ClassifierCfg())
    zone, _ = c.update(HeadSample(0.0, True, yaw=0.0, pitch=18.0, iris_h=0.0))
    assert zone is Zone.LAPTOP


def test_turn_frames_are_trimmed_from_calibration(rng):
    lg = cluster(rng, 60, 30, 8, 0.2, 0.0) + cluster(rng, 20, 2, 12, 0.0, 0.0)  # 25 % leaked laptop frames
    lap = cluster(rng, 80, 0, 12, 0.0, 0.0)
    m = fit_zone_model(lg, lap)
    assert m.mean_lg[0] == pytest.approx(30, abs=2.0)


def test_fit_handles_a_constant_feature(rng):
    lg = [HeadSample(s.t, True, s.yaw, s.pitch, 0.0, 0.0) for s in cluster(rng, 40, 32, 7, 0, 0)]
    lap = [HeadSample(s.t, True, s.yaw, s.pitch, 0.0, 0.0) for s in cluster(rng, 40, -2, 12, 0, 0)]
    m = fit_zone_model(lg, lap)
    assert np.all(np.isfinite(m.w)) and m.separation > 4


def test_overlapping_clusters_rate_too_close(rng):
    m = fit_zone_model(cluster(rng, 60, -10, 0, 0, 0), cluster(rng, 60, -9, 0, 0, 0))
    assert quality(m.separation) == "too close"


def test_fit_rejects_identical_clusters():  # Review Focus #4
    same = [HeadSample(i / 15, True, -10.0 + (i % 3), 0.0 + (i % 2), 0.0, 0.0) for i in range(30)]
    with pytest.raises(ValueError, match="indistinguishable"):
        fit_zone_model(same, list(same))


def test_fit_rejects_too_few_samples(rng):  # Review Focus #4
    with pytest.raises(ValueError, match="at least 5"):
        fit_zone_model(cluster(rng, 4, 32, 7, 0, 0), cluster(rng, 40, -2, 12, 0, 0))
    with pytest.raises(ValueError, match="at least 5"):
        fit_zone_model(cluster(rng, 40, 32, 7, 0, 0, face=False), cluster(rng, 40, -2, 12, 0, 0))


def test_quality_bands():
    assert (quality(4.0), quality(3.99), quality(2.0), quality(1.99)) == ("excellent", "good", "good", "too close")


def test_model_dict_round_trip(rng):
    m = fit_zone_model(cluster(rng, 40, 32, 7, 0, 0), cluster(rng, 40, -2, 12, 0, 0))
    assert ZoneModel.from_dict(m.to_dict()) == m


# Hand-built model: z = yaw/15 + 1  ->  yaw -30 => z -1 (LG), yaw 0 => z +1 (laptop); pitch sd 5
TOY = ZoneModel(w=(1 / 15, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 10, 0), mean_laptop=(0, 10, 0), sd=(10.0, 5.0, 0.1))


def s(t, yaw=None, pitch=10.0):
    return HeadSample(t=t, face=False) if yaw is None else HeadSample(t=t, face=True, yaw=yaw, pitch=pitch)


def test_ema_and_dead_band():
    c = ZoneClassifier(TOY, ClassifierCfg())
    assert c.update(s(0.0, 0)) == (Zone.LAPTOP, pytest.approx(1.0))
    zone, m = c.update(s(0.1, -30))  # 1 + 0.35 * (-1 - 1) = 0.30
    assert zone is Zone.LAPTOP and m == pytest.approx(0.30)
    zone, m = c.update(s(0.2, -30))  # 0.30 + 0.35 * (-1.30) = -0.155
    assert zone is Zone.UNKNOWN and m == pytest.approx(-0.155)
    zone, m = c.update(s(0.3, -30))  # -0.155 + 0.35 * (-0.845) = -0.45075
    assert zone is Zone.LG and m == pytest.approx(-0.45075)


def test_far_off_pitch_is_unknown_and_not_fed_to_the_ema():
    """Desk session: leaning down to a phone (pitch +28, both screens ~+10) produced a switch."""
    c = ZoneClassifier(TOY, ClassifierCfg())
    c.update(s(0.0, 0))
    assert c.update(s(0.1, -30, pitch=10 + 3.6 * 5)) == (Zone.UNKNOWN, None)  # 3.6 sd > 3.5
    zone, m = c.update(s(0.2, 0))
    assert zone is Zone.LAPTOP and m == pytest.approx(1.0)  # the outlier never entered the EMA


def test_yaw_past_the_lg_is_not_an_outlier():
    c = ZoneClassifier(TOY, ClassifierCfg())
    assert c.update(s(0.0, -80))[0] is Zone.LG  # turned far beyond the LG: still LG


def test_face_lost_after_hard_left_turn_latches_lg():
    c = ZoneClassifier(TOY, ClassifierCfg())
    c.update(s(0.0, -45))  # z = -2.0 <= -1.2
    assert c.update(s(0.066)) == (Zone.LG, pytest.approx(-2.0))
    assert c.update(s(2.0)) == (Zone.LG, pytest.approx(-2.0))  # stays latched while lost
    assert c.update(s(2.1, 0)) == (Zone.LAPTOP, pytest.approx(1.0))  # EMA restarts on reacquire


def test_face_lost_after_mild_lg_is_unknown():
    c = ZoneClassifier(TOY, ClassifierCfg())
    c.update(s(0.0, -30))  # z = -1.0 > -1.2
    assert c.update(s(0.066)) == (Zone.UNKNOWN, None)


def test_face_lost_after_a_long_gap_is_unknown():
    c = ZoneClassifier(TOY, ClassifierCfg())
    c.update(s(0.0, -45))
    assert c.update(s(0.5)) == (Zone.UNKNOWN, None)  # 0.5 s > face_lost_memory_s (0.3)
