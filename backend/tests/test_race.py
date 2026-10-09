import pytest

from app.analytics.race import (
    RACE_TYPES,
    AthleteProfile,
    Course,
    bike_time,
    durability,
    riegel_fraction,
    simulate,
)

A = AthleteProfile(
    ftp_watts=214,
    run_threshold_speed=4.4,
    css_speed=1.0,
    weight_kg=77,
    ctl=90,
    race_day_tsb=12,
    longest_run_8wk_m=29_000,
    longest_ride_8wk_s=20_000,
)


def test_bike_physics_is_plausible():
    t = bike_time(150, 180_000, 1500, 88, 0.29, 0.0042, 1.2)
    assert 5.2 * 3600 < t < 6.8 * 3600


def test_more_power_is_faster():
    slow = bike_time(140, 180_000, 1000, 88, 0.3, 0.0045, 1.2)
    fast = bike_time(180, 180_000, 1000, 88, 0.3, 0.0045, 1.2)
    assert fast < slow


def test_durability_rewards_long_runs():
    assert durability(32_000, 100) > durability(18_000, 100)


def test_riegel_is_anchored_at_one_hour():
    assert riegel_fraction(4.4, 4.4 * 3600) == pytest.approx(1.0)
    assert riegel_fraction(4.4, 5000) > 1 > riegel_fraction(4.4, 42_195)


def test_prediction_is_ordered_and_realistic():
    p = simulate(A, Course(), n=2000)
    assert p.total.p10 < p.total.p50 < p.total.p90
    assert 9 * 3600 < p.total.p50 < 15 * 3600
    assert sum(c for _, c in p.histogram) == 2000


def test_heat_slows_the_run():
    cool = simulate(A, Course(run_temp_c=15), n=500)
    hot = simulate(A, Course(run_temp_c=32), n=500)
    assert hot.legs["run"].p50 > cool.legs["run"].p50


# a 4.4 m/s threshold (~3:47/km) is a roughly 17:30 5K, 2:50-3:00 marathon runner
@pytest.mark.parametrize(
    ("race", "lo_min", "hi_min"),
    [
        ("mile", 4.8, 6.0),
        ("5k", 16.5, 19),
        ("10k", 35, 39),
        ("half_marathon", 77, 86),
        ("marathon", 165, 190),
        ("sprint_tri", 60, 85),
        ("olympic_tri", 120, 155),
        ("half_ironman", 270, 345),
        ("ironman", 540, 900),
    ],
)
def test_every_distance_is_realistic(race, lo_min, hi_min):
    p = simulate(A, Course(race_type=race, bike_climb_m=0, run_temp_c=18), n=400)
    assert lo_min * 60 < p.total.p50 < hi_min * 60
    assert sum(leg.p50 for leg in p.legs.values()) == pytest.approx(p.total.p50, rel=0.03)


def test_run_races_have_only_a_run_leg():
    p = simulate(A, Course(race_type="marathon"), n=200)
    assert set(p.legs) == {"run"} and p.bike_avg_watts is None


def test_longer_races_are_slower_per_km():
    paces = [
        simulate(A, Course(race_type=k, run_temp_c=18), n=300).run_pace_s_per_km
        for k in ("mile", "5k", "10k", "half_marathon", "marathon")
    ]
    assert paces == sorted(paces)


def test_triathlon_legs_in_order():
    for key, r in RACE_TYPES.items():
        if r.kind == "triathlon":
            assert list(simulate(A, Course(race_type=key), n=100).legs) == [
                "swim",
                "t1",
                "bike",
                "t2",
                "run",
            ]


def test_custom_run_distances_fit_between_the_standard_ones():
    from app.analytics.race import resolve_race

    t = {d: simulate(A, Course(race_type="run", distance_m=d, run_temp_c=18), n=300).total.p50
         for d in (5000, 8000, 10_000, 15_000, 21_097.5)}  # fmt: skip
    assert t[5000] < t[8000] < t[10_000] < t[15_000] < t[21_097.5]
    assert resolve_race("run", 15_000).label == "15 km run"
    assert resolve_race("run", 42_195).key == "marathon"  # a standard distance stays standard
