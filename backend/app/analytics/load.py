"""Training Stress Score (TSS) for each sport.

Every workout is reduced to one number on a common scale, where 100 means
one hour at threshold. The method depends on what the workout recorded:

* bike with power      -> power TSS from Normalized Power (Coggan)
* run with pace        -> rTSS from grade-adjusted pace vs threshold pace
* swim                 -> sTSS from pace vs Critical Swim Speed (cubed)
* anything with HR     -> hrTSS from Banister TRIMP, scaled to an hour at LTHR
* Strava summary only  -> Relative Effort, rescaled to TSS using the athlete's
                          own workouts that have both numbers
* strength / other     -> duration-based estimate

The functions are pure and work on plain numbers or numpy arrays so they can
be tested without a database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class Sport(StrEnum):
    SWIM = "swim"
    BIKE = "bike"
    RUN = "run"
    STRENGTH = "strength"
    OTHER = "other"


class TssMethod(StrEnum):
    POWER = "power"
    PACE = "pace"
    SWIM_PACE = "swim_pace"
    HEART_RATE = "heart_rate"
    RELATIVE_EFFORT = "relative_effort"
    DURATION = "duration"


@dataclass(frozen=True)
class Thresholds:
    """The athlete's current threshold markers. All speeds in m/s."""

    ftp_watts: float = 214.0
    run_threshold_speed: float = 4.17  # ~6:26 /mi
    css_speed: float = 0.95  # ~1:36 /100yd
    lthr: float = 165.0
    max_hr: float = 192.0
    rest_hr: float = 50.0
    strength_tss_per_hour: float = 30.0
    # TSS per point of Strava Relative Effort, calibrated per athlete from
    # workouts that have both (see ingest.scoring.resolve_thresholds)
    re_scale: float = 0.8


@dataclass(frozen=True)
class TssResult:
    tss: float
    method: TssMethod
    intensity_factor: float | None = None


# --------------------------------------------------------------------------- power


def normalized_power(watts: np.ndarray, sample_seconds: float = 1.0) -> float:
    """Coggan Normalized Power: 30 s rolling mean, raised to the 4th power,
    averaged, then the 4th root. Falls back to the plain mean for rides
    shorter than the rolling window."""
    w = np.asarray(watts, dtype=float)
    w = np.nan_to_num(w, nan=0.0)
    window = max(1, int(round(30 / sample_seconds)))
    if w.size < window:
        return float(w.mean()) if w.size else 0.0
    kernel = np.ones(window) / window
    rolling = np.convolve(w, kernel, mode="valid")
    return float(np.mean(rolling**4) ** 0.25)


def power_tss(duration_s: float, np_watts: float, ftp: float) -> TssResult:
    if ftp <= 0 or duration_s <= 0:
        return TssResult(0.0, TssMethod.POWER, 0.0)
    intensity = np_watts / ftp
    tss = duration_s * np_watts * intensity / (ftp * 3600) * 100
    return TssResult(tss, TssMethod.POWER, intensity)


# ---------------------------------------------------------------------------- run


def grade_adjusted_speed(speed: np.ndarray, grade_pct: np.ndarray) -> np.ndarray:
    """Convert speed on a slope to the equivalent flat speed using the Minetti
    (2002) metabolic cost of running polynomial, normalised to flat ground."""
    g = np.clip(np.asarray(grade_pct, dtype=float) / 100.0, -0.45, 0.45)
    cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    return np.asarray(speed, dtype=float) * cost / 3.6


def normalized_graded_speed(speed: np.ndarray, grade_pct: np.ndarray | None = None) -> float:
    """Like Normalized Power but for running: weights hard surges the way the
    body experiences them rather than taking the plain average."""
    s = np.nan_to_num(np.asarray(speed, dtype=float))
    if grade_pct is not None:
        s = grade_adjusted_speed(s, grade_pct)
    s = s[s > 0.5]  # drop standing still
    if s.size == 0:
        return 0.0
    window = 30
    if s.size < window:
        return float(s.mean())
    rolling = np.convolve(s, np.ones(window) / window, mode="valid")
    return float(np.mean(rolling**4) ** 0.25)


