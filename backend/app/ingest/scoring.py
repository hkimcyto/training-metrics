"""Turns raw activity data (summary and optional streams) into scored rows,
and resolves the thresholds every score depends on."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import thresholds as est
from app.analytics.efficiency import bike_efficiency, run_efficiency, summary_efficiency
from app.analytics.load import (
    Sport,
    Thresholds,
    WorkoutSummary,
    normalized_graded_speed,
    normalized_power,
    score,
)
from app.analytics.power_curve import best_efforts, merge_curves
from app.db.models import Activity, Athlete

SPORT_MAP = {
    "Swim": Sport.SWIM,
    "OpenWaterSwim": Sport.SWIM,
    "Ride": Sport.BIKE,
    "VirtualRide": Sport.BIKE,
    "GravelRide": Sport.BIKE,
    "MountainBikeRide": Sport.BIKE,
    "EBikeRide": Sport.BIKE,
    "Run": Sport.RUN,
    "TrailRun": Sport.RUN,
    "VirtualRun": Sport.RUN,
    "WeightTraining": Sport.STRENGTH,
    "Workout": Sport.STRENGTH,
    "Crossfit": Sport.STRENGTH,
}


def sport_of(sport_type: str) -> Sport:
    return SPORT_MAP.get(sport_type, Sport.OTHER)


def resolve_thresholds(db: Session, athlete: Athlete) -> tuple[Thresholds, dict[str, str]]:
    """Use what the athlete entered; otherwise estimate from the last 90 days;
    otherwise fall back to population defaults. Returns the sources too."""
    d = Thresholds()
    since = date.today() - timedelta(days=90)
    acts = db.scalars(
        select(Activity).where(Activity.athlete_id == athlete.id, Activity.day >= since)
    ).all()
    sources: dict[str, str] = {}

    ftp = athlete.ftp_watts
    if ftp:
        sources["ftp"] = "set by athlete"
    else:
        curve = merge_curves(a.power_curve for a in acts if a.power_curve)
        e = est.bike_ftp({int(k): v for k, v in curve.items()})
        ftp, sources["ftp"] = (e.value, e.source) if e else (d.ftp_watts, "default")

    run = athlete.run_threshold_speed
    if run:
        sources["run"] = "set by athlete"
    else:
        best: dict[float, float] = {}
        for a in acts:
            if a.sport == "run" and a.distance_m >= 5000 and a.moving_s:
                best[a.distance_m] = min(best.get(a.distance_m, 1e9), a.moving_s)
        # the fastest run of 5 km or more, judged by its Riegel-equivalent hour speed
        cands = [est.riegel_speed_for_duration(dd, t) for dd, t in best.items()]
        run, sources["run"] = (
            (max(cands), "Riegel from best run") if cands else (d.run_threshold_speed, "default")
        )

    css = athlete.css_speed
    if css:
        sources["css"] = "set by athlete"
    else:
        e = est.swim_css((a.distance_m, a.moving_s) for a in acts if a.sport == "swim")
        css, sources["css"] = (e.value, e.source) if e else (d.css_speed, "default")

    max_hr = athlete.max_hr or d.max_hr
    return (
        Thresholds(
            ftp_watts=ftp,
            run_threshold_speed=run,
            css_speed=css,
            lthr=athlete.lthr or round(max_hr * 0.87),
            max_hr=max_hr,
            rest_hr=athlete.rest_hr or d.rest_hr,
        ),
        sources,
    )


def apply_streams(act: Activity, streams: dict[str, list[Any]]) -> None:
    """Derive NP, efficiency, decoupling and the power curve from 1 Hz streams."""
    if not streams:
        return
    hr = np.array(streams.get("heartrate") or [], dtype=float)
    if act.sport == "bike" and streams.get("watts"):
        w = np.array(streams["watts"], dtype=float)
        act.np_watts = normalized_power(w)
        act.power_curve = {str(k): v for k, v in best_efforts(w).items()}
        if hr.size == w.size:
            e = bike_efficiency(w, hr)
            if e:
                act.ef, act.decoupling_pct = e.ef, e.decoupling_pct
    elif act.sport == "run" and streams.get("velocity_smooth"):
        v = np.array(streams["velocity_smooth"], dtype=float)
        g = np.array(streams["grade_smooth"], dtype=float) if streams.get("grade_smooth") else None
        if g is not None and g.size != v.size:
            g = None
        if hr.size == v.size:
            e = run_efficiency(v, hr, g)
            if e:
                act.ef, act.decoupling_pct = e.ef, e.decoupling_pct
        act.avg_speed = act.avg_speed or float(np.mean(v))
        act.graded_speed = normalized_graded_speed(v, g)
    act.has_streams = True


def rescore(act: Activity, t: Thresholds) -> None:
    summary = WorkoutSummary(
        sport=Sport(act.sport),
        moving_s=act.moving_s,
        distance_m=act.distance_m,
        avg_hr=act.avg_hr,
        avg_watts=act.avg_watts,
        np_watts=act.np_watts,
        ngs=act.graded_speed,
        device_watts=act.device_watts,
    )
    r = score(summary, t)
    act.tss, act.tss_method, act.intensity = round(r.tss, 1), r.method.value, r.intensity_factor
    if act.ef is None:
        act.ef = summary_efficiency(
            act.sport, act.avg_speed or 0, act.np_watts or act.avg_watts, act.avg_hr
        )
