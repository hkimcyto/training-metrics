"""Generate a realistic demo athlete so the public site works without a
Strava account.

The data is synthetic but built to behave like a real build to an Ironman:
3-week build / 1-week recovery blocks, a weekly pattern of swim, bike, run and
strength, long rides and runs that grow toward race day, routes around San
Francisco and Marin, and wellness data that responds to training load.

Aerobic efficiency is generated from a hidden Banister model, so the fitting
code has a real signal to recover, the same way it would from a real athlete.

    python -m app.demo               # load the real snapshot (or synthetic if absent)
    python -m app.demo --synthetic   # always use the synthetic athlete
    python -m app.demo --if-missing  # only if there isn't one yet
"""

from __future__ import annotations

import gzip
import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics.banister import predict
from app.analytics.load import normalized_power
from app.analytics.polyline import encode
from app.analytics.power_curve import best_efforts
from app.db.models import Activity, Athlete, Base, WellnessDay
from app.db.session import SessionLocal, engine
from app.ingest.scoring import sport_of
from app.ingest.sync import rescore_all

END = date(2026, 10, 4)  # a Sunday, three weeks out from the demo race
WEEKS = 26
RACE = END + timedelta(days=20)

# Waypoints for real routes; the generator adds GPS-like wiggle between them.
ROUTES = {
    "Golden Gate Park loop": (
        "run",
        [
            (37.7694, -122.4580),
            (37.7710, -122.4740),
            (37.7697, -122.4950),
            (37.7660, -122.5090),
            (37.7638, -122.4900),
            (37.7655, -122.4700),
            (37.7694, -122.4580),
        ],
    ),
    "Marina to the Bridge": (
        "run",
        [
            (37.8060, -122.4235),
            (37.8065, -122.4320),
            (37.8040, -122.4440),
            (37.8035, -122.4640),
            (37.8075, -122.4750),
            (37.8035, -122.4640),
            (37.8040, -122.4440),
            (37.8060, -122.4235),
        ],
    ),
    "Embarcadero out-and-back": (
        "run",
        [
            (37.7840, -122.3880),
            (37.7955, -122.3937),
            (37.8060, -122.4100),
            (37.8080, -122.4180),
            (37.8060, -122.4100),
            (37.7955, -122.3937),
            (37.7840, -122.3880),
        ],
    ),
    "Lake Merced loop": (
        "run",
        [
            (37.7310, -122.4880),
            (37.7235, -122.4985),
            (37.7120, -122.4955),
            (37.7095, -122.4840),
            (37.7200, -122.4800),
            (37.7310, -122.4880),
        ],
    ),
    "Hawk Hill": (
        "bike",
        [
            (37.7980, -122.4560),
            (37.8078, -122.4750),
            (37.8320, -122.4790),
            (37.8330, -122.4990),
            (37.8255, -122.4990),
            (37.8320, -122.4790),
            (37.8078, -122.4750),
            (37.7980, -122.4560),
        ],
    ),
    "Paradise Loop": (
        "bike",
        [
            (37.7980, -122.4560),
            (37.8078, -122.4750),
            (37.8590, -122.4850),
            (37.8890, -122.5150),
            (37.9050, -122.4900),
            (37.8735, -122.4566),
            (37.8900, -122.5300),
            (37.8590, -122.4850),
            (37.8078, -122.4750),
            (37.7980, -122.4560),
        ],
    ),
    "Point Reyes": (
        "bike",
        [
            (37.7980, -122.4560),
            (37.8078, -122.4750),
            (37.8590, -122.4850),
            (37.9250, -122.5200),
            (37.9871, -122.5889),
            (38.0090, -122.6560),
            (38.0420, -122.7550),
            (38.0688, -122.8069),
            (38.0420, -122.7550),
            (37.9871, -122.5889),
            (37.9250, -122.5200),
            (37.8590, -122.4850),
            (37.8078, -122.4750),
            (37.7980, -122.4560),
        ],
    ),
    "Half Moon Bay": (
        "bike",
        [
            (37.7600, -122.5100),
            (37.7050, -122.4980),
            (37.6600, -122.4950),
            (37.6138, -122.4869),
            (37.5500, -122.5100),
            (37.5000, -122.4700),
            (37.4636, -122.4286),
            (37.5000, -122.4700),
            (37.5500, -122.5100),
            (37.6138, -122.4869),
            (37.7050, -122.4980),
            (37.7600, -122.5100),
        ],
    ),
}


