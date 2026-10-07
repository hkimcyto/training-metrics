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

from app.analytics import banister, pmc
from app.analytics.power_curve import fit_critical_power, merge_curves
from app.analytics.race import AthleteProfile, Course, simulate
from app.db.models import Activity, Athlete, WellnessDay
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
    if athlete.race_date and athlete.race_date > today:
        days_to_race = (athlete.race_date - today).days
        best, plans = banister.best_taper(load, fit, days_to_race)
        proj = pmc.project(series[-1], best.daily_tss + [0.0])
        forecast = {
            "race_date": athlete.race_date.isoformat(),
            "race_name": athlete.race_name,
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


def race_prediction(db: Session, athlete: Athlete) -> dict[str, Any]:
    today = _today(db, athlete)
    thresholds, sources = resolve_thresholds(db, athlete)
    view = pmc_view(db, athlete, days=1)
    last = view["series"][-1] if view["series"] else {"ctl": 0, "tsb": 0}
    fc = view["forecast"]
    ctl = fc["race_day"]["ctl"] if fc else last["ctl"]
    tsb = fc["race_day"]["tsb"] if fc else 15.0

    since = today - timedelta(weeks=8)
    recent = activities(db, athlete, since)
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
    course = Course(
        name=athlete.race_name or "IRONMAN",
        bike_climb_m=athlete.race_climb_m,
        wetsuit=athlete.race_wetsuit,
        run_temp_c=athlete.race_temp_c,
    )
    p = simulate(profile, course, n=6000)

    def leg(s: Any) -> dict[str, float]:
        return {"p10": s.p10, "p50": s.p50, "p90": s.p90}

    return {
        "course": course.__dict__,
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
        "legs": {k: leg(getattr(p, k)) for k in ("total", "swim", "t1", "bike", "t2", "run")},
        "bike_avg_watts": p.bike_avg_watts,
        "bike_avg_speed": p.bike_avg_speed,
        "run_pace_s_per_km": p.run_pace_s_per_km,
        "histogram": [{"hours": h, "count": c} for h, c in p.histogram],
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
        out["points"].append(
            {
                "day": a.day.isoformat(),
                "sport": a.sport,
                "ef": a.ef,
                "decoupling": a.decoupling_pct,
                "name": a.name,
            }
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
