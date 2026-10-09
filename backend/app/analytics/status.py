"""Training status in the spirit of Garmin's, for athletes without a watch
that reports one.

Garmin weighs three things: whether fitness (VO2 max) is moving, whether
recent load is in a sensible band against the long-term load, and whether
HRV says the body is coping. Without VO2 max, the 28-day change in fitness
(CTL) stands in for the fitness trend, and the acute:chronic load ratio
(ATL/CTL) for the load band.
"""

from __future__ import annotations

STATUSES = ("PEAKING", "PRODUCTIVE", "MAINTAINING", "RECOVERY", "STRAINED", "DETRAINING")


def classify(
    ctl_change_28d: float, ctl: float, tsb: float, acwr: float | None, hrv_low_nights: int
) -> str:
    """One day's status from fitness trend, load ratio, form and HRV.

    `hrv_low_nights` counts nights in the last week below the athlete's own
    HRV range; three or more is the body asking for a break."""
    if ctl < 5:
        return "NO_STATUS"
    ratio = acwr if acwr is not None else 1.0
    rising = ctl_change_28d >= 0.05 * ctl
    falling = ctl_change_28d <= -0.08 * ctl
    if hrv_low_nights >= 3 or tsb < -30:
        return "STRAINED"
    if rising and tsb > 0 and ratio < 0.9:
        return "PEAKING"  # fitness built, load backing off: a taper
    if falling and ratio < 0.7:
        return "DETRAINING"
    if ratio < 0.8:
        return "RECOVERY"
    if rising:
        return "PRODUCTIVE"
    return "MAINTAINING"
