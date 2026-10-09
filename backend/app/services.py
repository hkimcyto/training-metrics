"""Read-side services: everything the dashboard shows is computed here from
stored activities and wellness days. Kept separate from the HTTP layer so it
can be tested directly."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import banister, pmc, status
from app.analytics.power_curve import fit_critical_power, merge_curves
from app.analytics.race import RACE_TYPES, AthleteProfile, Course, resolve_race, simulate
from app.analytics.races_catalog import CATALOG
from app.db.models import Activity, Athlete, Race, WellnessDay
from app.ingest.scoring import resolve_thresholds

ENDURANCE = ("swim", "bike", "run")


def _today(db: Session, athlete: Athlete) -> date:
    """Demo data is frozen in time, so 'today' is its last activity day."""
    if athlete.is_demo:
        last = db.scalar(
            select(Activity.day)
            .where(Activity.athlete_id == athlete.id)
            .order_by(Activity.day.desc())
        )
        return last or date.today()
    return date.today()


def activities(db: Session, athlete: Athlete, since: date | None = None) -> list[Activity]:
    q = select(Activity).where(Activity.athlete_id == athlete.id)
    if since:
        q = q.where(Activity.day >= since)
    return list(db.scalars(q.order_by(Activity.start_time)).all())


def tss_by_day(acts: list[Activity]) -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for a in acts:
        out[a.day] += a.tss
    return out


# ----------------------------------------------------------------- overview


def weekly(db: Session, athlete: Athlete, weeks: int = 12) -> list[dict[str, Any]]:
    today = _today(db, athlete)
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=weeks - 1)
    rows = {
        start + timedelta(weeks=i): {
            "week": (start + timedelta(weeks=i)).isoformat(),
            **{f"{s}_s": 0.0 for s in ENDURANCE},
            **{f"{s}_m": 0.0 for s in ENDURANCE},
            "strength_sessions": 0,
            "tss": 0.0,
            "longest_ride_s": 0.0,
            "longest_run_s": 0.0,
        }
        for i in range(weeks)
    }
    for a in activities(db, athlete, start):
        wk = a.day - timedelta(days=a.day.weekday())
        r = rows.get(wk)
        if r is None:
            continue
        r["tss"] += a.tss
        if a.sport == "strength":
            r["strength_sessions"] += 1
        elif a.sport in ENDURANCE:
            r[f"{a.sport}_s"] += a.moving_s
            r[f"{a.sport}_m"] += a.distance_m
            if a.sport == "bike":
                r["longest_ride_s"] = max(r["longest_ride_s"], a.moving_s)
            if a.sport == "run":
                r["longest_run_s"] = max(r["longest_run_s"], a.moving_s)
    return [rows[k] for k in sorted(rows)]


def records(db: Session, athlete: Athlete, days: int = 84) -> dict[str, Any]:
    since = _today(db, athlete) - timedelta(days=days)
    out: dict[str, Any] = {}
    for sport in ENDURANCE:
        a = db.scalar(
            select(Activity)
            .where(
                Activity.athlete_id == athlete.id, Activity.sport == sport, Activity.day >= since
            )
            .order_by(Activity.distance_m.desc())
        )
        if a:
            out[sport] = activity_dict(a)
    return out


def activity_dict(a: Activity) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "sport": a.sport,
        "sport_type": a.sport_type,
        "start_time": a.start_time.isoformat(),
        "day": a.day.isoformat(),
        "trainer": a.trainer,
        "moving_s": a.moving_s,
        "distance_m": a.distance_m,
        "elev_gain_m": a.elev_gain_m,
        "avg_speed": a.avg_speed,
        "avg_hr": a.avg_hr,
        "max_hr": a.max_hr,
        "avg_watts": a.avg_watts,
        "np_watts": a.np_watts,
        "tss": a.tss,
        "tss_method": a.tss_method,
        "intensity": a.intensity,
        "ef": a.ef,
        "decoupling_pct": a.decoupling_pct,
        "has_map": bool(a.polyline),
    }


# ---------------------------------------------------------------------- pmc


def _performance_markers(acts: list[Activity], start: date) -> tuple[np.ndarray, np.ndarray]:
    """Aerobic efficiency from steady bike and run sessions, standardised
    within each sport so they can share one performance scale."""
    idx: list[int] = []
    val: list[float] = []
    for sport in ("bike", "run"):
        pts = [
            a
            for a in acts
            if a.sport == sport
            and a.ef
            and a.moving_s >= 2400
            and (a.intensity is None or 0.5 <= a.intensity <= 0.88)
        ]
        if len(pts) < 4:
            continue
        efs = np.array([a.ef for a in pts], dtype=float)
        z = (efs - efs.mean()) / (efs.std() or 1.0)
        for a, zz in zip(pts, z, strict=True):
            idx.append((a.day - start).days)
            val.append(float(zz))
    order = np.argsort(idx)
    return np.array(idx)[order], np.array(val)[order]


def pmc_view(db: Session, athlete: Athlete, days: int = 150) -> dict[str, Any]:
    acts = activities(db, athlete)
    today = _today(db, athlete)
    if not acts:
        return {"series": [], "forecast": None, "model": None}
    start = acts[0].day
    series = pmc.compute_pmc(tss_by_day(acts), start, today)
    load = np.array([d.tss for d in series])

    obs_idx, obs_val = _performance_markers(acts, start)
    fit = banister.fit(load, obs_idx, obs_val)
    model = {
        "personalised": fit.personalised,
        "tau_fitness": fit.tau1,
        "tau_fatigue": fit.tau2,
        "k_ratio": fit.k2 / fit.k1 if fit.k1 else None,
        "r2": fit.r2,
        "observations": fit.n_obs,
        "markers": [
            {"day": (start + timedelta(days=int(i))).isoformat(), "z": float(v)}
            for i, v in zip(obs_idx, obs_val, strict=True)
            if (today - (start + timedelta(days=int(i)))).days <= days
        ],
    }

    forecast = None
    target = target_race(db, athlete)
    if target and target.day > today:
        days_to_race = (target.day - today).days
        best, plans = banister.best_taper(load, fit, days_to_race)
        proj = pmc.project(series[-1], best.daily_tss + [0.0])
        forecast = {
            "race_date": target.day.isoformat(),
            "race_name": target.name,
            "taper_days": best.days,
            "taper_reduction": best.reduction,
            "gain_vs_no_taper": best.gain_vs_no_taper,
            "race_day": {"ctl": proj[-1][0], "atl": proj[-1][1], "tsb": proj[-1][2]},
            "days": [
                {
                    "day": (today + timedelta(days=i + 1)).isoformat(),
                    "tss": t,
                    "ctl": c,
                    "atl": a,
                    "tsb": b,
                }
                for i, (t, (c, a, b)) in enumerate(zip(best.daily_tss + [0.0], proj, strict=True))
            ],
            "grid": [
                {"days": p.days, "reduction": p.reduction, "gain": p.gain_vs_no_taper}
                for p in plans
            ],
        }

    tail = series[-days:]
    return {
        "series": [
            {
                "day": d.day.isoformat(),
                "tss": d.tss,
                "ctl": d.ctl,
                "atl": d.atl,
                "tsb": d.tsb,
                "ramp": d.ramp,
            }
            for d in tail
        ],
        "acwr": pmc.acute_chronic_ratio(series),
        "forecast": forecast,
        "model": model,
    }


# --------------------------------------------------------------------- race


def race_types() -> list[dict[str, str]]:
    return [{"key": r.key, "label": r.label, "kind": r.kind} for r in RACE_TYPES.values()]


def target_race(db: Session, athlete: Athlete) -> Race | None:
    """The race the athlete is building toward: the next A race, else the
    next race of any priority."""
    today = _today(db, athlete)
    upcoming = [r for r in athlete.races if r.day >= today]
    return next((r for r in upcoming if r.priority == "A"), upcoming[0] if upcoming else None)


def race_dict(r: Race) -> dict[str, Any]:
    race = resolve_race(r.race_type, r.distance_m)
    return {
        "id": r.id,
        "name": r.name,
        "day": r.day.isoformat(),
        "race_type": r.race_type,
        "label": race.label,
        "kind": race.kind,
        "distance_m": r.distance_m,
        "priority": r.priority,
        "climb_m": r.climb_m,
        "temp_c": r.temp_c,
        "wetsuit": r.wetsuit,
        "catalog_key": r.catalog_key,
    }


def races_view(db: Session, athlete: Athlete) -> dict[str, Any]:
    target = target_race(db, athlete)
    return {
        "races": [race_dict(r) for r in athlete.races],
        "target_id": target.id if target else None,
        "today": _today(db, athlete).isoformat(),
        "race_types": race_types(),
        "catalog": CATALOG,
    }


def _race_day_form(db: Session, athlete: Athlete, day: date | None) -> tuple[float, float]:
    """Fitness (CTL) and form (TSB) on race day. A past race uses what the
    athlete actually had; a future one assumes the best taper into it; with
    no date, today's fitness arriving fresh."""
    acts = activities(db, athlete)
    today = _today(db, athlete)
    if not acts:
        return 0.0, 15.0
    start = acts[0].day
    series = pmc.compute_pmc(tss_by_day(acts), start, today)
    if day is None:
        return series[-1].ctl, 15.0
    if day <= today:
        row = next((p for p in series if p.day == day), series[0] if day < start else series[-1])
        return row.ctl, row.tsb
    load = np.array([d.tss for d in series])
    fit = banister.fit(load, *_performance_markers(acts, start))
    best, _ = banister.best_taper(load, fit, (day - today).days)
    proj = pmc.project(series[-1], best.daily_tss + [0.0])
    return proj[-1][0], proj[-1][2]