def run_tss(duration_s: float, ngs: float, threshold_speed: float) -> TssResult:
    if threshold_speed <= 0 or duration_s <= 0 or ngs <= 0:
        return TssResult(0.0, TssMethod.PACE, 0.0)
    intensity = ngs / threshold_speed
    return TssResult(duration_s / 3600 * intensity**2 * 100, TssMethod.PACE, intensity)


# --------------------------------------------------------------------------- swim


def swim_tss(duration_s: float, distance_m: float, css_speed: float) -> TssResult:
    """sTSS uses the cube of intensity because drag rises with the square of
    speed, so the power cost of swimming faster climbs steeply."""
    if css_speed <= 0 or duration_s <= 0 or distance_m <= 0:
        return TssResult(0.0, TssMethod.SWIM_PACE, 0.0)
    intensity = (distance_m / duration_s) / css_speed
    return TssResult(duration_s / 3600 * intensity**3 * 100, TssMethod.SWIM_PACE, intensity)


# ----------------------------------------------------------------------------- hr


def trimp(
    duration_s: float, avg_hr: float, rest_hr: float, max_hr: float, male: bool = True
) -> float:
    """Banister TRIMP. Heart-rate reserve weighted exponentially so time near
    max counts far more than easy time."""
    if max_hr <= rest_hr:
        return 0.0
    hrr = min(max((avg_hr - rest_hr) / (max_hr - rest_hr), 0.0), 1.0)
    a, b = (0.64, 1.92) if male else (0.86, 1.67)
    return duration_s / 60 * hrr * a * math.exp(b * hrr)


def hr_tss(duration_s: float, avg_hr: float, t: Thresholds) -> TssResult:
    one_hour_at_lthr = trimp(3600, t.lthr, t.rest_hr, t.max_hr)
    if one_hour_at_lthr <= 0:
        return TssResult(0.0, TssMethod.HEART_RATE)
    value = trimp(duration_s, avg_hr, t.rest_hr, t.max_hr) / one_hour_at_lthr * 100
    return TssResult(value, TssMethod.HEART_RATE, avg_hr / t.lthr)


# ------------------------------------------------------------------------ dispatch


@dataclass
class WorkoutSummary:
    """The minimum needed to score a workout, from a stream or a summary."""

    sport: Sport
    moving_s: float
    distance_m: float = 0.0
    avg_hr: float | None = None
    avg_watts: float | None = None
    np_watts: float | None = None
    ngs: float | None = None  # normalized graded speed, m/s
    device_watts: bool = False
    relative_effort: float | None = None


def score(w: WorkoutSummary, t: Thresholds) -> TssResult:
    """Pick the most accurate method the workout's data allows."""
    if w.moving_s <= 0:
        return TssResult(0.0, TssMethod.DURATION)

    if w.sport is Sport.BIKE and w.device_watts and (w.np_watts or w.avg_watts):
        return power_tss(w.moving_s, float(w.np_watts or w.avg_watts), t.ftp_watts)

    if w.sport is Sport.RUN:
        speed = w.ngs or (w.distance_m / w.moving_s if w.distance_m else 0)
        if speed > 0:
            return run_tss(w.moving_s, speed, t.run_threshold_speed)

    if w.sport is Sport.SWIM and w.distance_m > 0:
        return swim_tss(w.moving_s, w.distance_m, t.css_speed)

    if w.avg_hr:
        return hr_tss(w.moving_s, w.avg_hr, t)

    if w.relative_effort and w.sport is not Sport.STRENGTH:
        return TssResult(w.relative_effort * t.re_scale, TssMethod.RELATIVE_EFFORT)

    per_hour = t.strength_tss_per_hour if w.sport is Sport.STRENGTH else 40.0
    return TssResult(w.moving_s / 3600 * per_hour, TssMethod.DURATION)
