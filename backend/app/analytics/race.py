"""Finish-time prediction by Monte Carlo simulation, for running races from
the mile to the marathon and triathlons from sprint to full distance.

Each simulated race draws the things nobody knows in advance (race-day
pacing, aerodynamic drag, how much the run fades, transition times) from
realistic ranges, then works out each leg:

* swim:  race pace as a fraction of Critical Swim Speed, plus extra distance
         from sighting and a wetsuit bonus when legal
* bike:  a physics model. Solve for the time where the energy the rider puts
         out at their chosen intensity equals the energy that air drag,
         rolling resistance and climbing take
* run:   threshold pace stretched to the race distance with Riegel's power
         law, scaled by a durability factor that depends on how much long
         running the athlete has done, plus heat

Thousands of races give a distribution instead of a single guess, so the
answer comes with a realistic range.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

G = 9.81
RIEGEL = 1.06  # time grows as distance^1.06 for well-trained runners


@dataclass(frozen=True)
class RaceType:
    """A race distance and how athletes typically pace it.

    Pacing fractions are relative to threshold (roughly one-hour race effort).
    Durability runs from `run_floor` (no long runs, low fitness) to
    `run_ceiling` (well prepared)."""

    key: str
    label: str
    run_m: float
    run_floor: float
    run_ceiling: float
    run_fade_sd: float
    heat_per_c: float  # fractional slowdown per °C above 18
    swim_m: float = 0
    bike_m: float = 0
    swim_frac: tuple[float, float] = (1.0, 1.0)
    bike_if: tuple[float, float] = (1.0, 1.0)  # without and with long rides
    t1_s: tuple[float, float] = (0, 0)
    t2_s: tuple[float, float] = (0, 0)

    @property
    def kind(self) -> str:
        return "triathlon" if self.bike_m else "run"


RACE_TYPES: dict[str, RaceType] = {
    r.key: r
    for r in (
        RaceType("mile", "1 mile", 1609.344, 1.0, 1.0, 0.015, 0.002),
        RaceType("5k", "5K", 5000, 1.0, 1.0, 0.018, 0.003),
        RaceType("10k", "10K", 10_000, 0.99, 1.0, 0.02, 0.004),
        RaceType("half_marathon", "Half marathon", 21_097.5, 0.95, 1.0, 0.025, 0.006),
        RaceType("marathon", "Marathon", 42_195, 0.86, 1.0, 0.03, 0.01),
        RaceType(
            "sprint_tri", "Sprint triathlon", 5000, 0.95, 0.99, 0.02, 0.003,
            swim_m=750, bike_m=20_000, swim_frac=(0.98, 1.04), bike_if=(0.88, 0.92),
            t1_s=(60, 150), t2_s=(40, 100),
        ),
        RaceType(
            "olympic_tri", "Olympic triathlon", 10_000, 0.90, 0.96, 0.025, 0.005,
            swim_m=1500, bike_m=40_000, swim_frac=(0.95, 1.01), bike_if=(0.83, 0.87),
            t1_s=(90, 180), t2_s=(60, 150),
        ),
        RaceType(
            "half_ironman", "Half Ironman (70.3)", 21_097.5, 0.78, 0.89, 0.03, 0.008,
            swim_m=1900, bike_m=90_000, swim_frac=(0.90, 0.97), bike_if=(0.72, 0.78),
            t1_s=(150, 330), t2_s=(100, 220),
        ),
        RaceType(
            "ironman", "Full Ironman", 42_195, 0.70, 0.85, 0.035, 0.01,
            swim_m=3800, bike_m=180_200, swim_frac=(0.86, 0.94), bike_if=(0.66, 0.71),
            t1_s=(240, 480), t2_s=(150, 300),
        ),
    )
}  # fmt: skip


RUN_KEYS = ("mile", "5k", "10k", "half_marathon", "marathon")


def run_race(distance_m: float) -> RaceType:
    """A running race at any distance, its pacing interpolated (on log
    distance) between the standard distances either side of it."""
    std = [RACE_TYPES[k] for k in RUN_KEYS]
    for r in std:
        if abs(r.run_m - distance_m) < 1:
            return r
    x = np.log([r.run_m for r in std])
    t = float(np.log(distance_m))

    def interp(attr: str) -> float:
        return float(np.interp(t, x, [getattr(r, attr) for r in std]))

    km = distance_m / 1000
    return RaceType(
        "run",
        f"{round(km, 1):g} km run",
        distance_m,
        interp("run_floor"),
        interp("run_ceiling"),
        interp("run_fade_sd"),
        interp("heat_per_c"),
    )


def resolve_race(race_type: str, distance_m: float | None = None) -> RaceType:
    """A standard race, or a custom-distance run when `race_type` is "run"."""
    if race_type == "run":
        if not distance_m:
            raise ValueError("a custom run needs a distance")
        return run_race(distance_m)
    return RACE_TYPES[race_type]


@dataclass(frozen=True)
class Course:
    name: str = "Full Ironman"
    race_type: str = "ironman"
    bike_climb_m: float = 1500
    wetsuit: bool = True
    run_temp_c: float = 22.0
    air_density: float = 1.2
    distance_m: float | None = None  # only for a custom-distance run

    @property
    def race(self) -> RaceType:
        return resolve_race(self.race_type, self.distance_m)


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
    legs: dict[str, LegStats]
    run_pace_s_per_km: float
    bike_avg_watts: float | None = None
    bike_avg_speed: float | None = None
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

    return float(brentq(balance, 60, 60 * 3600))


def riegel_fraction(threshold_speed: float, distance_m: float) -> float:
    """Share of threshold speed a fresh runner can hold over `distance_m`.

    Threshold is about one hour of racing, so it anchors Riegel's
    T2 = T1 (D2/D1)^1.06 at T1 = 3600 s. Shorter races come out faster than
    threshold, longer ones slower."""
    d60 = threshold_speed * 3600
    return float((distance_m / d60) ** (1 - RIEGEL))


def durability(longest_run_m: float, ctl: float, race: RaceType | None = None) -> float:
    """Fraction of the fresh-legs pace an athlete can actually hold on the day.

    Well-prepared age groupers run around 80-85% of threshold in an Ironman
    marathon. Missing long runs (relative to the race's run distance) and low
    fitness both pull that down. Short races barely depend on either."""
    race = race or RACE_TYPES["ironman"]
    need = 0.38 * race.run_m  # long runs start to count at ~38% of race distance
    long_run = np.clip((longest_run_m - need) / need, 0, 1)
    fitness = np.clip((ctl - 50) / (110 - 50), 0, 1)
    return float(
        race.run_floor + (race.run_ceiling - race.run_floor) * (0.6 * long_run + 0.4 * fitness)
    )


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
    race = course.race
    rng = np.random.default_rng(seed)
    # one "how's the day going" draw shared by every leg: sleep, stomach, wind
    day = rng.normal(1.0, 0.03, n).clip(0.88, 1.08)
    form = form_multiplier(athlete.race_day_tsb) * day
    legs: dict[str, np.ndarray] = {}
    drivers: dict[str, float] = {"form_multiplier": float(form_multiplier(athlete.race_day_tsb))}
    bike_watts = bike_speed = None

    if race.kind == "triathlon":
        swim_frac = rng.uniform(*race.swim_frac, n)
        sighting = rng.uniform(1.02, 1.08, n)
        wetsuit = 1.04 if course.wetsuit else 1.0
        swim_speed = athlete.css_speed * swim_frac * wetsuit * form
        legs["swim"] = race.swim_m * sighting / swim_speed
        legs["t1"] = rng.uniform(*race.t1_s, n)

        # bike: intensity is lower for athletes without long rides in the legs
        need_h = race.bike_m / 30_000  # hours at a typical 30 km/h
        ride = np.clip((athlete.longest_ride_8wk_s / 3600 - 0.65 * need_h) / (0.4 * need_h), 0, 1)
        lo, hi = race.bike_if
        intensity = np.clip(rng.normal(lo + (hi - lo) * ride, 0.025, n), lo - 0.08, hi + 0.08)
        power = athlete.ftp_watts * intensity * form
        cda = rng.normal(0.29, 0.02, n).clip(0.22, 0.38)
        crr = rng.normal(0.0042, 0.0004, n).clip(0.003, 0.006)
        mass = athlete.weight_kg + 10.5
        legs["bike"] = np.array(
            [
                bike_time(p, race.bike_m, course.bike_climb_m, mass, c, r, course.air_density)
                for p, c, r in zip(power, cda, crr, strict=True)
            ]
        )
        legs["t2"] = rng.uniform(*race.t2_s, n)
        bike_watts = float(np.median(power))
        bike_speed = float(race.bike_m / np.median(legs["bike"]))
        drivers["bike_intensity_factor"] = float(np.median(intensity))

    # run: off the bike, the durability factor alone sets pace against
    # threshold; a standalone race starts from the Riegel fraction instead
    base = durability(athlete.longest_run_8wk_m, athlete.ctl, race)
    fresh = (
        1.0
        if race.kind == "triathlon"
        else riegel_fraction(athlete.run_threshold_speed, race.run_m)
    )
    fade = rng.normal(0.0, race.run_fade_sd, n)
    heat = 1 - race.heat_per_c * max(course.run_temp_c - 18, 0)
    frac = np.clip(fresh * (base + fade), 0.5 * fresh, 1.1 * fresh)
    run_speed = athlete.run_threshold_speed * frac * heat * form
    legs["run"] = race.run_m / run_speed
    drivers["run_durability"] = base
    drivers["run_vs_threshold"] = float(fresh * base * heat)

    total = sum(legs.values())

    def stats(x: np.ndarray) -> LegStats:
        p10, p50, p90 = np.percentile(x, [10, 50, 90])
        return LegStats(float(p10), float(p50), float(p90))

    counts, edges = np.histogram(total, bins=30)
    return RacePrediction(
        total=stats(total),
        legs={k: stats(v) for k, v in legs.items()},
        run_pace_s_per_km=float(np.median(legs["run"]) / (race.run_m / 1000)),
        bike_avg_watts=bike_watts,
        bike_avg_speed=bike_speed,
        histogram=[
            (float((a + b) / 2), int(c))
            for a, b, c in zip(edges[:-1], edges[1:], counts, strict=True)
        ],
        drivers=drivers,
    )
