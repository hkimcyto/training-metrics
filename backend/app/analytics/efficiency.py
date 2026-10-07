"""Aerobic efficiency markers from steady workouts.

Efficiency Factor (EF) is output per heartbeat: Normalized Power / avg HR on
the bike, or graded speed / avg HR running. When aerobic fitness improves, EF
rises for the same effort.

Aerobic decoupling (Pa:HR) compares EF in the first and second halves of a
long steady session. Under about 5% means the athlete held output without
heart rate drifting upward, a standard sign of endurance being in place for
that duration.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .load import normalized_graded_speed, normalized_power


@dataclass(frozen=True)
class Efficiency:
    ef: float
    decoupling_pct: float | None


def _halves(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mid = x.size // 2
    return x[:mid], x[mid:]


def bike_efficiency(watts: np.ndarray, hr: np.ndarray) -> Efficiency | None:
    hr = np.asarray(hr, dtype=float)
    if hr.size < 600 or np.nanmean(hr) < 80:
        return None
    ef = normalized_power(watts) / float(np.nanmean(hr))
    w1, w2 = _halves(np.asarray(watts, dtype=float))
    h1, h2 = _halves(hr)
    ef1 = normalized_power(w1) / float(np.nanmean(h1))
    ef2 = normalized_power(w2) / float(np.nanmean(h2))
    return Efficiency(ef, (ef1 - ef2) / ef1 * 100 if ef1 else None)


def run_efficiency(
    speed: np.ndarray, hr: np.ndarray, grade: np.ndarray | None = None
) -> Efficiency | None:
    hr = np.asarray(hr, dtype=float)
    if hr.size < 600 or np.nanmean(hr) < 80:
        return None
    ef = normalized_graded_speed(speed, grade) * 60 / float(np.nanmean(hr))  # m/min per bpm
    s1, s2 = _halves(np.asarray(speed, dtype=float))
    h1, h2 = _halves(hr)
    g1, g2 = _halves(np.asarray(grade, dtype=float)) if grade is not None else (None, None)
    ef1 = normalized_graded_speed(s1, g1) / float(np.nanmean(h1))
    ef2 = normalized_graded_speed(s2, g2) / float(np.nanmean(h2))
    return Efficiency(ef, (ef1 - ef2) / ef1 * 100 if ef1 else None)


def summary_efficiency(
    sport: str, avg_speed: float, avg_watts: float | None, avg_hr: float | None
) -> float | None:
    """EF from summary numbers when no stream is stored."""
    if not avg_hr or avg_hr < 80:
        return None
    if sport == "bike" and avg_watts:
        return avg_watts / avg_hr
    if sport == "run" and avg_speed:
        return avg_speed * 60 / avg_hr
    return None
