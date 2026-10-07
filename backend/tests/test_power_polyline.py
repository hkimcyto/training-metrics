import numpy as np
import pytest

from app.analytics.polyline import decode, encode, heat_grid
from app.analytics.power_curve import best_efforts, fit_critical_power


def test_polyline_known_value():
    # Example from Google's polyline documentation
    pts = decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert pts == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_polyline_round_trip():
    pts = [(37.7749, -122.4194), (37.7755, -122.4180), (37.7801, -122.4100)]
    assert decode(encode(pts)) == pytest.approx(pts)


def test_heat_grid_counts_routes_not_points():
    route = [(37.0, -122.0)] * 50
    grid = heat_grid([route, route])
    assert max(c for *_, c in grid) == 2


def test_critical_power_recovers_parameters():
    cp, wp = 230.0, 18_000.0
    curve = {t: wp / t + cp for t in (120, 180, 300, 480, 600, 900, 1200)}
    f = fit_critical_power(curve)
    assert f.cp == pytest.approx(cp)
    assert f.w_prime == pytest.approx(wp)


def test_best_efforts_finds_the_hard_block():
    w = np.r_[np.full(600, 150.0), np.full(300, 280.0), np.full(600, 150.0)]
    assert best_efforts(w, [300])[300] == pytest.approx(280)
