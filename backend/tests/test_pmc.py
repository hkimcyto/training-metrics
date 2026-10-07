from datetime import date, timedelta

import numpy as np
import pytest

from app.analytics.pmc import compute_pmc, ewma, project

START = date(2026, 1, 1)


def test_constant_load_converges_to_load():
    days = {START + timedelta(i): 80.0 for i in range(300)}
    pmc = compute_pmc(days, START, START + timedelta(299), ctl_seed=0, atl_seed=0)
    assert pmc[-1].ctl == pytest.approx(80, rel=0.01)
    assert pmc[-1].atl == pytest.approx(80, rel=0.001)


def test_rest_makes_form_positive():
    days = {START + timedelta(i): 100.0 for i in range(60)}
    pmc = compute_pmc(days, START, START + timedelta(70), ctl_seed=50, atl_seed=50)
    assert pmc[59].tsb < 0 < pmc[-1].tsb


def test_ewma_time_constant():
    out = ewma(np.ones(42), 42, seed=0)
    assert out[-1] == pytest.approx(1 - np.exp(-1), rel=1e-6)


def test_projection_matches_recompute():
    days = {START + timedelta(i): 70.0 + (i % 7) * 5 for i in range(80)}
    pmc = compute_pmc(days, START, START + timedelta(79))
    proj = project(pmc[-1], [0.0] * 10)
    full = compute_pmc(days, START, START + timedelta(89))
    assert proj[-1][0] == pytest.approx(full[-1].ctl)
    assert proj[-1][1] == pytest.approx(full[-1].atl)
