from app.analytics.race import AthleteProfile, Course, bike_time, durability, simulate

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


def test_prediction_is_ordered_and_realistic():
    p = simulate(A, Course(), n=2000)
    assert p.total.p10 < p.total.p50 < p.total.p90
    assert 9 * 3600 < p.total.p50 < 15 * 3600
    assert sum(c for _, c in p.histogram) == 2000


def test_heat_slows_the_run():
    cool = simulate(A, Course(run_temp_c=15), n=500)
    hot = simulate(A, Course(run_temp_c=32), n=500)
    assert hot.run.p50 > cool.run.p50