def _route(name: str, rng: np.random.Generator) -> str:
    pts = ROUTES[name][1]
    out: list[tuple[float, float]] = []
    for (a, b), (c, d) in zip(pts[:-1], pts[1:], strict=True):
        n = max(8, int(math.hypot(c - a, d - b) / 0.0012))
        for i in range(n):
            t = i / n
            out.append(
                (a + (c - a) * t + rng.normal(0, 0.00012), b + (d - b) * t + rng.normal(0, 0.00012))
            )
    out.append(pts[-1])
    return encode(out)


def _ride_stream(
    seconds: int, target_w: float, rng: np.random.Generator, intervals: bool
) -> np.ndarray:
    base = np.full(seconds, target_w) + rng.normal(0, 18, seconds)
    if intervals:  # 2x20 min just under threshold, the classic FTP builder
        for start in range(900, seconds - 1500, 1800):
            n = min(1200, seconds - start)
            base[start : start + n] = target_w * 1.42 + rng.normal(0, 8, n)
    # surges: short sprints, punchy 1-minute climbs and the odd 5-minute effort,
    # so the power-duration curve has a realistic shape at the short end
    for _ in range(int(rng.integers(2, 6))):
        n = int(rng.choice([8, 12, 20]))
        s = int(rng.integers(0, seconds - n))
        base[s : s + n] = rng.uniform(560, 820)
    for _ in range(int(rng.integers(1, 4))):
        s = int(rng.integers(0, seconds - 60))
        base[s : s + 60] = target_w * rng.uniform(1.75, 2.0)
    if rng.random() < 0.35 and seconds > 1200:
        s = int(rng.integers(0, seconds - 300))
        base[s : s + 300] = target_w * rng.uniform(1.48, 1.62)
    coast = rng.random(seconds) < 0.04
    base[coast] = 0
    return np.clip(base, 0, None)