def race_prediction(
    db: Session,
    athlete: Athlete,
    race_id: int | None = None,
    race_type: str | None = None,
    distance_m: float | None = None,
) -> dict[str, Any]:
    """Forecast a saved race (by id), or any distance on a typical course
    (by type). With neither, the target race; with no races at all, a
    marathon."""
    today = _today(db, athlete)
    target = target_race(db, athlete)
    saved: Race | None = None
    if race_id is not None:
        saved = next((r for r in athlete.races if r.id == race_id), None)
        if saved is None:
            raise LookupError("race not found")
    elif race_type is None:
        saved = target

    if saved:
        race = resolve_race(saved.race_type, saved.distance_m)
        course = Course(
            name=saved.name,
            race_type=saved.race_type,
            distance_m=saved.distance_m,
            bike_climb_m=saved.climb_m if saved.climb_m is not None else race.bike_m * 0.006,
            wetsuit=saved.wetsuit,
            run_temp_c=saved.temp_c,
        )
        day: date | None = saved.day
    else:
        race_type = race_type or "marathon"
        race = resolve_race(race_type, distance_m)
        # any other distance runs on a typical course: rolling, mild, wetsuit legal
        course = Course(
            name=race.label,
            race_type=race_type,
            distance_m=distance_m,
            bike_climb_m=race.bike_m * 0.006,
            run_temp_c=18,
        )
        day = target.day if target else None

    thresholds, sources = resolve_thresholds(db, athlete)
    ctl, tsb = _race_day_form(db, athlete, day)
    # long sessions in the 8 weeks before the race (or before today, if it's ahead)
    until = min(day, today) if day else today
    recent = [a for a in activities(db, athlete, until - timedelta(weeks=8)) if a.day <= until]
    longest_run = max((a.distance_m for a in recent if a.sport == "run"), default=0.0)
    longest_ride = max((a.moving_s for a in recent if a.sport == "bike"), default=0.0)

    profile = AthleteProfile(
        ftp_watts=thresholds.ftp_watts,
        run_threshold_speed=thresholds.run_threshold_speed,
        css_speed=thresholds.css_speed,
        weight_kg=athlete.weight_kg,
        ctl=ctl,
        race_day_tsb=tsb,
        longest_run_8wk_m=longest_run,
        longest_ride_8wk_s=longest_ride,
    )
    p = simulate(profile, course, n=6000)

    def leg(s: Any) -> dict[str, float]:
        return {"p10": s.p10, "p50": s.p50, "p90": s.p90}

    garmin = athlete.garmin_profile or {}
    garmin_time = (garmin.get("race_predictions") or {}).get(race.key)
    return {
        "race": race_dict(saved) if saved else None,
        "race_type": race.key,
        "race_day": day.isoformat() if day else None,
        "is_target": saved is not None and target is not None and saved.id == target.id,
        "garmin_prediction": garmin_time
        and {"time_s": garmin_time, "as_of": garmin.get("race_predictions_as_of")},
        "course": {
            "name": course.name,
            "label": race.label,
            "kind": race.kind,
            "swim_m": race.swim_m,
            "bike_m": race.bike_m,
            "run_m": race.run_m,
            "bike_climb_m": course.bike_climb_m,
            "wetsuit": course.wetsuit,
            "run_temp_c": course.run_temp_c,
        },
        "inputs": {
            "ftp_watts": thresholds.ftp_watts,
            "run_threshold_speed": thresholds.run_threshold_speed,
            "css_speed": thresholds.css_speed,
            "race_day_ctl": ctl,
            "race_day_tsb": tsb,
            "longest_run_8wk_m": longest_run,
            "longest_ride_8wk_s": longest_ride,
            "sources": sources,
        },
        "legs": {"total": leg(p.total), **{k: leg(v) for k, v in p.legs.items()}},
        "bike_avg_watts": p.bike_avg_watts,
        "bike_avg_speed": p.bike_avg_speed,
        "run_pace_s_per_km": p.run_pace_s_per_km,
        "histogram": [{"s": t, "count": c} for t, c in p.histogram],
        "drivers": p.drivers,
    }


