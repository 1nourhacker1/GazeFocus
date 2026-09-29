import numpy as np
import pytest

from gazefocus.config import ClassifierCfg
from gazefocus.logic.classifier import ZoneClassifier, ZoneModel, features, fit_zone_model, quality
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


def test_fit_maps_screen_means_to_minus_and_plus_one(rng):
    lg, lap = cluster(rng, 80, -34, 7, -0.3, 0.0), cluster(rng, 80, -3, -8, 0.1, 0.0)
    m = fit_zone_model(lg, lap)
    assert m.z(np.array(m.mean_lg)) == pytest.approx(-1.0, abs=1e-9)
    assert m.z(np.array(m.mean_laptop)) == pytest.approx(1.0, abs=1e-9)
    assert m.separation > 4 and quality(m.separation) == "excellent"


def test_fit_ignores_no_face_samples(rng):
    lg = cluster(rng, 40, -34, 7, -0.3, 0.0) + cluster(rng, 30, 0, 0, 0, 0, face=False)
    lap = cluster(rng, 40, -3, -8, 0.1, 0.0)
    m = fit_zone_model(lg, lap)
    assert m.z(np.array(m.mean_lg)) == pytest.approx(-1.0, abs=1e-9)


def test_fit_handles_a_constant_feature(rng):
    lg = [HeadSample(s.t, True, s.yaw, s.pitch, 0.0, 0.0) for s in cluster(rng, 40, -34, 7, 0, 0)]
    lap = [HeadSample(s.t, True, s.yaw, s.pitch, 0.0, 0.0) for s in cluster(rng, 40, -3, -8, 0, 0)]
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
        fit_zone_model(cluster(rng, 4, -34, 7, 0, 0), cluster(rng, 40, -3, -8, 0, 0))
    with pytest.raises(ValueError, match="at least 5"):
        fit_zone_model(cluster(rng, 40, -34, 7, 0, 0, face=False), cluster(rng, 40, -3, -8, 0, 0))


def test_quality_bands():
    assert (quality(4.0), quality(3.99), quality(2.0), quality(1.99)) == ("excellent", "good", "good", "too close")


def test_model_dict_round_trip(rng):
    m = fit_zone_model(cluster(rng, 40, -34, 7, 0, 0), cluster(rng, 40, -3, -8, 0, 0))
    assert ZoneModel.from_dict(m.to_dict()) == m


# Hand-built model: z = yaw/15 + 1  ->  yaw -30 => z -1 (LG), yaw 0 => z +1 (laptop)
TOY = ZoneModel(w=(1 / 15, 0.0, 0.0, 0.0), b=1.0, separation=5.0, mean_lg=(-30, 0, 0, 0), mean_laptop=(0, 0, 0, 0))


def s(t, yaw=None):
    return HeadSample(t=t, face=False) if yaw is None else HeadSample(t=t, face=True, yaw=yaw)


def test_ema_and_dead_band():
    c = ZoneClassifier(TOY, ClassifierCfg())
    assert c.update(s(0.0, 0)) == (Zone.LAPTOP, pytest.approx(1.0))
    zone, m = c.update(s(0.1, -30))  # 1 + 0.35 * (-1 - 1) = 0.30
    assert zone is Zone.LAPTOP and m == pytest.approx(0.30)
    zone, m = c.update(s(0.2, -30))  # 0.30 + 0.35 * (-1.30) = -0.155
    assert zone is Zone.UNKNOWN and m == pytest.approx(-0.155)
    zone, m = c.update(s(0.3, -30))  # -0.155 + 0.35 * (-0.845) = -0.45075
    assert zone is Zone.LG and m == pytest.approx(-0.45075)


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


def test_features_order():
    assert list(features(HeadSample(0, True, 1, 2, 3, 4))) == [1, 2, 3, 4]
