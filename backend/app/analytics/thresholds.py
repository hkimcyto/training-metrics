"""Estimate threshold markers from training history when the athlete hasn't
entered them. Each estimate states where it came from so the UI can show it."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from .power_curve import fit_critical_power

RIEGEL = 1.06


@dataclass(frozen=True)
class Estimate:
    value: float
    source: str


def riegel_speed_for_duration(distance_m: float, time_s: float, target_s: float = 3600) -> float:
    """Speed sustainable for ``target_s`` given one race-effort result,
    using Riegel's endurance model T2 = T1 (D2/D1)^1.06."""
    d2 = distance_m * (target_s / time_s) ** (1 / RIEGEL)
    return d2 / target_s


def run_threshold_from_vo2max(vo2max: float) -> float:
    """Threshold speed (m/s) implied by a VO2 max, from Daniels & Gilbert's
    oxygen cost of running, VO2 = -4.60 + 0.182258 v + 0.000104 v^2 with v in
    m/min. Threshold pace sits at about 88% of VO2 max."""
    a, b, c = 0.000104, 0.182258, -4.60 - 0.88 * vo2max
    return (-b + float(np.sqrt(b * b - 4 * a * c))) / (2 * a) / 60


def run_threshold(best_efforts: dict[float, float]) -> Estimate | None:
    """best_efforts maps distance (m) to best time (s). Uses the longest
    effort of at least 5 km, since short efforts overstate threshold."""
    usable = {d: t for d, t in best_efforts.items() if d >= 5000}
    if not usable:
        return None
    d = max(usable)
    return Estimate(riegel_speed_for_duration(d, usable[d]), f"Riegel from best {d / 1000:g} km")


def bike_ftp(curve: dict[int, float]) -> Estimate | None:
    fit = fit_critical_power(curve)
    if fit is None:
        return None
    src = "95% of best 20 min" if 1200 in curve else "Critical Power fit"
    return Estimate(fit.ftp_estimate, src)


def swim_css(sessions: Iterable[tuple[float, float]]) -> Estimate | None:
    """sessions are (distance_m, moving_s). Session averages include easy
    and drill sets, so CSS sits above the faster sessions' average pace."""
    speeds = np.array([d / t for d, t in sessions if d >= 1000 and t > 0])
    if speeds.size < 3:
        return None
    return Estimate(float(np.percentile(speeds, 90) * 1.08), "from pool session paces")