# ---------------------------------------------------------------- analysis


def power_curve(db: Session, athlete: Athlete, days: int = 90) -> dict[str, Any]:
    today = _today(db, athlete)
    acts = [a for a in activities(db, athlete) if a.power_curve]
    recent = merge_curves(
        {int(k): v for k, v in a.power_curve.items()}
        for a in acts
        if a.day >= today - timedelta(days=days)
    )
    all_time = merge_curves({int(k): v for k, v in a.power_curve.items()} for a in acts)
    fit = fit_critical_power(recent)
    return {
        "recent": [{"s": k, "w": v} for k, v in recent.items()],
        "all_time": [{"s": k, "w": v} for k, v in all_time.items()],
        "cp": fit.__dict__ if fit else None,
        "weight_kg": athlete.weight_kg,
    }


def efficiency_trend(db: Session, athlete: Athlete, days: int = 120) -> dict[str, Any]:
    today = _today(db, athlete)
    acts = [
        a
        for a in activities(db, athlete, today - timedelta(days=days))
        if a.ef and a.sport in ("bike", "run") and a.moving_s >= 1800
    ]
    out: dict[str, Any] = {"points": [], "trend": {}}
    for a in acts:
        # the whole workout rides along so hovering a point can show it
        out["points"].append(
            {**activity_dict(a), "decoupling": a.decoupling_pct, "polyline": a.polyline}
        )
    for sport in ("bike", "run"):
        pts = [(a.day, a.ef) for a in acts if a.sport == sport]
        if len(pts) >= 5:
            x = np.array([(d - today).days for d, _ in pts], dtype=float)
            y = np.array([v for _, v in pts], dtype=float)
            slope, intercept = np.polyfit(x, y, 1)
            out["trend"][sport] = {
                "pct_per_4wk": float(slope * 28 / y.mean() * 100),
                "start": float(intercept + slope * x.min()),
                "end": float(intercept),
            }
    return out