def build(db: Session) -> Athlete:
    Base.metadata.create_all(engine)
    _drop_existing(db)

    rng = np.random.default_rng(2026)
    athlete = Athlete(
        name="Demo Athlete",
        is_demo=True,
        weight_kg=74,
        max_hr=190,
        rest_hr=47,
        lthr=168,
        ftp_watts=236,
        run_threshold_speed=4.25,
        css_speed=1.02,
        race_name="Fall IRONMAN (demo)",
        race_date=RACE,
        race_type="ironman",
        race_climb_m=1200,
        race_wetsuit=True,
        race_temp_c=24,
    )
    db.add(athlete)
    db.flush()

    start = END - timedelta(weeks=WEEKS) + timedelta(days=1)
    days = (END - start).days + 1
    plan: list[list[tuple[str, float, str]]] = [[] for _ in range(days)]  # (sport, hours, flavour)

    for w in range(WEEKS):
        block = w % 4
        recovery = block == 3
        growth = 0.75 + 0.6 * w / (WEEKS - 1)
        vol = growth * (0.65 if recovery else 1 + 0.07 * block)
        long_ride = min(5.8, 2.2 + 3.9 * w / (WEEKS - 2)) * (0.6 if recovery else 1)
        long_run = min(2.6, 1.1 + 1.6 * w / (WEEKS - 2)) * (0.65 if recovery else 1)
        week = [
            [("swim", 0.8 * vol, "css"), ("strength", 0.75, "")],  # Mon
            [("bike", 1.1 * vol, "intervals"), ("run", 0.6 * vol, "easy")],  # Tue
            [("swim", 1.0 * vol, "endurance"), ("run", 0.9 * vol, "tempo")],  # Wed
            [("bike", 1.4 * vol, "indoor"), ("strength", 0.7, "")],  # Thu
            [("swim", 0.9 * vol, "endurance"), ("run", 0.7 * vol, "easy")],  # Fri
            [("bike", long_ride, "long"), ("run", 0.35 * vol, "brick")],  # Sat
            [("run", long_run, "long")],  # Sun
        ]
        for d in range(7):
            i = w * 7 + d
            if i < days:
                plan[i] = [s for s in week[d] if rng.random() > 0.05]  # the odd missed session

    # hidden "true" response to load drives aerobic efficiency
    approx = np.array(
        [
            sum({"swim": 55, "bike": 62, "run": 70, "strength": 30}[s] * h for s, h, _ in p)
            for p in plan
        ]
    )
    truth = predict(approx, 0.0, np.array([0.0012, 0.0032, 36.0, 9.0]))
    truth = (truth - truth.mean()) / truth.std()

    ftp, thr_speed, css = 236.0, 4.25, 1.02
    ride_routes = ["Hawk Hill", "Paradise Loop", "Half Moon Bay"]
    run_routes = [
        "Golden Gate Park loop",
        "Marina to the Bridge",
        "Embarcadero out-and-back",
        "Lake Merced loop",
    ]

    for i, sessions in enumerate(plan):
        day = start + timedelta(days=i)
        fit_boost = 1 + 0.035 * truth[i]
        for k, (sport, hours, flavour) in enumerate(sessions):
            secs = int(hours * 3600 * rng.uniform(0.92, 1.08))
            st = datetime.combine(day, time(6 + k * 10, int(rng.integers(0, 59))))
            act = Activity(
                athlete_id=athlete.id,
                source="demo",
                external_id=f"demo-{i}-{k}",
                start_time=st,
                day=day,
                moving_s=secs,
                elapsed_s=secs * rng.uniform(1.02, 1.15),
                sport=sport,
            )
            if sport == "bike":
                indoor = flavour in ("indoor", "intervals") or (
                    flavour != "long" and rng.random() < 0.3
                )
                frac = {"intervals": 0.68, "indoor": 0.70, "long": 0.66}.get(flavour, 0.64)
                stream = _ride_stream(
                    secs, ftp * frac * rng.uniform(0.96, 1.04), rng, flavour == "intervals"
                )
                np_w = normalized_power(stream)
                hr = (
                    athlete.rest_hr
                    + (athlete.lthr - athlete.rest_hr) * (np_w / ftp) ** 1.1 / fit_boost
                )
                hr += rng.normal(0, 2)
                speed = (6.9 if indoor else 7.6) * (np_w / 160) ** 0.33
                route = (
                    None
                    if indoor
                    else (
                        "Point Reyes"
                        if flavour == "long" and hours > 4
                        else rng.choice(ride_routes)
                    )
                )
                act.sport_type = "VirtualRide" if indoor else "Ride"
                act.name = {
                    "intervals": "Zwift - 2x15 FTP Intervals",
                    "indoor": "Zwift - Endurance",
                }.get(flavour) or (route or "Ride")
                act.trainer = indoor
                act.device_watts = True
                act.avg_watts = float(stream.mean())
                act.np_watts = np_w
                act.power_curve = {str(kk): v for kk, v in best_efforts(stream).items()}
                act.avg_hr = float(hr)
                act.max_hr = float(min(athlete.max_hr, hr + rng.uniform(15, 28)))
                act.distance_m = speed * secs
                act.avg_speed = speed
                act.elev_gain_m = 0 if indoor else act.distance_m / 1000 * rng.uniform(6, 14)
                act.ef = np_w / hr
                drift = max(0.0, (hours - 2) * 1.6 - 1.2 * truth[i]) + rng.normal(0, 0.8)
                act.decoupling_pct = float(drift) if hours >= 1.5 else None
                act.polyline = _route(route, rng) if route else None
                act.has_streams = True
            elif sport == "run":
                frac = {"tempo": 0.86, "long": 0.74, "brick": 0.78}.get(flavour, 0.72)
                speed = thr_speed * frac * rng.uniform(0.97, 1.03) * (1 + 0.015 * truth[i])
                hr = (
                    athlete.rest_hr
                    + (athlete.lthr - athlete.rest_hr) * (frac**1.6) / fit_boost
                    + rng.normal(0, 2)
                )
                route = rng.choice(run_routes)
                treadmill = flavour == "easy" and rng.random() < 0.35
                act.sport_type = "Run"
                act.name = (
                    "Treadmill run" if treadmill else ("Long run" if flavour == "long" else route)
                )
                act.trainer = treadmill
                act.distance_m = speed * secs
                act.avg_speed = speed
                act.graded_speed = speed * 1.01
                act.avg_hr = float(hr)
                act.max_hr = float(min(athlete.max_hr, hr + rng.uniform(10, 22)))
                act.elev_gain_m = 0 if treadmill else act.distance_m / 1000 * rng.uniform(4, 12)
                act.ef = speed * 60 / hr
                act.decoupling_pct = (
                    float(max(0.0, (hours - 1) * 2.2 - truth[i]) + rng.normal(0, 0.7))
                    if hours >= 1
                    else None
                )
                act.polyline = None if treadmill else _route(route, rng)
                act.has_streams = True
            elif sport == "swim":
                speed = (
                    css
                    * {"css": 0.88, "endurance": 0.84}.get(flavour, 0.85)
                    * rng.uniform(0.97, 1.03)
                )
                act.sport_type = "Swim"
                act.name = "CSS set" if flavour == "css" else "Endurance swim"
                act.distance_m = round(speed * secs / 22.86) * 22.86  # whole 25-yd lengths
                act.avg_speed = speed
                act.avg_hr = float(118 + rng.normal(0, 5))
            else:
                act.sport_type = "WeightTraining"
                act.name = rng.choice(["Legs + core", "Push + core", "Pull + mobility"])
                act.avg_hr = float(102 + rng.normal(0, 6))
            db.add(act)

    # wellness that responds to yesterday's load
    for i in range(days):
        day = start + timedelta(days=i)
        y = approx[i - 1] if i else 80
        db.add(
            WellnessDay(
                athlete_id=athlete.id,
                day=day,
                source="demo",
                hrv_ms=float(
                    np.clip(64 + 3 * truth[i] - 0.055 * (y - 85) + rng.normal(0, 4), 35, 95)
                ),
                rest_hr=float(
                    np.clip(47 - 0.8 * truth[i] + 0.018 * (y - 85) + rng.normal(0, 1.4), 40, 60)
                ),
                sleep_s=float(np.clip(rng.normal(7.4, 0.55) + 0.003 * (y - 85), 5.2, 9.3) * 3600),
                sleep_score=float(np.clip(rng.normal(80, 7) - 0.04 * (y - 85), 45, 98)),
                body_battery_high=float(np.clip(rng.normal(82, 8) - 0.06 * (y - 85), 35, 100)),
                body_battery_low=float(np.clip(rng.normal(18, 6), 5, 40)),
                stress_avg=float(np.clip(rng.normal(27, 5) + 0.03 * (y - 85), 10, 60)),
            )
        )
    db.commit()
    rescore_all(db, athlete)
    db.commit()
    return athlete


