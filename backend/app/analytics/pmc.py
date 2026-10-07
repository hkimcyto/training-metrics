"""Performance Management Chart: fitness (CTL), fatigue (ATL) and form (TSB).

CTL and ATL are exponentially weighted averages of daily TSS with time
constants of 42 and 7 days. Form is yesterday's fitness minus yesterday's
fatigue, which is how freshness on a given morning is usually defined.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

CTL_DAYS = 42
ATL_DAYS = 7


@dataclass(frozen=True)
class PmcDay:
    day: date
    tss: float
    ctl: float
    atl: float
    tsb: float
    ramp: float  # CTL change over the last 7 days


def daily_series(tss_by_day: Mapping[date, float], start: date, end: date) -> np.ndarray:
    n = (end - start).days + 1
    out = np.zeros(n)
    for d, v in tss_by_day.items():
        i = (d - start).days
        if 0 <= i < n:
            out[i] += v
    return out


def ewma(load: np.ndarray, tau: float, seed: float = 0.0) -> np.ndarray:
    """Exponential decay form, exact for any time constant."""
    k = 1 - np.exp(-1 / tau)
    out = np.empty_like(load, dtype=float)
    prev = seed
    for i, x in enumerate(load):
        prev = prev + k * (x - prev)
        out[i] = prev
    return out


def compute_pmc(
    tss_by_day: Mapping[date, float],
    start: date,
    end: date,
    ctl_seed: float | None = None,
    atl_seed: float | None = None,
) -> list[PmcDay]:
    """Build the chart day by day. Without seeds, both averages start at the
    mean daily load of the first two weeks so the first month isn't distorted
    by a cold start at zero."""
    load = daily_series(tss_by_day, start, end)
    if load.size == 0:
        return []
    warm = float(load[: min(14, load.size)].mean())
    ctl = ewma(load, CTL_DAYS, warm if ctl_seed is None else ctl_seed)
    atl = ewma(load, ATL_DAYS, warm if atl_seed is None else atl_seed)
    days: list[PmcDay] = []
    for i in range(load.size):
        prev_ctl = ctl[i - 1] if i else (warm if ctl_seed is None else ctl_seed)
        prev_atl = atl[i - 1] if i else (warm if atl_seed is None else atl_seed)
        ramp = ctl[i] - ctl[i - 7] if i >= 7 else ctl[i] - ctl[0]
        days.append(
            PmcDay(
                day=start + timedelta(days=i),
                tss=float(load[i]),
                ctl=float(ctl[i]),
                atl=float(atl[i]),
                tsb=float(prev_ctl - prev_atl),
                ramp=float(ramp),
            )
        )
    return days


def project(last: PmcDay, planned_tss: Iterable[float]) -> list[tuple[float, float, float]]:
    """Roll fitness and fatigue forward over a planned load, e.g. a taper.
    Returns (ctl, atl, tsb) for each future day."""
    kc, ka = 1 - np.exp(-1 / CTL_DAYS), 1 - np.exp(-1 / ATL_DAYS)
    ctl, atl = last.ctl, last.atl
    out = []
    for x in planned_tss:
        tsb = ctl - atl
        ctl += kc * (x - ctl)
        atl += ka * (x - atl)
        out.append((ctl, atl, tsb))
    return out


def acute_chronic_ratio(days: list[PmcDay]) -> float | None:
    """ATL/CTL. Above roughly 1.5 is the zone injury research flags as risky."""
    if not days or days[-1].ctl <= 0:
        return None
    return days[-1].atl / days[-1].ctl