def calendar(db: Session, athlete: Athlete, days: int = 365) -> list[dict[str, Any]]:
    today = _today(db, athlete)
    by_day = tss_by_day(activities(db, athlete, today - timedelta(days=days)))
    return [
        {
            "day": (today - timedelta(days=i)).isoformat(),
            "tss": round(by_day.get(today - timedelta(days=i), 0.0), 1),
        }
        for i in range(days - 1, -1, -1)
    ]


def routes(db: Session, athlete: Athlete, days: int = 180) -> list[dict[str, Any]]:
    since = _today(db, athlete) - timedelta(days=days)
    rows = db.scalars(
        select(Activity).where(
            Activity.athlete_id == athlete.id, Activity.day >= since, Activity.polyline.is_not(None)
        )
    ).all()
    return [
        {
            "id": a.id,
            "sport": a.sport,
            "name": a.name,
            "day": a.day.isoformat(),
            "distance_m": a.distance_m,
            "polyline": a.polyline,
        }
        for a in rows
    ]


# ----------------------------------------------------------- training status


def _hrv_band(hrv: dict[date, float], d: date) -> tuple[float, float] | None:
    """Mean and SD of the 60 nights before `d`: the athlete's normal range."""
    window = [v for day, v in hrv.items() if d - timedelta(days=60) <= day < d]
    if len(window) < 14:
        return None
    return float(np.mean(window)), float(np.std(window))


