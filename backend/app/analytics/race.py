"""Ironman finish-time prediction by Monte Carlo simulation.

Each simulated race draws the things nobody knows in advance (race-day
pacing, aerodynamic drag, how much the run fades, transition times) from
realistic ranges, then works out each leg:

* swim:  race pace as a fraction of Critical Swim Speed, plus extra distance
         from sighting and a wetsuit bonus when legal
* bike:  a physics model. Solve for the time where the energy the rider puts
         out at their chosen intensity equals the energy that air drag,
         rolling resistance and climbing take
* run:   threshold pace scaled by a durability factor that depends on how
         much long running the athlete has done, plus heat

Ten thousand races give a distribution instead of a single guess, so the
answer comes with a realistic range.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

G = 9.81


@dataclass(frozen=True)
class Course:
    name: str = "IRONMAN"
    swim_m: float = 3800
    bike_m: float = 180_200
    run_m: float = 42_195
    bike_climb_m: float = 1500
    wetsuit: bool = True
    run_temp_c: float = 22.0
    air_density: float = 1.2


@dataclass(frozen=True)
class AthleteProfile:
    ftp_watts: float
    run_threshold_speed: float  # m/s
    css_speed: float  # m/s
    weight_kg: float
    ctl: float
    race_day_tsb: float
    longest_run_8wk_m: float
    longest_ride_8wk_s: float


@dataclass
class LegStats:
    p10: float
    p50: float
    p90: float


@dataclass
class RacePrediction:
    total: LegStats
    swim: LegStats
    t1: LegStats
    bike: LegStats
    t2: LegStats
    run: LegStats
    bike_avg_watts: float
    bike_avg_speed: float
    run_pace_s_per_km: float
    histogram: list[tuple[float, int]] = field(default_factory=list)
    drivers: dict[str, float] = field(default_factory=dict)


def bike_time(
    power_w: float,
    distance_m: float,
    climb_m: float,
    mass_kg: float,
    cda: float,
    crr: float,
    rho: float,
    drivetrain: float = 0.975,
    descent_recovery: float = 0.25,
) -> float:
    """Time in seconds where delivered energy balances the losses.

    The rider supplies P*eta*T. Aero and rolling losses at average speed v=D/T
    take (0.5 rho CdA v^3 + Crr m g v) T, and climbing takes m g H, of which a
    share comes back on the descents."""

    def balance(t: float) -> float:
        v = distance_m / t
        resist = 0.5 * rho * cda * v**3 + crr * mass_kg * G * v
        climb = mass_kg * G * climb_m * (1 - descent_recovery)
        return power_w * drivetrain * t - resist * t - climb

    return float(brentq(balance, 1800, 60 * 3600))


def durability(longest_run_m: float, ctl: float) -> float:
    """Fraction of threshold speed sustainable for an Ironman marathon.

    Well-prepared age groupers run around 80-85% of threshold off the bike.
    Missing long runs and low fitness both pull that down."""
    long_run = np.clip((longest_run_m - 16_000) / (32_000 - 16_000), 0, 1)
    fitness = np.clip((ctl - 50) / (110 - 50), 0, 1)
    return 0.70 + 0.09 * long_run + 0.06 * fitness


def form_multiplier(tsb: float) -> float:
    """Arriving fresh helps, arriving tired hurts. Peaks around +15 form."""
    return 1 + 0.0025 * (15 - abs(np.clip(tsb, -40, 40) - 15))


def simulate(
    athlete: AthleteProfile,
    course: Course | None = None,
    n: int = 10_000,
    seed: int | None = 7,
) -> RacePrediction:
    course = course or Course()
    rng = np.random.default_rng(seed)
    # one "how's the day going" draw shared by all three legs: sleep, stomach, wind
    day = rng.normal(1.0, 0.03, n).clip(0.88, 1.08)
    form = form_multiplier(athlete.race_day_tsb) * day

    # swim
    swim_frac = rng.uniform(0.86, 0.94, n)
    sighting = rng.uniform(1.02, 1.08, n)
    wetsuit = 1.04 if course.wetsuit else 1.0
    swim_speed = athlete.css_speed * swim_frac * wetsuit * form
    swim = course.swim_m * sighting / swim_speed

    t1 = rng.uniform(240, 480, n)
    t2 = rng.uniform(150, 300, n)

    # bike: intensity is lower for athletes without long rides in the legs
    ride_hours = athlete.longest_ride_8wk_s / 3600
    target_if = 0.66 + 0.02 * np.clip(ride_hours - 4, 0, 2.5)
    intensity = np.clip(rng.normal(target_if, 0.025, n), 0.58, 0.80)
    power = athlete.ftp_watts * intensity * form
    cda = rng.normal(0.29, 0.02, n).clip(0.22, 0.38)
    crr = rng.normal(0.0042, 0.0004, n).clip(0.003, 0.006)
    mass = athlete.weight_kg + 10.5
    bike = np.array(
        [
            bike_time(p, course.bike_m, course.bike_climb_m, mass, c, r, course.air_density)
            for p, c, r in zip(power, cda, crr, strict=True)
        ]
    )

    # run
    base = durability(athlete.longest_run_8wk_m, athlete.ctl)
    fade = rng.normal(0.0, 0.035, n)
    heat = 1 - 0.01 * max(course.run_temp_c - 18, 0)
    run_speed = athlete.run_threshold_speed * np.clip(base + fade, 0.55, 0.92) * heat * form
    run = course.run_m / run_speed

    total = swim + t1 + bike + t2 + run

    def stats(x: np.ndarray) -> LegStats:
        p10, p50, p90 = np.percentile(x, [10, 50, 90])
        return LegStats(float(p10), float(p50), float(p90))

    counts, edges = np.histogram(total / 3600, bins=30)
    return RacePrediction(
        total=stats(total),
        swim=stats(swim),
        t1=stats(t1),
        bike=stats(bike),
        t2=stats(t2),
        run=stats(run),
        bike_avg_watts=float(np.median(power)),
        bike_avg_speed=float(course.bike_m / np.median(bike)),
        run_pace_s_per_km=float(np.median(run) / (course.run_m / 1000)),
        histogram=[
            (float((a + b) / 2), int(c))
            for a, b, c in zip(edges[:-1], edges[1:], counts, strict=True)
        ],
        drivers={
            "bike_intensity_factor": float(np.median(intensity)),
            "run_durability": float(base),
            "form_multiplier": float(form_multiplier(athlete.race_day_tsb)),
        },
    )
