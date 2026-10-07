import numpy as np
import pytest

from app.analytics.banister import best_taper, fit, predict


def synthetic(k1=0.02, k2=0.05, tau1=38.0, tau2=8.0, days=240, seed=1):
    rng = np.random.default_rng(seed)
    load = np.clip(rng.normal(80, 25, days), 0, None)
    load[::7] = 0
    perf = predict(load, 0.0, np.array([k1, k2, tau1, tau2]))
    idx = np.arange(20, days, 3)
    return load, idx, perf[idx] + rng.normal(0, 0.05 * perf.std(), idx.size)


def test_fit_recovers_time_constants():
    load, idx, obs = synthetic()
    f = fit(load, idx, obs, prior_weight=0.02)
    assert f.personalised
    assert f.r2 > 0.8
    assert f.tau1 == pytest.approx(38, rel=0.25)
    assert f.tau2 == pytest.approx(8, rel=0.35)


def test_short_history_falls_back_to_prior():
    load, idx, obs = synthetic(days=40)
    f = fit(load, idx[:5], obs[:5])
    assert not f.personalised and f.tau1 == 42


def test_taper_beats_training_through():
    load, idx, obs = synthetic()
    f = fit(load, idx, obs)
    best, plans = best_taper(load, f, days_to_race=21)
    assert best.gain_vs_no_taper > 0
    assert 3 <= best.days <= 21
    assert len(plans) > 50


def test_weak_signal_falls_back_to_standard_model():
    rng = np.random.default_rng(3)
    load = np.clip(rng.normal(80, 25, 200), 0, None)
    idx = np.arange(20, 200, 4)
    noise = rng.normal(0, 1, idx.size)  # performance unrelated to load
    f = fit(load, idx, noise)
    assert not f.personalised and f.tau1 == 42 and f.tau2 == 7