def training_status(db: Session, athlete: Athlete, weeks: int = 12) -> dict[str, Any]:
    """Garmin's own training status when the athlete's export includes it,
    otherwise an estimate from fitness trend, load ratio and HRV."""
    today = _today(db, athlete)
    since = today - timedelta(weeks=weeks)
    rows = db.scalars(
        select(WellnessDay)
        .where(
            WellnessDay.athlete_id == athlete.id,
            WellnessDay.day >= since - timedelta(days=70),
            WellnessDay.day <= today,
        )
        .order_by(WellnessDay.day)
    ).all()
    by_day = {r.day: r for r in rows}
    hrv = {r.day: r.hrv_ms for r in rows if r.hrv_ms}
    days = [since + timedelta(days=i) for i in range((today - since).days + 1)]

    hrv_view = None
    week = [v for d, v in hrv.items() if d > today - timedelta(days=7)]
    band = _hrv_band(hrv, today - timedelta(days=6))
    if week and band:
        avg, (base, sd) = float(np.mean(week)), band
        hrv_view = {
            "weekly_avg": avg,
            "baseline": base,
            "low": base - sd,
            "high": base + sd,
            "status": "BALANCED"
            if abs(avg - base) <= sd
            else "LOW"
            if avg < base - 2 * sd
            else "UNBALANCED",
        }

    garmin = [r for r in rows if r.training_status and r.day > today - timedelta(days=14)]
    if garmin:
        last = garmin[-1]
        vo2 = [r for r in rows if r.vo2max]
        vo2_view = None
        if vo2:
            before = [r.vo2max for r in vo2 if r.day <= vo2[-1].day - timedelta(days=28)]
            vo2_view = {
                "value": vo2[-1].vo2max,
                "change_28d": vo2[-1].vo2max - before[-1] if before else None,
            }
        loads = [r for r in rows if r.acute_load is not None]
        load = loads[-1] if loads else None
        return {
            "source": "garmin",
            "as_of": last.day.isoformat(),
            "status": last.training_status,
            "fitness_trend": last.fitness_trend,
            "vo2max": vo2_view,
            "load": load
            and {
                "acute": load.acute_load,
                "chronic": load.chronic_load,
                "ratio": load.acute_load / load.chronic_load if load.chronic_load else None,
                "status": load.load_status,
                "units": "garmin",
            },
            "hrv": hrv_view,
            "readiness": next((r.readiness for r in reversed(rows) if r.readiness), None),
            "timeline": [
                {"day": d.isoformat(), "status": by_day[d].training_status if d in by_day else None}
                for d in days
            ],
        }

    acts = activities(db, athlete)
    if not acts:
        return {"source": "estimated", "status": "NO_STATUS", "timeline": []}
    start = acts[0].day
    series = {p.day: p for p in pmc.compute_pmc(tss_by_day(acts), start, today)}

    def classify(d: date) -> str | None:
        p, back = series.get(d), series.get(d - timedelta(days=28))
        if p is None:
            return None
        nights = [(n, hrv[n]) for n in hrv if d - timedelta(days=7) < n <= d]
        lows = sum(1 for n, v in nights if (b := _hrv_band(hrv, n)) and v < b[0] - b[1])
        acwr = p.atl / p.ctl if p.ctl > 0 else None
        return status.classify(p.ctl - (back.ctl if back else 0), p.ctl, p.tsb, acwr, lows)

    now = series[today]
    back = series.get(today - timedelta(days=28))
    change = now.ctl - (back.ctl if back else 0)
    ratio = now.atl / now.ctl if now.ctl > 0 else None
    return {
        "source": "estimated",
        "as_of": today.isoformat(),
        "status": classify(today),
        "fitness_trend": "INCREASING"
        if change >= 0.05 * now.ctl
        else "DECREASING"
        if change <= -0.05 * now.ctl
        else "STABLE",
        "fitness": {"ctl": now.ctl, "change_28d": change},
        "vo2max": None,
        "load": {
            "acute": now.atl,
            "chronic": now.ctl,
            "ratio": ratio,
            "status": None
            if ratio is None
            else "HIGH"
            if ratio > 1.3
            else "LOW"
            if ratio < 0.8
            else "OPTIMAL",
            "units": "tss",
        },
        "hrv": hrv_view,
        "readiness": None,
        "timeline": [{"day": d.isoformat(), "status": classify(d)} for d in days],
    }