SNAPSHOT = Path(__file__).parent / "fixtures" / "athlete.json.gz"


def build_from_snapshot(db: Session, path: Path = SNAPSHOT) -> Athlete:
    """Load a real athlete's exported Strava history as the public demo.

    The snapshot is produced by tools/build_snapshot.py, which trims the ends
    of every route so start and finish locations aren't published."""
    Base.metadata.create_all(engine)
    _drop_existing(db)
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    meta = data["athlete"]
    athlete = Athlete(
        name=meta["name"],
        is_demo=True,
        weight_kg=meta.get("weight_kg", 77),
        max_hr=meta.get("max_hr", 192),
        ftp_watts=meta.get("ftp_watts"),
        race_name=meta.get("race_name", "IRONMAN California"),
        race_date=date.fromisoformat(meta.get("race_date", "2026-10-18")),
        race_type=meta.get("race_type", "ironman"),
        race_climb_m=meta.get("race_climb_m", 500),
        race_wetsuit=meta.get("race_wetsuit", True),
        race_temp_c=meta.get("race_temp_c", 25),
    )
    db.add(athlete)
    db.flush()
    for r in data["activities"]:
        start = datetime.fromisoformat(r["start_local"])
        sport = sport_of(r["sport_type"]).value
        db.add(
            Activity(
                athlete_id=athlete.id,
                source="strava",
                external_id=r["id"],
                name=r["name"][:255],
                sport=sport,
                sport_type=r["sport_type"],
                start_time=start,
                day=start.date(),
                trainer=r["trainer"],
                moving_s=r["moving_s"],
                elapsed_s=r["elapsed_s"],
                distance_m=r["distance_m"],
                elev_gain_m=r["elev_gain_m"],
                avg_speed=r.get("avg_speed"),
                avg_hr=r.get("avg_hr"),
                avg_watts=r.get("avg_watts"),
                np_watts=r.get("avg_watts"),
                device_watts=r.get("device_watts", False),
                power_curve=r.get("power_curve") or None,
                relative_effort=r.get("relative_effort"),
                ef=r.get("ef"),
                decoupling_pct=r.get("decoupling_pct"),
                polyline=r.get("polyline"),
            )
        )
    db.commit()
    rescore_all(db, athlete)
    db.commit()
    return athlete


def _drop_existing(db: Session) -> None:
    old = db.scalar(select(Athlete).where(Athlete.is_demo.is_(True)))
    if old:
        db.execute(delete(WellnessDay).where(WellnessDay.athlete_id == old.id))
        db.execute(delete(Activity).where(Activity.athlete_id == old.id))
        db.delete(old)
        db.commit()


if __name__ == "__main__":
    import sys

    with SessionLocal() as s:
        if "--if-missing" in sys.argv:
            Base.metadata.create_all(engine)
            if s.scalar(select(Athlete.id).where(Athlete.is_demo.is_(True))):
                print("demo athlete already present")
                sys.exit(0)
        synthetic = "--synthetic" in sys.argv or not SNAPSHOT.exists()
        a = build(s) if synthetic else build_from_snapshot(s)
        n = s.scalar(
            select(Activity.id).where(Activity.athlete_id == a.id).order_by(Activity.id.desc())
        )
        print(f"demo athlete {a.id} created with activities up to id {n}")
