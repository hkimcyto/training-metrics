"""Mean-maximal power curve and a Critical Power model fit.

The power curve is the best average power held for every duration. Fitting
the two-parameter Critical Power model, P(t) = W'/t + CP, to the 2-20 minute
part of it gives CP (close to FTP) and W' (the finite energy above CP).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

DURATIONS = [5, 15, 30, 60, 120, 180, 300, 480, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200]


def best_efforts(watts: np.ndarray, durations: Iterable[int] = DURATIONS) -> dict[int, float]:
    """Best rolling average for each duration, O(n) per duration via a cumsum."""
    w = np.nan_to_num(np.asarray(watts, dtype=float))
    c = np.concatenate([[0.0], np.cumsum(w)])
    out: dict[int, float] = {}
    for d in durations:
        if d <= w.size:
            out[d] = float(np.max(c[d:] - c[:-d]) / d)
    return out


def merge_curves(curves: Iterable[dict[int, float]]) -> dict[int, float]:
    best: dict[int, float] = {}
    for curve in curves:
        for d, p in curve.items():
            best[d] = max(best.get(d, 0.0), p)
    return dict(sorted(best.items()))


@dataclass(frozen=True)
class CpFit:
    cp: float
    w_prime: float
    ftp_estimate: float
    r2: float


def fit_critical_power(curve: dict[int, float], lo: int = 120, hi: int = 1200) -> CpFit | None:
    """Linear least squares on work = CP * t + W' (the work-time form is
    linear, so no iterative solver is needed)."""
    pts = [(t, p) for t, p in curve.items() if lo <= t <= hi]
    if len(pts) < 3:
        return None
    t = np.array([x for x, _ in pts], dtype=float)
    work = np.array([x * p for x, p in pts], dtype=float)
    a = np.vstack([t, np.ones_like(t)]).T
    (cp, w_prime), *_ = np.linalg.lstsq(a, work, rcond=None)
    pred = cp * t + w_prime
    r2 = 1 - np.sum((work - pred) ** 2) / (np.sum((work - work.mean()) ** 2) or 1.0)
    twenty = curve.get(1200)
    ftp = 0.95 * twenty if twenty else 0.97 * cp
    return CpFit(float(cp), float(max(w_prime, 0.0)), float(ftp), float(r2))
