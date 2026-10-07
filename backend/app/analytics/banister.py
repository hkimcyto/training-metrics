"""Banister impulse-response model, fitted to the athlete's own data.

Every day of training adds two things: a slow-building fitness effect and a
fast-building fatigue effect that also fades faster. Performance is

    p(t) = p0 + k1 * sum_s w(s) e^{-(t-s)/tau1} - k2 * sum_s w(s) e^{-(t-s)/tau2}

Generic 42/7-day constants are a population average. Fitting k1, k2, tau1 and
tau2 to an athlete's own performance markers (here aerobic efficiency from
steady workouts) gives a personal model, which is then used to search for the
taper that peaks performance on race day.

The fit is regularised toward the textbook constants, so a short or noisy
history degrades gracefully to the standard model instead of overfitting.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

PRIOR = np.array([1.0, 2.0, 42.0, 7.0])  # k1, k2, tau1, tau2
LOWER = np.array([0.01, 0.01, 15.0, 2.0])
UPPER = np.array([10.0, 20.0, 80.0, 25.0])


@dataclass(frozen=True)
class BanisterFit:
    p0: float
    k1: float
    k2: float
    tau1: float
    tau2: float
    r2: float
    n_obs: int
    personalised: bool

    def as_params(self) -> np.ndarray:
        return np.array([self.k1, self.k2, self.tau1, self.tau2])


def _kernel_sums(load: np.ndarray, tau: float) -> np.ndarray:
    """g(t) = sum_{s<t} w(s) e^{-(t-s)/tau}, computed recursively in O(n)."""
    decay = np.exp(-1 / tau)
    g = np.zeros_like(load, dtype=float)
    acc = 0.0
    for i in range(load.size):
        g[i] = acc
        acc = (acc + load[i]) * decay
    return g


def predict(load: np.ndarray, p0: float, params: np.ndarray) -> np.ndarray:
    k1, k2, tau1, tau2 = params
    return p0 + k1 * _kernel_sums(load, tau1) - k2 * _kernel_sums(load, tau2)


def fit(
    load: np.ndarray,
    obs_idx: np.ndarray,
    obs_val: np.ndarray,
    prior_weight: float = 0.15,
    min_obs: int = 12,
    min_r2: float = 0.15,
) -> BanisterFit:
    """Fit to performance observations taken on days ``obs_idx``.

    Observations are standardised first so k1 and k2 come out in standard
    deviations of performance per unit of TSS. Each parameter is pulled
    toward its prior by ``prior_weight`` (in units of its own scale)."""
    obs_idx = np.asarray(obs_idx, dtype=int)
    y = np.asarray(obs_val, dtype=float)
    mu, sd = float(y.mean()) if y.size else 0.0, float(y.std()) if y.size > 1 else 1.0
    sd = sd or 1.0
    z = (y - mu) / sd
    scale = float(np.mean(load)) or 1.0
    w = load / scale  # keeps k1/k2 well conditioned

    if y.size < min_obs:
        return _prior_fit(mu, n_obs=int(y.size))

    def residuals(theta: np.ndarray) -> np.ndarray:
        p0, *params = theta
        pred = predict(w, p0, np.array(params))[obs_idx]
        reg = prior_weight * (np.array(params) - PRIOR) / np.maximum(PRIOR, 1.0)
        return np.concatenate([pred - z, reg * np.sqrt(z.size)])

    x0 = np.concatenate([[0.0], PRIOR])
    lo = np.concatenate([[-50.0], LOWER])
    hi = np.concatenate([[50.0], UPPER])
    res = least_squares(residuals, x0, bounds=(lo, hi), loss="soft_l1", f_scale=1.0)
    p0, k1, k2, tau1, tau2 = res.x
    if tau2 >= tau1:  # fatigue must fade faster than fitness
        return _prior_fit(mu, n_obs=int(y.size))
    pred = predict(w, p0, res.x[1:])[obs_idx]
    ss_res = float(np.sum((z - pred) ** 2))
    ss_tot = float(np.sum((z - z.mean()) ** 2)) or 1.0
    r2 = 1 - ss_res / ss_tot
    if r2 < min_r2:  # the markers don't carry enough signal to trust a personal fit
        fallback = _prior_fit(mu, n_obs=int(y.size))
        return BanisterFit(**{**fallback.__dict__, "r2": r2})
    return BanisterFit(
        p0=float(p0),
        k1=float(k1 / scale),
        k2=float(k2 / scale),
        tau1=float(tau1),
        tau2=float(tau2),
        r2=r2,
        n_obs=int(y.size),
        personalised=True,
    )


def _prior_fit(mu: float, n_obs: int) -> BanisterFit:
    return BanisterFit(0.0, 0.01, 0.02, 42.0, 7.0, r2=0.0, n_obs=n_obs, personalised=False)


# --------------------------------------------------------------------------- taper


@dataclass(frozen=True)
class TaperPlan:
    days: int
    reduction: float  # fraction of normal load removed by race day
    daily_tss: list[float]
    race_day_performance: float
    gain_vs_no_taper: float


def taper_profile(base: float, days: int, reduction: float) -> np.ndarray:
    """Exponential taper: load decays smoothly to (1 - reduction) of base,
    the shape Mujika and Padilla found works better than step cuts."""
    if days <= 0:
        return np.array([])
    t = np.arange(1, days + 1)
    k = -np.log(max(1 - reduction, 1e-3)) / days
    return base * np.exp(-k * t)


def best_taper(
    history: np.ndarray,
    fit_: BanisterFit,
    days_to_race: int,
    base_load: float | None = None,
) -> tuple[TaperPlan, list[TaperPlan]]:
    """Grid-search taper length and depth for the best race-day performance.
    Days before the taper keep the recent average load."""
    if days_to_race < 1:
        raise ValueError("race must be in the future")
    base = float(base_load if base_load is not None else history[-28:].mean())
    params = fit_.as_params()

    def race_perf(future: np.ndarray) -> float:
        series = np.concatenate([history, future, [0.0]])  # race-day morning
        return float(predict(series, fit_.p0, params)[-1])

    pre = days_to_race - 1  # training days between today and race morning
    no_taper = race_perf(np.full(pre, base))
    plans: list[TaperPlan] = []
    # search inside the range the taper literature supports (Bosquet 2007:
    # 8-14 days, 40-60% volume cut), with some room either side
    for days in range(min(5, pre), min(pre, 21) + 1):
        for reduction in np.arange(0.2, 0.651, 0.05):
            taper = taper_profile(base, days, float(reduction))
            build = np.full(pre - days, base)
            future = np.concatenate([build, taper])
            perf = race_perf(future)
            plans.append(
                TaperPlan(days, round(float(reduction), 2), future.tolist(), perf, perf - no_taper)
            )
    best = max(plans, key=lambda p: p.race_day_performance)
    return best, plans