# ------------------------------------------------------------------ wellness


def wellness(db: Session, athlete: Athlete, days: int = 90) -> dict[str, Any]:
    today = _today(db, athlete)
    since = today - timedelta(days=days)
    rows = db.scalars(
        select(WellnessDay)
        .where(WellnessDay.athlete_id == athlete.id, WellnessDay.day >= since - timedelta(days=60))
        .order_by(WellnessDay.day)
    ).all()
    if not rows:
        return {"days": [], "insights": None}

    hrv = {r.day: r.hrv_ms for r in rows if r.hrv_ms}
    out_days = []
    for r in rows:
        if r.day < since:
            continue
        window = [v for d, v in hrv.items() if r.day - timedelta(days=60) <= d < r.day]
        base = float(np.mean(window)) if len(window) >= 14 else None
        sd = float(np.std(window)) if len(window) >= 14 else None
        status = None
        if base and sd and r.hrv_ms:
            status = (
                "low" if r.hrv_ms < base - sd else "high" if r.hrv_ms > base + sd else "balanced"
            )
        out_days.append(
            {
                "day": r.day.isoformat(),
                "sleep_h": r.sleep_s / 3600 if r.sleep_s else None,
                "sleep_score": r.sleep_score,
                "hrv_ms": r.hrv_ms,
                "hrv_baseline": base,
                "hrv_sd": sd,
                "hrv_status": status,
                "rest_hr": r.rest_hr,
                "body_battery_high": r.body_battery_high,
                "stress_avg": r.stress_avg,
            }
        )

    # does a hard day show up in the next morning's HRV and resting HR?
    load = tss_by_day(activities(db, athlete, since - timedelta(days=2)))
    pairs_hrv = [(load.get(d - timedelta(days=1), 0.0), v) for d, v in hrv.items() if d >= since]
    rhr = {r.day: r.rest_hr for r in rows if r.rest_hr and r.day >= since}
    pairs_rhr = [(load.get(d - timedelta(days=1), 0.0), v) for d, v in rhr.items()]

    def corr(pairs: list[tuple[float, float]]) -> float | None:
        if len(pairs) < 10:
            return None
        x, y = np.array(pairs).T
        if x.std() == 0 or y.std() == 0:
            return None
        return float(np.corrcoef(x, y)[0, 1])

    return {
        "days": out_days,
        "insights": {
            "hrv_vs_prior_day_tss": corr(pairs_hrv),
            "rhr_vs_prior_day_tss": corr(pairs_rhr),
            "nights": len(out_days),
        },
    }
