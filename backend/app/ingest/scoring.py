"""Turns raw activity data (summary and optional streams) into scored rows,
and resolves the thresholds every score depends on."""

from __future__ import annotations

from dataclasses import replace
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
    hr_tss,
    normalized_graded_speed,
    normalized_power,
    score,
)
from app.analytics.power_curve import best_efforts, merge_curves
from app.db.models import Activity, Athlete, WellnessDay

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
    """Use what the athlete entered; then what Garmin has measured; otherwise
    estimate from the last 90 days; otherwise fall back to population
    defaults. Returns the sources too."""
    d = Thresholds()
    since = date.today() - timedelta(days=90)
    acts = db.scalars(
        select(Activity).where(Activity.athlete_id == athlete.id, Activity.day >= since)
    ).all()
    sources: dict[str, str] = {}
    garmin = athlete.garmin_profile or {}

    ftp = athlete.ftp_watts
    if ftp:
        sources["ftp"] = "set by athlete"
    elif garmin.get("ftp_watts"):
        ftp, sources["ftp"] = garmin["ftp_watts"], "Garmin FTP"
    else:
        curve = merge_curves(a.power_curve for a in acts if a.power_curve)
        e = est.bike_ftp({int(k): v for k, v in curve.items()})
        ftp, sources["ftp"] = (e.value, e.source) if e else (d.ftp_watts, "default")

    run = athlete.run_threshold_speed
    vo2 = db.scalar(
        select(WellnessDay.vo2max)
        .where(
            WellnessDay.athlete_id == athlete.id,
            WellnessDay.vo2max.is_not(None),
            WellnessDay.day >= date.today() - timedelta(days=60),
        )
        .order_by(WellnessDay.day.desc())
    )
    if run:
        sources["run"] = "set by athlete"
    elif garmin.get("run_threshold_speed"):
        run, sources["run"] = garmin["run_threshold_speed"], "Garmin lactate threshold"
    elif vo2:
        run, sources["run"] = est.run_threshold_from_vo2max(vo2), f"Garmin VO2 max {vo2:.0f}"
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

    max_hr = athlete.max_hr or garmin.get("max_hr") or d.max_hr
    rest = db.scalars(
        select(WellnessDay.rest_hr).where(
            WellnessDay.athlete_id == athlete.id,
            WellnessDay.rest_hr.is_not(None),
            WellnessDay.day >= date.today() - timedelta(days=30),
        )
    ).all()
    base = Thresholds(
        ftp_watts=ftp,
        run_threshold_speed=run,
        css_speed=css,
        lthr=athlete.lthr or garmin.get("lthr") or round(max_hr * 0.87),
        max_hr=max_hr,
        rest_hr=athlete.rest_hr or (float(np.median(rest)) if rest else d.rest_hr),
    )
    # calibrate Relative Effort against heart-rate TSS on workouts that have both
    ratios = [
        hr_tss(a.moving_s, a.avg_hr, base).tss / a.relative_effort
        for a in acts
        if a.avg_hr and a.relative_effort and a.relative_effort >= 10 and a.sport in ("bike", "run")
    ]
    if len(ratios) >= 5:
        sources["re_scale"] = f"calibrated on {len(ratios)} workouts"
        return replace(base, re_scale=float(np.median(ratios))), sources
    sources["re_scale"] = "default"
    return base, sources


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
        relative_effort=act.relative_effort,
    )
    r = score(summary, t)
    act.tss, act.tss_method, act.intensity = round(r.tss, 1), r.method.value, r.intensity_factor
    if act.ef is None:
        act.ef = summary_efficiency(
            act.sport, act.avg_speed or 0, act.np_watts or act.avg_watts, act.avg_hr
        )
